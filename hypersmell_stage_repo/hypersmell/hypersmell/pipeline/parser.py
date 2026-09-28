import re
from loguru import logger

SCENT_FAMILY_KEYWORDS = {
    "floral": ["floral", "rose", "jasmine", "lavender", "lily", "ylang-ylang"],
    "woody": ["woody", "sandalwood", "cedar", "vetiver", "patchouli", "pine"],
    "citrus": ["citrus", "lemon", "bergamot", "orange", "grapefruit", "mandarin"],
    "musky": ["musky", "musk", "ambrette", "ambergris"],
    "oriental": ["oriental", "vanilla", "amber", "resin", "incense"],
    "fresh": ["fresh", "aquatic", "marine", "green", "ozonic", "mint"],
}

def extract_scent_families(text: str) -> list[str]:
    """Heuristic extraction of scent families from text using keyword matching."""
    text_lower = text.lower()
    families = set()
    for family, keywords in SCENT_FAMILY_KEYWORDS.items():
        for keyword in keywords:
            # Match whole words only
            if re.search(rf"\b{keyword}\b", text_lower):
                families.add(family)
                break
    return sorted(list(families))


def parse_document(content: str, metadata: dict | None = None) -> str:
    """Parse raw document content into clean text.

    For mock API content, this mostly passes through with whitespace
    normalization. Real integrations would handle PDF, DOCX, etc.
    """
    if not content:
        logger.warning("Empty content received for parsing")
        return ""

    # Normalize whitespace
    text = " ".join(content.split())
    
    if metadata is not None:
        metadata["scent_families"] = extract_scent_families(text)
        
    logger.debug(f"Parsed document: {len(text)} chars")
    return text
