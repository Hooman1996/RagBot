# Production Knowledge Update Diagnostics

Run these checks on development and production independently, save both
outputs, and diff them. Commands are read-only unless a section explicitly says
otherwise. Do not paste secret values into tickets; compare secret fingerprints
or secret-manager version IDs.

Start with the bundled collector from the deployed repository:

```bash
cd /path/to/deployed/faq
bash scripts/diagnose_knowledge_update_production.sh > /tmp/knowledge-update-diagnostic.txt 2>&1
```

It reports processes, worker count evidence, working directories, non-secret
configuration, TCP reachability, filesystem permissions, listening ports, and
container layout. It never restarts services or mutates data.

## Application differential

```bash
git rev-parse HEAD
git status --short
python3 --version
python3 -m pip freeze | sort
ps -eo pid,ppid,user,lstart,args | grep -E '[g]unicorn|[u]vicorn|[f]astapi.*main:app'
for pid in $(pgrep -f 'gunicorn|uvicorn|fastapi.*main:app'); do readlink -f "/proc/$pid/cwd"; done
systemctl show YOUR_APP_UNIT -p User -p Group -p WorkingDirectory -p ExecStart -p FragmentPath
```

Compare exact Git SHA, Python and package versions (especially
`qdrant-client==1.16.2` from the repository lock), startup command, worker
count, working directory, service account, and unit/container image digest.
Confirm the running code contains `wait=True` in
`QdrantKnowledgeVectorStore.upsert` and the revision-aware BM25 cache.

## Safe environment comparison

Run within the same environment namespace as each FastAPI worker:

```bash
python3 -m new_architecture.knowledge_update_diagnostics --check-configuration --check-paths --check-connections
```

Compare these non-secret values exactly:

```text
POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER
QDRANT_HOST QDRANT_PORT QDRANT_COLLECTION QDRANT_HTTPS
MINIO_ENDPOINT MINIO_BUCKET MINIO_SECURE MINIO_KNOWLEDGE_PREFIX
DATA_INSERTION_DIRECTORY KNOWLEDGE_BASE_CSV
TEI_EMBED_URL TEI_RERANK_URL
WEB_CONCURRENCY
```

For secrets, compare fingerprints without revealing values:

```bash
for name in POSTGRES_PASSWORD QDRANT_API_KEY MINIO_ACCESS_KEY MINIO_SECRET_KEY; do
  value="${!name:-}"
  if [[ -n "$value" ]]; then
    printf '%s ' "$name"
    printf '%s' "$value" | sha256sum | cut -c1-16
  else
    echo "$name <unset>"
  fi
done
```

## PostgreSQL

Use the same environment and credentials as FastAPI; the query prints no
password:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select current_database(), current_schema(), inet_server_addr(), inet_server_port(), pg_is_in_recovery();" \
  -c "show transaction_isolation;" \
  -c "select table_name from information_schema.tables where table_schema=current_schema() and table_name in ('collections','documents','chunks','embeddings','chunk_versions','knowledge_document_revisions','queries','chat_sessions') order by 1;" \
  -c "select count(*) as chunks, max(updated_at) as latest_chunk_update from chunks;"
