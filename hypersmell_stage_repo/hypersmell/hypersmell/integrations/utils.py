import re

def normalize_ingredient(name: str) -> str:
    """Normalize ingredient name by stripping parenthetical descriptions.
    
    Example:
        'bergamot oil (cold-pressed)' -> 'bergamot oil'
    """
    if not name:
        return name
    return re.sub(r'\s*\([^)]*\)', '', name).strip()
