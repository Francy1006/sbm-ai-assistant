from functools import lru_cache

from fastembed import TextEmbedding

from app.config.settings import EMBEDDING_MODEL_NAME


@lru_cache(maxsize=1)
def _get_model() -> TextEmbedding:
    return TextEmbedding(model_name=EMBEDDING_MODEL_NAME)


def create_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    return [
        embedding.tolist()
        for embedding in _get_model().embed(texts, batch_size=16)
    ]


def create_embedding(text: str) -> list[float]:
    return create_embeddings([text])[0]
