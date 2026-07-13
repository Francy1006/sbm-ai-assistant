from slack_sdk import WebClient

from app.config.settings import SLACK_BOT_TOKEN

if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN is not configured")

client = WebClient(token=SLACK_BOT_TOKEN)


def send_slack_message(
    channel: str,
    text: str,
    thread_ts: str | None = None
):
    response = client.chat_postMessage(
        channel=channel,
        text=text,
        thread_ts=thread_ts
    )

    return response.data