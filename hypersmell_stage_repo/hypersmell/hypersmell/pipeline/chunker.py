from loguru import logger

MAX_CHUNK_SIZE = 1500  # characters per chunk


def chunk_document(text: str) -> list[dict]:
    """Split text into chunks for embedding.

    Splits on sentence boundaries, respecting MAX_CHUNK_SIZE.
    """
    if not text:
        return []

    chunks = []
    chunk_index = 0
    remaining_text = text

    while remaining_text:
        if len(remaining_text) <= MAX_CHUNK_SIZE:
            chunks.append({"content": remaining_text, "chunk_index": chunk_index})
            break

        # Find the last sentence boundary before MAX_CHUNK_SIZE
        boundary = remaining_text.rfind(". ", 0, MAX_CHUNK_SIZE)
        if boundary == -1:
            cut_index = MAX_CHUNK_SIZE
        else:
            cut_index = boundary + 1

        chunk_text = remaining_text[:cut_index].strip()

        if chunk_text:
            chunks.append({"content": chunk_text, "chunk_index": chunk_index})
            chunk_index += 1

        remaining_text = remaining_text[cut_index:].strip()

    logger.debug(f"Chunked document: {len(chunks)} chunk(s)")

    return chunks