```

Verify `pg_is_in_recovery()` is false for the writer. Confirm the updater and
retrieval process resolve to the same host, port, database, and schema. Check
that there is exactly one embedding per tested chunk and that the production
schema has the columns used by the handler:

```bash
psql -X -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select table_name,column_name,data_type from information_schema.columns where table_name in ('chunks','embeddings','chunk_versions') order by table_name,ordinal_position;"
```

## Qdrant

Run from the FastAPI namespace. This uses the configured client and prints no
API key:

```bash
python3 - <<'PY'
import os
from qdrant_client import QdrantClient
client = QdrantClient(
    host=os.environ['QDRANT_HOST'],
    port=int(os.getenv('QDRANT_PORT', '6333')),
    api_key=os.getenv('QDRANT_API_KEY'),
    https=os.getenv('QDRANT_HTTPS', 'false').lower() == 'true',
)
name = os.environ['QDRANT_COLLECTION']
info = client.get_collection(name)
print({'collection': name, 'points_count': info.points_count, 'status': str(info.status)})
PY
```

Compare host, port, HTTPS mode, collection name, Qdrant server version,
collection status, vector dimension, distance, and point count. Ensure updater
and retriever use the same collection. Qdrant's documented `wait=true` behavior
is necessary for immediate visibility; do not replace it with sleeps.

## MinIO

MinIO is not part of the live edit/read path, but application startup currently
requires it. Perform only bucket existence/listing checks:

```bash
python3 - <<'PY'
import os
from minio import Minio
client = Minio(
    os.environ['MINIO_ENDPOINT'],
    access_key=os.environ['MINIO_ACCESS_KEY'],
    secret_key=os.environ['MINIO_SECRET_KEY'],
    secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true',
)
bucket = os.environ['MINIO_BUCKET']
print({'bucket': bucket, 'exists': client.bucket_exists(bucket)})
PY
```

Compare endpoint, bucket, prefix, TLS, credentials version, and network access.
Do not overwrite an object to diagnose an answer edit.

## Filesystem and ignored artifacts

```bash
data_root="${DATA_INSERTION_DIRECTORY:-$PWD/data_insertion_chunks}"
find "$data_root" -maxdepth 3 -printf '%M %u:%g %y %p\n' | sort
git check-ignore -v "$data_root"/DOCUMENTS/* "$data_root"/CHUNKS/General_FAQ/* 2>/dev/null || true
findmnt -T "$data_root" || true
```

Compare the absolute resolved path, existence, owner/group, mode, mount source,
read-only flag, and provisioning process. Missing ignored source/chunk files
affect ingestion/reset but not an already-ingested live edit.

## Processes, Docker, and networking

```bash
ss -ltnp
docker ps --no-trunc --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.Networks}}'
docker inspect APP_CONTAINER --format '{{json .Config.Cmd}} {{json .Config.Entrypoint}} {{json .Mounts}} {{json .NetworkSettings.Networks}}'
docker inspect POSTGRES_CONTAINER QDRANT_CONTAINER MINIO_CONTAINER --format '{{.Name}} {{json .NetworkSettings.Networks}} {{json .NetworkSettings.Ports}}'
```

Check for old processes, multiple releases behind a load balancer, differing
environment files, restart policy, mounts, DNS aliases, firewalls, and the
meaning of `localhost`. Inside an app container, `localhost:6333` refers to that
app container, not a Qdrant sibling.

## Cache and update correlation

Search logs by the returned `knowledge_update_id`:

```bash
journalctl -u YOUR_APP_UNIT --since '30 minutes ago' --no-pager | grep 'KNOWLEDGE_UPDATE_ID_FROM_RESPONSE'
docker logs APP_CONTAINER --since 30m 2>&1 | grep 'KNOWLEDGE_UPDATE_ID_FROM_RESPONSE'
```

Expected ordered events are `UPDATE_RECEIVED`, `POSTGRES_STAGED`,
`QDRANT_UPDATED`, `POSTGRES_UPDATED`, `READ_AFTER_WRITE_VERIFIED`,
`CACHE_INVALIDATED`, and `UPDATE_COMPLETED`. Compare worker PID, database name,
collection, stage duration, and result. No answer text should appear in logs;
use the SHA-256 fingerprint.

## Approved isolated write test

The bundled write mode is deliberately refused unless explicitly confirmed,
and remains disabled until DevOps provisions a dedicated test database schema,
Qdrant collection, MinIO prefix, and synthetic document:

```bash
bash scripts/diagnose_knowledge_update_production.sh --synthetic-write-test --confirm-synthetic-write
```

After provisioning, run the application against only that isolated namespace.
Create the Persian synthetic FAQ, retrieve old, call the same update API,
retrieve from a new HTTP connection, inspect a new PostgreSQL connection and a
new Qdrant client, perform 20 revisions plus a concurrent pair, then delete only
the synthetic records. Never aim this procedure at a banking collection merely
because the text is synthetic.

## Values that must match

| Area | Development versus production |
|---|---|
| Application | SHA, image digest, Python, package lock, startup command, worker count, CWD, service user |
| PostgreSQL | DNS/IP, port, DB, schema, primary/read-only state, tables/columns, credential version |
| Qdrant | DNS/IP, port/TLS, server/client version, collection, dimension/distance, credential version |
| MinIO | DNS/IP, port/TLS, bucket, prefix, credential version |
| Files | resolved data root, mount, owner/group/mode, provisioned source/chunks |
| Network | container network/DNS, published ports, firewall, proxy/load-balancer targets |
| Cache | worker count, revision query visibility, any external Redis/proxy/browser cache |

Do not classify the environment as the cause until this comparison and the
isolated write/read test both produce evidence.
