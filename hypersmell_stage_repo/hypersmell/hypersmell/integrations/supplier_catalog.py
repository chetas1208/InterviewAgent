from loguru import logger

from hypersmell.integrations.base import Integration, PaginatedResult, retry
from hypersmell.integrations.utils import normalize_ingredient


class SupplierCatalogIntegration(Integration):
    """Syncs fragrance ingredients from the Supplier Catalog API."""

    def __init__(self, connection, settings):
        super().__init__(connection, settings)
        # Direct OAuth — token stored on the connection record
        if connection and connection.access_token:
            self.client.headers["Authorization"] = f"Bearer {connection.access_token}"

    @retry(max_retries=3)
    def list_resources(self, cursor: str | None = None) -> PaginatedResult:
        """List ingredients from the supplier catalog."""
        params = {}
        if cursor:
            params["cursor"] = cursor

        response = self.client.get(
            f"{self.settings.supplier_catalog_api_url}/ingredients",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        logger.debug(
            f"Listed {len(data['items'])} ingredients "
            f"(cursor: {cursor} -> {data['next_cursor']})"
        )

        return PaginatedResult(
            items=data["items"],
            next_cursor=data["next_cursor"],
        )

    @retry(max_retries=3)
    def fetch_resource(self, external_id: str) -> dict:
        """Fetch full ingredient details."""
        response = self.client.get(
            f"{self.settings.supplier_catalog_api_url}/ingredients/{external_id}",
        )
        response.raise_for_status()

        ingredient = response.json()
        ingredient["name"] = normalize_ingredient(ingredient["name"])
        logger.debug(f"Fetched ingredient: {ingredient['name']}")

        return {
            "external_id": ingredient["id"],
            "title": ingredient["name"],
            "content": self._build_content(ingredient),
            "metadata": {
                "cas_number": ingredient.get("cas_number"),
                "scent_family": ingredient.get("scent_family"),
                "supplier": ingredient.get("supplier"),
                "price_per_kg": ingredient.get("price_per_kg"),
                "origin_country": ingredient.get("origin_country"),
                "synonyms": ingredient.get("synonyms", []),
            },
        }

    def _build_content(self, ingredient: dict) -> str:
        """Build searchable content from ingredient data."""
        parts = [
            ingredient["name"],
            ingredient.get("description", ""),
            f"Safety: {ingredient.get('safety_notes', '')}",
        ]
        if ingredient.get("synonyms"):
            parts.append(f"Also known as: {', '.join(ingredient['synonyms'])}")
        return "\n\n".join(filter(None, parts))
