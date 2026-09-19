# Evaluation System production handoff

## Ownership and topology

```text
Users / Engineers
       |
Eval Frontend (Nginx)
       |
Eval Backend API <-> PostgreSQL `evaluation` schema <-> Eval Worker
                                                        |
                                             RagBot internal HTTP API
                                                        |
                           Qdrant / TEI / vLLM / application DB / MinIO
```

The Eval frontend owns the static UI, same-origin API reverse proxy, and SSE
proxy behavior. The Eval backend owns datasets, planning, queue/worker logic,
trace persistence, PostgreSQL SSE, and the `evaluation` schema. RagBot owns the
answering pipeline, retrieval, reranking, prompts, generation, pipeline
observer, and its own data/model services.

Eval never connects directly to Qdrant, TEI, vLLM, MinIO, models, or GPUs.
RagBot makes no outbound connection to Eval. Dependency direction is strictly
`Eval -> RagBot`.

## Network contract

- Eval API and worker need the PostgreSQL host/port and credentials for the
  database containing the isolated `evaluation` schema.
- Eval API and worker use `EVAL_RAGBOT_BASE_URL` for a reachable RagBot service.
- Frontend Nginx needs DNS/network routing to the Eval API for
  `/api/v1/evaluation/*`, including long-lived SSE connections.
- RagBot does not need Eval DNS, credentials, or network routes.

Use service addresses reachable from each container; loopback addresses are
only valid when the target really shares that container.

## Images and process roles

Publish immutable tags or commit-SHA tags:

- `ragbot-eval-backend:<immutable-tag>` runs twice: once as the Eval API and
  once as the Eval Worker. Both roles use the same image and configuration.
- `ragbot-eval-frontend:<immutable-tag>` contains Nginx and the static UI.

Registry publication and production deployment are outside this repository's
release-readiness task.

## Database contract

Eval may share a physical PostgreSQL server with RagBot, but it owns only the
`evaluation` schema. There are no foreign keys into RagBot application schemas.
Migrations never run automatically at container startup. Initialization is an
explicit, gated operation using the backend's existing status/initialize
workflow. Application rollback preserves evaluation data; never reset or drop
the schema as part of rollback.

## HTTP compatibility contract

RagBot exposes to Eval:

- `GET /api/documents`
- `POST /api/internal/evaluation/v1/turn`
- `GET /api/internal/evaluation/v1/runtime-snapshot`

Eval exposes the browser/control-plane namespace `/api/v1/evaluation/*` through
Nginx. OpenAPI remains the detailed schema source; this document records
ownership, not a duplicate schema.

If RagBot changes an internal evaluation request or response, update the Eval
backend client, types, and tests in the same coordinated release. Normal
pipeline behavior changes need not change the transport contract. Runtime
snapshots capture RagBot identity/config for traceability.

## Rollback

- Frontend: deploy the prior frontend image.
- Eval API and worker: deploy the prior matching backend image to both roles.
- RagBot: use its independent release rollback.

The HTTP boundary permits independent rollback while the internal evaluation
contract remains compatible. Coordinate versions when that contract changes.
