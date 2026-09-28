from fastapi import APIRouter

from hypersmell.api.api_keys import router as api_keys_router
from hypersmell.api.integrations import router as integrations_router
from hypersmell.api.resources import router as resources_router
from hypersmell.api.search import router as search_router
from hypersmell.api.webhooks import router as webhooks_router
from hypersmell.api.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(workspaces_router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(api_keys_router, prefix="/api-keys", tags=["api-keys"])
api_router.include_router(resources_router, prefix="/resources", tags=["resources"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(webhooks_router, tags=["webhooks"])
