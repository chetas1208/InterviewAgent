from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://hypersmell:hypersmell@postgres:5432/hypersmell"
    redis_url: str = "redis://redis:6379"
    s3_endpoint_url: str = "http://minio:9000"
    s3_bucket: str = "hypersmell"
    supplier_catalog_api_url: str = "http://supplier-catalog-api:8001"
    tasting_notes_api_url: str = "http://tasting-notes-api:8002"
    embedding_model: str = "all-MiniLM-L6-v2"
    inngest_event_key: str = "local"
    inngest_signing_key: str = ""
    mango_url: str = "http://mango:3000"  # only needed for tasting_notes, remove after migration
    mango_fallback_tokens: str = "{}"  # JSON fallback token map

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()
