import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from slack_sdk.signature import SignatureVerifier

from app.api.routes.rag import rag_query
from app.services.slack_service import send_slack_message

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

if not SLACK_SIGNING_SECRET:
    raise ValueError("SLACK_SIGNING_SECRET is not configured")

slack_signature_verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

router = APIRouter(
    prefix="/slack",
    tags=["Slack"],
)


@router.post("/test")
def slack_test(data: dict):
    return send_slack_message(
        channel=data["channel"],
        text=data["text"],
    )


def process_slack_mention(channel: str, text: str, thread_ts: str):
    question = text.split(">", 1)[-1].strip()

    try:
        rag_response = rag_query({"question": question})
    except Exception:
        send_slack_message(
            channel=channel,
            text="No pude generar la respuesta. Intenta nuevamente.",
            thread_ts=thread_ts,
        )
        return

    sources_text = "\n".join(
        [
            f"- {source['page_title']} v{source['page_version']} | score: {round(source['score'], 4)}"
            for source in rag_response["sources"]
        ]
    )

    message = f"""
        *Pregunta:*
        {question}

        *Respuesta:*
        {rag_response["answer"]}

        *Fuentes:*
        {sources_text}
        """

    send_slack_message(
        channel=channel,
        text=message,
        thread_ts=thread_ts,
    )


@router.post("/rag")
def slack_rag(data: dict):
    channel = data["channel"]
    question = data["question"]

    rag_response = rag_query({"question": question})

    sources_text = "\n".join(
        [
            f"- {source['page_title']} v{source['page_version']} | score: {round(source['score'], 4)}"
            for source in rag_response["sources"]
        ]
    )

    message = f"""
        *Pregunta:*
        {question}

        *Respuesta:*
        {rag_response["answer"]}

        *Fuentes:*
        {sources_text}
        """

    return send_slack_message(channel=channel, text=message)



@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()

    if not slack_signature_verifier.is_valid_request(raw_body, dict(request.headers)):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    data = await request.json()

    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    event = data.get("event", {})

    if event.get("type") == "app_mention":
        background_tasks.add_task(
            process_slack_mention, event["channel"], event["text"], event["ts"]
        )

    return {"ok": True}
