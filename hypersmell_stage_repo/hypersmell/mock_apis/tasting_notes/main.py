import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Tasting Notes API")

DATA_PATH = Path(__file__).parent / "seed_data.json"
sessions: list[dict] = []

_request_counts: dict[str, int] = {}


def _should_rate_limit(endpoint: str) -> bool:
    """Return True for every ~10th request to a given endpoint."""
    _request_counts[endpoint] = _request_counts.get(endpoint, 0) + 1
    return _request_counts[endpoint] % 10 == 0


@app.on_event("startup")
def load_data():
    global sessions
    with open(DATA_PATH) as f:
        sessions = json.load(f)


@app.get("/sessions")
def list_sessions(cursor: str | None = None, page_size: int = 50):
    """Paginated tasting session list."""
    if _should_rate_limit("list_sessions"):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "2"},
        )
    start_idx = int(cursor) if cursor else 0
    page = sessions[start_idx : start_idx + page_size]
    next_cursor = str(start_idx + page_size) if start_idx + page_size < len(sessions) else None
    return {"items": page, "next_cursor": next_cursor}


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Get full tasting session detail."""
    if _should_rate_limit("get_session"):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "2"},
        )
    for session in sessions:
        if session["id"] == session_id:
            return session
    raise HTTPException(status_code=404, detail="Session not found")
