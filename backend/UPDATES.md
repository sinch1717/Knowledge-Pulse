# Multi-Tenancy Update

## Purpose
Organization-based multi-tenancy was introduced to isolate customer-specific knowledge, documents, vector embeddings, chat conversations, and analytics across different organizations. Previously, all operations operated on a single shared global dataset. With this update, the FastAPI backend supports multiple isolated organization datasets hosted on the same infrastructure.

## Tenant model
For this milestone, the model follows **One User = One Organization**.
Multiple users belonging to the same organization are not yet supported. All backend data belongs strictly to exactly one organization identified by `organization_id`.

## Tenant identifier
The tenant boundary is represented by `organization_id`:
- **HTTP Requests**: Supplied exclusively via the standard HTTP header:
  ```http
  X-Organization-Id: <organization_id>
  ```
- **Validation**: Must be a non-empty string consisting of 1–64 alphanumeric characters, underscores, or hyphens (`^[a-zA-Z0-9_-]{1,64}$`). Missing, empty, or malformed headers on tenant-scoped routes are rejected immediately with HTTP 400 (`"X-Organization-Id header is required."`).
- **Development Tooling**: `DEFAULT_ORGANIZATION_ID = "org_default"` is defined in `app/config.py` as a temporary fallback *strictly* for internal development tooling, legacy operational scripts, and smoke tests. HTTP routes never fall back to `org_default`.

## Database changes
No separate `Organization` SQL table was created for this milestone, keeping tenant identity lightweight and prepared for future Next.js integration.

### Models Modified (`app/models.py`)
The `organization_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)` column and indexes were added to all 9 tenant-owned models:
1. `Source` (composite index: `(organization_id, created_at)`)
2. `Chunk` (composite index: `(organization_id, source_id)`)
3. `Conversation` (composite index: `(organization_id, session_id)`)
4. `Message` (composite indexes: `(organization_id, period)`, `(organization_id, created_at)`, `(organization_id, conversation_id)`)
5. `TopicCluster` (composite index: `(organization_id, period)`)
6. `ClusterMember` (composite index: `(organization_id, cluster_id)`)
7. `Report` (composite index: `(organization_id, period)`)
8. `Recommendation` (composite index: `(organization_id, report_id)`)
9. `EvaluationRun` (composite index: `(organization_id, ran_at)`)

### Migration Script
- Created `scripts/migrate_multitenancy.py` to idempotently alter SQLite tables, backfill existing rows with `org_default`, and establish required indexes.

## API changes
Existing endpoint paths, request bodies, and response payloads remain compatible. The `X-Organization-Id` header is required for all business endpoints:

- **Sources**:
  - `GET /api/sources` (scoped to tenant)
  - `POST /api/sources` (creates source under tenant)
  - `POST /api/sources/upload` (creates uploaded file source under tenant)
  - `POST /api/sources/{source_id}/reindex` (scoped to `source_id` + `organization_id`; returns 404 if not found)
  - `DELETE /api/sources/{source_id}` (scoped to `source_id` + `organization_id`; returns 404 if not found)
- **Chat**:
  - `POST /api/chat` (scoped RAG retrieval and conversation logging)
- **Overview & Insights**:
  - `GET /api/overview` (scoped to tenant)
  - `GET /api/insights` (scoped to tenant and period)
  - `GET /api/insights/{insight_id}` (scoped to `insight_id` + `organization_id`; returns 404 if not found)
- **Reports**:
  - `GET /api/reports/latest` (returns latest report for tenant)
  - `GET /api/reports` (lists tenant reports)
- **Analytics**:
  - `POST /api/analytics/run` (triggers background batch for requesting tenant)
- **Evaluation**:
  - `GET /api/evaluation/latest` (returns latest evaluation run for tenant)
- **Health (Infrastructure)**:
  - `GET /api/health` continues to operate publicly **without** requiring `X-Organization-Id`.

## Vector store changes
In `app/vector_store.py`:
- `upsert(...)`: Stores `organization_id` in the metadata of every indexed chunk.
- `search(...)`: Accepts `organization_id` and applies Chroma native metadata filtering:
  ```python
  where={"organization_id": organization_id}
  ```
  Filtering occurs directly inside Chroma, preventing cross-tenant vector leakage before retrieval.
- `delete_source(...)`: Filters vector deletion by both `source_id` and `organization_id`:
  ```python
  where={"$and": [{"source_id": {"$eq": source_id}}, {"organization_id": {"$eq": organization_id}}]}
  ```

## RAG changes
In `app/rag/engine.py`:
- `answer(...)`: Accepts `organization_id`. Vectors are retrieved solely using tenant-scoped filters. Both customer and assistant messages and conversation records are persisted with `organization_id`.
- `retrieve_only(...)`: Accepts `organization_id` to evaluate retrieval against the specific organization's chunks.
- Confidence scoring calculation (`compute_confidence`) remains unchanged.

## Analytics changes
In `app/analytics/batch.py` and `app/analytics/recommend.py`:
- `run_batch(db, period, organization_id)`: Loads only questions belonging to the specified tenant and period.
- `_clear_period(db, period, organization_id)`: Deletes only that tenant's clusters and reports for the period.
- Historical trend matching (`match_to_previous`) compares centroids only against previous period clusters of the same organization.
- `TopicCluster`, `ClusterMember`, `Report`, and `Recommendation` entities are persisted with `organization_id`.

## Scripts updated
All operational and developer scripts accept `--organization-id` (defaulting to `org_default` for development compatibility):
- `scripts/migrate_multitenancy.py`: Database schema migration and backfill.
- `scripts/seed_conversations.py`: Accepts `--organization-id`, queries headings for that tenant, and tags replayed chat turns with that tenant ID.
- `scripts/run_analytics.py`: Accepts `--organization-id` and runs the analytics batch for that tenant.
- `scripts/build_eval_set.py`: Accepts `--organization-id` and samples chunks belonging to that tenant.
- `scripts/run_evaluation.py`: Accepts `--organization-id` and runs reference-free evaluation for that tenant.
- `scripts/smoke_test.py`: Updated to use `org_default` across all pipeline phases and verifies HTTP endpoint multi-tenancy.

## Tests
A dedicated isolation test suite was created in `tests/test_multitenancy.py` (executed with `python -m unittest tests/test_multitenancy.py`), verifying:
- Public accessibility of `/api/health` without headers.
- Rejection (HTTP 400) of missing, empty, or malformed `X-Organization-Id` headers across all tenant endpoints.
- Strict isolation between two independent tenants (`org_test_alpha` and `org_test_beta`) for sources, chat retrieval, insights, reports, and analytics batches.
- Cross-tenant lookups and deletion returning HTTP 404.

## Migration instructions
To migrate an existing SQLite development database:
```bash
python scripts/migrate_multitenancy.py
```
The migration script is idempotent, preserves existing data, backfills existing rows to `org_default`, and verifies that zero NULL values remain.

## Local development
For local curl or API requests, include the `X-Organization-Id` header:
```bash
# List sources
curl http://localhost:8000/api/sources \
  -H "X-Organization-Id: org_default"

# Ask a question
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: org_default" \
  -d '{"question":"How do I edit an invoice?","session_id":"dev_sess_1"}'
```

## Future Next.js integration
The Next.js application will derive `organization_id` from the authenticated user in MongoDB and supply `X-Organization-Id: <organization_id>` on all server-to-server HTTP calls to the FastAPI backend. User identity and authentication enforcement remain the responsibility of the Next.js application.

## Known limitation
One user per organization is assumed for this milestone. Multiple users belonging to the same organization are intentionally deferred to a later milestone.
