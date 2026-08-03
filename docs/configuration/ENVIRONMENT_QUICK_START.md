# RagBot environment quick start

This guide is for a developer or operator who has not worked with environment
files before. It never asks you to print the whole `.env`.

## What an environment variable is

An environment variable is a named setting given to a program. For example:

```dotenv
API_PORT=8080
```

The name is `API_PORT`; its value tells the direct RagBot server which network
port to use.

A `.env` file is a convenient text file containing many of these assignments.
This repository's live local file is:

```text
/root/projects/faq/.env
```

Treat it as sensitive. It can contain passwords, API keys, internal addresses,
and storage credentials. Do not paste it into chat, tickets, logs, or commits.

## How RagBot reads the file

`main.py` and several supporting modules call `load_dotenv()`. When you start
RagBot from this repository, it finds `.env` and loads variables that are not
already exported by the shell.

The practical order is:

1. A value already exported in the process environment wins.
2. `.env` fills in a missing value.
3. Code uses its own default if the variable is still missing.
4. A required value with no default may fail at startup or during the first
   request.

Most values are read only once during Python import/startup. Editing `.env`
does not update a running process.

## Edit safely

Before editing:

```bash
cd /root/projects/faq
umask 077
install -m 600 .env /tmp/ragbot-env.backup
```

The backup contains secrets. Keep it only as long as needed and never add it to
Git.

Edit one setting at a time with your normal editor. A valid basic line is:

```dotenv
NAME=value
```

Important syntax rules:

- Use one assignment per line.
- Names may contain letters, numbers, and `_`, but may not start with a number.
- Do not put spaces in the name.
- Avoid spaces around `=`. Python dotenv accepts some spaces, but shell tools
  and other runtimes may not.
- Use `#` at the start of a line for a comment.
- Quotes are useful when a value contains spaces or `#`:

```dotenv
DISPLAY_LABEL="staging chatbot #2"
```

- Matching single quotes preserve text literally. Double quotes can interpret
  escapes such as `\n`.
- Never add quotes merely by copying shell syntax you do not understand.
- Do not include credentials inside a URL such as
  `https://user:password@example.com`.

After editing, validate before restart:

```bash
python3 scripts/validate_environment.py \
  --env-file .env \
  --mode staging \
  --show-optional \
  --format text
```

The validator prints names and classifications such as `set`, `missing`, or
`malformed`. It never prints values.

## Host, port, endpoint, and URL

A **host** identifies a machine or container:

```dotenv
QDRANT_HOST=localhost
```

A **port** identifies one network service on that host:

```dotenv
QDRANT_PORT=6333
```

An **endpoint** may be a host and port without a scheme:

```dotenv
MINIO_ENDPOINT=localhost:9000
```

A **URL** includes the protocol:

```dotenv
TEI_EMBED_URL=http://127.0.0.1:7997
```

These forms are not interchangeable unless code explicitly supports both.
RagBot uses a complete URL for TEI and vLLM. Active Qdrant code uses
`QDRANT_HOST`, `QDRANT_PORT`, and `QDRANT_HTTPS`; it ignores `QDRANT_URL`.

`localhost` always means “the same network namespace as this process.” From a
program running directly on a host, it means that host. From inside a Docker
container, it means that container—not the host and not a neighboring
container. Containers normally reach each other through a Docker service name.

## Staging and production are different

Staging is for controlled testing with synthetic data. Production handles real
service traffic and must use production-approved credentials, TLS, databases,
buckets, models, and network addresses.

Do not copy staging `.env` into production. Do not run load tests against
production. The current `ENVIRONMENT` variable is only a label: application
code does not use it as a safety switch.

This repository does not contain Docker Compose, Kubernetes, systemd, vLLM, or
TEI startup definitions. An operator must verify those external deployments
separately. In particular, `.env` does not configure vLLM `max_num_seqs` or
TEI server admission limits.

## The important setting groups

### Timeouts

- `APPLICATION_REQUEST_TIMEOUT_SECONDS` is the entire FastAPI operation
  deadline and cannot exceed 50 seconds.
- `REQUEST_ADMISSION_TIMEOUT_SECONDS` is how long a request may wait for an
  application processing slot.
- `TEI_HTTP_*_TIMEOUT_SECONDS` limits individual embedding/reranking client
  phases.
- `VLLM_HTTP_*_TIMEOUT_SECONDS` limits individual generation client phases.

These timers can overlap; they are not added into a larger entitlement. A
downstream timeout should normally be below the total endpoint deadline so
there is time left for queueing, database work, and returning the response.

### Concurrency

- `REQUEST_CONCURRENCY_LIMIT` limits admitted application operations.
- `BLOCKING_CONCURRENCY_LIMIT` limits synchronous jobs offloaded from async
  request code.
- `TEI_HTTP_MAX_CONNECTIONS` and `VLLM_HTTP_MAX_CONNECTIONS` limit outgoing
  client sockets.
- `QDRANT_CONCURRENCY` limits concurrent vector calls.

The TEI and vLLM servers also have their own external queues. Setting every
number to 50 does not guarantee that 50 requests finish quickly. It can instead
create longer queues and GPU contention.

### Embeddings and vectors

The current retrieval policy expects 1024-dimensional vectors and cosine
distance. Query embedding uses `prompt_name="query"`; stored document embedding
uses raw document semantics. Keep `QDRANT_VECTOR_SIZE=1024` unless a planned
migration rebuilds the collection and passes retrieval and answer-quality
tests.

The documented staging endpoints use embedding port 7997 and reranker port
7998. Swapping them causes protocol failures.

