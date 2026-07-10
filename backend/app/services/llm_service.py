import os
import cohere

COHERE_API_KEY = os.getenv("COHERE_API_KEY")
COHERE_MODEL= os.getenv("COHERE_MODEL")

client = cohere.ClientV2(api_key=COHERE_API_KEY)

def generate_answer(question: str, context: str) -> str:
    response = client.chat(
        model=COHERE_MODEL,
        messages=[
            {
                "role": "system",
                "content": """
Eres un asistente RAG estricto.

Reglas:
1. Responde únicamente con información presente explícitamente en el contexto.
2. No agregues ejemplos, supuestos, inferencias ni conocimiento externo.
3. Si el contexto no contiene suficiente información, responde: "No está especificado en la documentación disponible."
4. No inventes estados, funcionalidades, nombres de módulos ni detalles operativos.
5. Responde de forma breve y directa.
"""
            },
            {
                "role": "user",
                "content": f"""
Contexto:
{context}

Pregunta:
{question}
"""
            }
        ]
    )

    return response.message.content[0].text


    