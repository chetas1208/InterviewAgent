# Legacy connection manager — migrating to direct OAuth.
# See supplier_catalog for the new pattern.

import json

import httpx
from loguru import logger


class MangoClient:
    """Client for Mango OAuth connection manager.

    Falls back to local token lookup via MANGO_FALLBACK_TOKENS env var
    when the Mango service is unreachable.
    """

    def __init__(self, mango_url: str, fallback_tokens: str = "{}"):
        self.mango_url = mango_url
        self._fallback_tokens: dict[str, str] = json.loads(fallback_tokens)
        self.client = httpx.Client(timeout=10)

    def get_connection(self, connection_id: str) -> dict:
        """Get connection details from Mango."""
        try:
            response = self.client.get(
                f"{self.mango_url}/connections/{connection_id}"
            )
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.HTTPStatusError):
            logger.warning(
                f"Mango unreachable, using fallback token for {connection_id}"
            )
            if connection_id in self._fallback_tokens:
                return {
                    "id": connection_id,
                    "access_token": self._fallback_tokens[connection_id],
                }
            raise

    def get_token(self, connection_id: str) -> str:
        """Get the current access token for a connection."""
        conn = self.get_connection(connection_id)
        return conn["access_token"]

    def refresh_token(self, connection_id: str) -> str:
        """Refresh an expired token."""
        try:
            response = self.client.post(
                f"{self.mango_url}/connections/{connection_id}/refresh"
            )
            response.raise_for_status()
            return response.json()["access_token"]
        except (httpx.ConnectError, httpx.HTTPStatusError):
            logger.warning(f"Mango unreachable, returning cached token for {connection_id}")
            return self._fallback_tokens.get(connection_id, "")

    def close(self):
        self.client.close()
