import inngest
from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from hypersmell.tasks.client import client
from hypersmell.tasks.events import Events

router = APIRouter()


@router.post("/webhooks/supplier-catalog")
async def supplier_catalog_webhook(request: Request):
    """Receive webhook events from the Supplier Catalog API."""
    body = await request.json()
    event_type = body.get("event")
    ingredient_id = body.get("ingredient_id")

    if not event_type or not ingredient_id:
        raise HTTPException(status_code=400, detail="Missing event or ingredient_id")

    logger.info(f"Webhook received: {event_type} for ingredient {ingredient_id}")

    # TODO: verify webhook signature

    await client.send(
        inngest.Event(
            name=Events.WEBHOOK_RECEIVED,
            data={
                "integration": "supplier_catalog",
                "event_type": event_type,
                "external_id": ingredient_id,
            },
        )
    )

    return {"status": "accepted"}
