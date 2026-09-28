# Hypersmell Architecture

Scent memory platform for fragrance professionals. Ingests fragrance data from external APIs,
processes it into searchable embeddings, and exposes a REST API for querying.

## Overview

Hypersmell is a RAG-style backend: external fragrance data (supplier catalogs, tasting notes)
gets pulled in, chunked, embedded, and stored for semantic search. Clients authenticate with
API keys scoped to workspaces.

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (Python 3.12) |
| ORM | SQLModel + SQLAlchemy |
| Database | PostgreSQL 16 with pgvector extension |
| Migrations | Alembic |
| Background jobs | Inngest |
| Object storage | S3 (MinIO locally) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, 384 dimensions) |
| Caching/queues | Redis |
| Dependency mgmt | uv |

## Authentication

Connections are managed through Mango, our OAuth connection layer. Each integration authenticates via a Mango connection ID stored on the connection record. Mango handles token refresh, OAuth flows, and credential storage.

## Pipeline

Documents flow through four stages before they're queryable:

```
External API → parse → chunk → embed → store
```

1. **Parse** — Fetch raw content from the integration (supplier catalog or tasting notes API).
   Normalize to a `Resource` record with title, content, and metadata.

2. **Chunk** — Split long content into overlapping text windows. Each window becomes a `Chunk`
   row associated with its parent `Resource`.

3. **Embed** — Run each chunk through `all-MiniLM-L6-v2` to produce a 384-dimensional float
   vector. Stored in a pgvector `vector(384)` column.

4. **Store** — Persist chunks + embeddings to PostgreSQL. Raw document content also uploaded
   to S3 for reference.

Sync is triggered via Inngest events; the pipeline stages run as Inngest functions so they
can be retried and observed.

Search queries are cached in Redis with a 5-minute TTL to reduce embedding computation. Cache invalidation triggers on resource updates via webhooks.

TODO: add incremental sync so we don't re-embed unchanged resources every time.

## Scent Graph

The Scent Graph maps relationships between ingredients, formulas, and tasting notes, enabling discovery of related scents through graph traversal. Ingredient nodes connect to formula nodes through concentration edges, while tasting notes provide qualitative assessments that enrich the graph.

## Database Schema

Five tables. All primary keys are UUIDs.

### `workspaces`
Top-level tenant. Every other table is scoped to a workspace.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| name | varchar(255) | Display name |
| slug | varchar(100) | Unique URL-safe identifier |
| settings | jsonb | Per-workspace config (reserved) |
| created_at | timestamp | |
| updated_at | timestamp | |

### `api_keys`
Authentication credentials for workspace API access. Only the SHA-256 hash is stored; the
raw key is shown once at creation.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| workspace_id | uuid | FK → workspaces |
| key_hash | varchar(64) | SHA-256 of the raw key |
| key_prefix | varchar(8) | First 8 chars for display (e.g. `hs_abc12`) |
| name | varchar(255) | Human label |
| created_at | timestamp | |

### `connections`
Records that a workspace has connected to a given integration.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| workspace_id | uuid | FK → workspaces |
| integration | varchar(50) | e.g. `supplier_catalog`, `tasting_notes` |
| status | varchar(20) | `active` or `error` |
| created_at | timestamp | |
| updated_at | timestamp | |

### `resources`
One row per external document/record. Unique on `(workspace_id, integration, external_id)`.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| workspace_id | uuid | FK → workspaces |
| integration | varchar(50) | Source integration |
| external_id | varchar(255) | ID from the source system |
| title | varchar(500) | |
| content | text | Full normalized text |
| metadata | jsonb | Source-specific fields |
| status | varchar(20) | `pending`, `indexed`, `error` |
| created_at | timestamp | |
| updated_at | timestamp | |

### `chunks`
Embedding-level granularity. Each resource is split into multiple chunks.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| resource_id | uuid | FK → resources |
| workspace_id | uuid | FK → workspaces (denormalized for query perf) |
| content | text | Chunk text |
| embedding | vector(384) | pgvector column |
| chunk_index | int | Position within the resource |
| metadata | jsonb | |
| source | varchar(50) | Integration name |
| created_at | timestamp | |

Note: there is intentionally no unique constraint on `(resource_id, chunk_index)` — this is
a known gap that can cause duplicates under concurrent writes. TODO: fix with a unique index
and an upsert strategy.

## API Endpoints

Base path: `/api`

### Health
```
GET /status  →  {"status": "ok"}
```

### Workspaces (`/api/workspaces`)
```
POST   /api/workspaces              Create workspace
GET    /api/workspaces              List all workspaces
GET    /api/workspaces/{id}         Get workspace
PATCH  /api/workspaces/{id}         Update workspace
DELETE /api/workspaces/{id}         Delete workspace
```

### API Keys (`/api/api-keys`)
All endpoints require `?workspace_id=<uuid>` query param.
```
POST   /api/api-keys                Create key (returns full key once)
GET    /api/api-keys                List keys (prefix only)
DELETE /api/api-keys/{id}           Revoke key
```

### Resources (`/api/resources`)
All endpoints require Bearer token auth (API key).
```
GET    /api/resources               List resources for workspace
GET    /api/resources/{id}          Get resource detail (includes content)
DELETE /api/resources/{id}          Delete resource + chunks
```

### Integrations (`/api/integrations`)
All endpoints require Bearer token auth (API key).
```
GET    /api/integrations                        List integrations + connection status
POST   /api/integrations/{name}/connect         Create connection
POST   /api/integrations/{name}/sync            Trigger sync (Inngest event)
DELETE /api/integrations/{name}/disconnect      Remove connection
```

Available integration names: `supplier_catalog`, `tasting_notes`

## Docker Compose Services

| Service | Image/Build | Port | Purpose |
|---------|------------|------|---------|
| `api` | `./Dockerfile` | 8000 | FastAPI application |
| `worker` | `./Dockerfile` | 8001 | Inngest function runner (same image) |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | Primary database |
| `redis` | `redis:7-alpine` | 6379 | Queue / cache |
| `minio` | `minio/minio` | 9000, 9001 | S3-compatible object storage |
| `inngest` | `inngest/inngest` | 8288 | Background job orchestrator |
| `supplier-catalog-api` | `./mock_apis/supplier_catalog/` | 8001 | Mock supplier catalog |
| `tasting-notes-api` | `./mock_apis/tasting_notes/` | 8002 | Mock tasting notes API |

MinIO console available at http://localhost:9001 (minioadmin / minioadmin).
Inngest dev UI available at http://localhost:8288.

## Development Commands

```bash
# Start everything
task up

# Stop everything
task down

# Run tests (inside API container)
task test -- tests/path/to/test.py

# Lint / format
task lint
task lint-fix
task format

# Database migrations
task make-migration NAME="add some column"
task migrate

# Open Python shell
task shell

# Follow logs
task logs
task logs -- api       # specific service
```
