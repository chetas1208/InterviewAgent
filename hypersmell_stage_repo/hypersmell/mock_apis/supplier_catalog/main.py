import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Supplier Catalog API")

DATA_PATH = Path(__file__).parent / "seed_data.json"
ingredients: list[dict] = []
webhooks: list[dict] = []


@app.on_event("startup")
def load_data():
    global ingredients
    with open(DATA_PATH) as f:
        ingredients = json.load(f)


@app.get("/ingredients")
def list_ingredients(cursor: str | None = None, page_size: int = 50):
    """Paginated ingredient list with cursor-based pagination."""
    start_idx = 0
    if cursor:
        start_idx = int(cursor)
    page = ingredients[start_idx : start_idx + page_size]
    next_cursor = str(start_idx + page_size) if start_idx + page_size < len(ingredients) else None
    return {"items": page, "next_cursor": next_cursor}


@app.get("/ingredients/{ingredient_id}")
def get_ingredient(ingredient_id: str):
    """Get full ingredient detail."""
    for ingredient in ingredients:
        if ingredient["id"] == ingredient_id:
            return ingredient
    raise HTTPException(status_code=404, detail="Ingredient not found")


@app.post("/webhooks")
async def register_webhook(request: Request):
    """Register a webhook callback URL."""
    body = await request.json()
    webhook_id = f"wh_{len(webhooks) + 1:03d}"
    webhooks.append({"id": webhook_id, "callback_url": body.get("callback_url")})
    return {"id": webhook_id, "status": "registered"}


@app.post("/webhooks/{webhook_id}/test")
def test_webhook(webhook_id: str):
    """Send a test webhook event."""
    for wh in webhooks:
        if wh["id"] == webhook_id:
            return {"status": "sent", "webhook_id": webhook_id}
    raise HTTPException(status_code=404, detail="Webhook not found")
