# Data Directory Layout

## Clone-time structure

```text
data_insertion_chunks/
├── DOCUMENTS/
│   └── .gitkeep
└── CHUNKS/
    └── General_FAQ/
        └── .gitkeep

benchmarks/
└── results/
    └── .gitkeep
```

Git does not track directories, so `.gitkeep` preserves only the directory
contract. It has no runtime behavior. `General_FAQ` is the only intentional
chunk category currently evidenced by the application and working tree.

## Local knowledge-base data

Users must supply their own approved documents below
`data_insertion_chunks/DOCUMENTS/`. Real FAQ sources, PDFs, spreadsheets, and
other knowledge-base material are private and never belong in the public Git
repository.

The chunking workflow writes derivatives below
`data_insertion_chunks/CHUNKS/<category>/`. Generated text chunks and embeddings
remain local even when the source document is safe. For the current category,
the expected local relationship is:

```text
data_insertion_chunks/DOCUMENTS/General_FAQ.csv
data_insertion_chunks/CHUNKS/General_FAQ/
```

The public tree contains neither the CSV nor generated chunk text.

## Runtime and result data

Qdrant vectors/snapshots, MinIO objects, PostgreSQL data, uploads, downloads,
mass-answer output, service logs, and Docker volume contents remain local in
their ignored directories. Raw benchmark results remain under
`benchmarks/results/`; only its `.gitkeep` is public.

Model servers run externally. vLLM serves generation and Hugging Face TEI serves
embedding/reranking; their model caches and downloaded binaries are not part of
this repository.

## Recreate required directories

```bash
mkdir -p \
  data_insertion_chunks/DOCUMENTS \
  data_insertion_chunks/CHUNKS/General_FAQ \
  benchmarks/results
```

These commands create directories only. They do not generate, ingest, upload,
or delete data.

Before any non-production ingestion, review the local documents, generated
chunks, environment destinations, and service endpoints. Never run insertion
from this staging repository against production.
