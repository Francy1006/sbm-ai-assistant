from fastembed import TextEmbedding

model = TextEmbedding(model_name="intfloat/multilingual-e5-large")

def create_embedding(text: str) -> list[float]:
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()