import os

import inngest

# Use dev mode (no signing key required) unless INNGEST_SIGNING_KEY is set.
# In production Porter/Doppler injects INNGEST_SIGNING_KEY automatically.
_is_production = bool(os.getenv("INNGEST_SIGNING_KEY"))

client = inngest.Inngest(
    app_id="hypersmell",
    is_production=_is_production,
)
