from loguru import logger
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def get_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """Load embedding model (cached after first call)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {model_name}")
        _model = SentenceTransformer(model_name)
    return _model


def embed_chunks(chunks: list[dict], model_name: str = "all-MiniLM-L6-v2") -> list[dict]:
    """Add embedding vectors to chunks."""
    if not chunks:
        return []

    model = get_model(model_name)
    texts = [chunk["content"] for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=False)

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        if hasattr(embedding, "tolist"):
            chunk["embedding"] = embedding.tolist()
        else:
            chunk["embedding"] = embedding

    logger.debug(f"Embedded {len(chunks)} chunks")
    return chunks
