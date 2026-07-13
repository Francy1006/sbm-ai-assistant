import cohere

from app.config.settings import COHERE_API_KEY, COHERE_MODEL
from app.prompts.rag_system_prompt import RAG_SYSTEM_PROMPT

client = cohere.ClientV2(api_key=COHERE_API_KEY)


def generate_answer(question: str, context: str) -> str:
    response = client.chat(
        model=COHERE_MODEL,
        messages=[
            {
                "role": "system",
                "content": RAG_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": f"""
Contexto:
{context}

Pregunta:
{question}
""",
            },
        ],
    )

    return response.message.content[0].text