from loguru import logger

from hypersmell.auth.mango import MangoClient
from hypersmell.integrations.base import Integration, PaginatedResult, retry
from hypersmell.integrations.utils import normalize_ingredient


class TastingNotesIntegration(Integration):
    """Syncs tasting session data from the Tasting Notes API.

    NOTE: Still using Mango for auth — needs migration to direct OAuth
    like supplier_catalog.
    """

    def __init__(self, connection, settings):
        super().__init__(connection, settings)
        self.mango = MangoClient(settings.mango_url, settings.mango_fallback_tokens)

    def _get_auth_headers(self) -> dict[str, str]:
        token = self.mango.get_token(self.connection.mango_connection_id)
        return {"Authorization": f"Bearer {token}"}

    @retry(max_retries=3)
    def list_resources(self, cursor: str | None = None) -> PaginatedResult:
        """List tasting sessions."""
        params = {}
        if cursor:
            params["cursor"] = cursor

        response = self.client.get(
            f"{self.settings.tasting_notes_api_url}/sessions",
            params=params,
            headers=self._get_auth_headers(),
        )
        response.raise_for_status()
        data = response.json()

        logger.debug(
            f"Listed {len(data['items'])} sessions "
            f"(cursor: {cursor} -> {data['next_cursor']})"
        )

        return PaginatedResult(
            items=data["items"],
            next_cursor=data["next_cursor"],
        )

    @retry(max_retries=3)
    def fetch_resource(self, external_id: str) -> dict:
        """Fetch full tasting session details."""
        response = self.client.get(
            f"{self.settings.tasting_notes_api_url}/sessions/{external_id}",
            headers=self._get_auth_headers(),
        )
        response.raise_for_status()
        session_data = response.json()
        
        # Normalize ingredients across note arrays
        normalized_ingredients = [normalize_ingredient(i) for i in session_data.get("ingredients", [])]
        top_notes = [normalize_ingredient(n) for n in session_data.get("top_notes", [])]
        middle_notes = [normalize_ingredient(n) for n in session_data.get("middle_notes", [])]
        base_notes = [normalize_ingredient(n) for n in session_data.get("base_notes", [])]
        
        # Build searchable content
        content = f"Tasting Session: {session_data.get('scent_name')}\n"
        content += f"Perfumer: {session_data.get('perfumer_name')}\n"
        content += f"Commentary: {session_data.get('commentary')}\n"
        content += f"Ingredients: {', '.join(normalized_ingredients)}\n"

        return {
            "external_id": session_data["id"],
            "title": session_data.get("scent_name", "Unknown Session"),
            "content": content,
            "metadata": {
                "perfumer_name": session_data.get("perfumer_name"),
                "overall_rating": session_data.get("overall_rating"),
                "sillage": session_data.get("sillage"),
                "longevity_hours": session_data.get("longevity_hours"),
                "top_notes": top_notes,
                "middle_notes": middle_notes,
                "base_notes": base_notes,
                "ingredients": normalized_ingredients,
            }
        }

    def close(self):
        self.mango.close()
        super().close()