### Database setup versus application database

`POSTGRES_*` describes the target database used by RagBot.
`DEFAULT_DB_*` is a separate administrative connection used only by
`new_architecture/setup_dbs.py` to create the target. Neither group overrides
the other.

## Starting and restarting

The simplest repository-defined start is:

```bash
cd /root/projects/faq
python3 main.py
```

Importing `main:app` through an external ASGI command also loads `.env`, but
that command is deployment-specific and is not defined by this repository.

After a change:

- Restart FastAPI for application, PostgreSQL target, Qdrant, MinIO client,
  service URL, timeout, concurrency, retrieval, or generation settings.
- Rerun only the insertion/setup/load-test command for command-only settings.
- Restart vLLM only when its own external server configuration changes.
- Restart TEI embedding/reranker only when their own external server
  configuration changes.
- Restart PostgreSQL, Qdrant, or MinIO only when changing those servers'
  configuration—not merely because their client address changed in `.env`.

The actual service-manager commands are unknown because this repository has no
Compose, Kubernetes, systemd, or service scripts. Use the deployment runbook;
do not guess on production.

## Verify configuration without revealing secrets

### 1. Check required variables and status

```bash
python3 scripts/validate_environment.py \
  --env-file .env \
  --mode staging \
  --format text
```

For production review:

```bash
python3 scripts/validate_environment.py \
  --env-file .env \
  --mode production \
  --format text
```

### 2. Validate dotenv syntax and types

The same command checks assignment syntax, quotes, integers, floats, booleans,
URLs, ranges, and important cross-field relationships. A critical problem exits
with code 2:

```bash
python3 scripts/validate_environment.py \
  --env-file .env \
  --mode staging \
  --format json
echo "$?"
```

The JSON contains no values.

### 3. Compare current names with the generated template

This prints names only:

```bash
comm -3 \
  <(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/{gsub(/[[:space:]]/, "", $1); print $1}' .env | sort -u) \
  <(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/{gsub(/[[:space:]]/, "", $1); print $1}' .env.example.generated | sort -u)
```

Left-only names are present only in `.env`; right-only names are absent from
`.env`.

### 4. Find Python-referenced names missing from `.env`

This is a lightweight discovery check; the validator is authoritative because
some settings use helper functions:

```bash
comm -23 \
  <(rg -U -o --no-filename --glob '*.py' 'os\.getenv\(\s*"[A-Z][A-Z0-9_]*"' . \
    | sed -E 's/.*"([A-Z][A-Z0-9_]*)"$/\1/' | sort -u) \
  <(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/{gsub(/[[:space:]]/, "", $1); print $1}' .env | sort -u)
```

### 5. Find current names with no direct repository reference

This conservative command prints a name only when no text reference exists
outside sensitive env files:

```bash
while IFS= read -r name; do
  if ! rg -q --hidden \
    --glob '!/.env' \
    --glob '!/.env.server_git' \
    --glob '!env.example' \
    --glob '!.env.example.generated' \
    --glob '!**/.git/**' \
    "$name" .; then
    printf '%s: unused\n' "$name"
  fi
done < <(
  awk -F= '/^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/{gsub(/[[:space:]]/, "", $1); print $1}' .env |
  sort -u
)
```

Text references can be comments or legacy code, so review the audit before
calling a variable active.

### 6. Verify the application process

After an authorized staging restart, use the non-secret health endpoint:

```bash
curl --fail --silent http://127.0.0.1:8080/api/health
```

Adjust only the public bind port. The response indicates startup readiness but
does not prove every downstream model request works.

### 7. Run the validator's synthetic tests

```bash
python3 -m unittest tests.test_validate_environment -v
```

These tests never read the real `.env`.

## Common mistakes

- Editing `.env` but not restarting FastAPI.
- Assuming `.gitignore` protects a file already tracked by Git.
- Swapping TEI embedding and reranking ports.
- Using `localhost` from inside a container to reach another container.
- Adding `http://` to `MINIO_ENDPOINT`, which expects `host:port`.
- Omitting `/v1` from the vLLM OpenAI-compatible base URL.
- Setting `QDRANT_URL` and expecting it to override the active split fields.
- Changing vector size without rebuilding compatible data.
- Setting keep-alive connections higher than maximum connections.
- Setting retrieval top-k higher than the candidate limit.
- Putting a real load-test token on the command line, where history/process
  tools can see it.
- Using `ENVIRONMENT=staging` as proof that a target is not production.

## Recover from an invalid change

1. Do not repeatedly restart a failing production service.
2. Run the validator and note only variable names/statuses.
3. Compare names with `.env.example.generated`.
4. Restore the secure backup if needed:

```bash
install -m 600 /tmp/ragbot-env.backup .env
```

5. Validate again.
6. Restart only the affected staging/service process using its approved
   runbook.
7. Delete the temporary backup through the approved secure-file procedure when
   recovery is complete.

If a credential was pasted into a log, ticket, chat, shell command, or Git
commit, removing the text is not enough. Notify the credential owner and rotate
it.

## Minimal startup checklist

- [ ] You are in `/root/projects/faq`.
- [ ] You know whether the target is staging or production.
- [ ] Required PostgreSQL, MinIO, TEI embedding, and TEI reranker variables
      report `set`.
- [ ] Secret variables are supplied from an approved source and are not printed.
- [ ] TEI embedding and reranker point to the correct distinct services.
- [ ] Vector size is 1024 for the current collection policy.
- [ ] The validator exits 0.
- [ ] The correct process is restarted through the deployment runbook.
- [ ] `/api/health` reports readiness.
