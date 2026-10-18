# Run-to-run stability protocol (L2)

This runbook tests whether the coverage audit's verdict for one row depends on the batch size. It is for the staging operator, and it runs on staging only. Never run it against production.

## Why

Two pilot rows changed verdict between runs:

| Row | A2 source row ID | Earlier verdicts |
|---|---|---|
| 121 | `row_dedce881f722f95251e3f326f002f465` | `possible_partial_gap` in A2 (300 entries, batch size 5); `covered_reachable` in A2.2 (batch size 2) |
| 518 | `row_db3be7cdd0b505a4def0a73355236a6f` | `covered_not_reachable` in A2.1; a schema error in A2.2 |

Those runs also changed the rubric and the code, so they cannot show that batch size caused the change. This protocol changes batch size only.

Since step 08 every accepted proof is verified a second time with its evidence in reversed order (`KNOWLEDGE_COVERAGE_VERIFICATION_PASSES=2`). That removes one source of order dependence inside a single verification. Batch size changes which entries the model sees together, which this protocol measures.

## Fixed inputs

Keep these the same for all 12 runs:

- **Snapshot.** One staging KB snapshot captured after step 05. Record its `snapshot_id`.
- **Commit.** One commit of `knowledge-gap-audit`, at or after step 08. Do not pull, edit or switch branches between runs.
- **Dataset.** The same imported dataset, with the same `dataset_id`.
- **Rows.** Rows 121 and 518 above, in every run.
- **Entry budget.** One explicit `--entry-budget` value, the same in every run.
- **Every other setting.** Change only `KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES`. The stability report refuses runs whose settings differ in any other key (`code_version_mismatch`).

## Runs

Run three pilot runs of both rows at each batch size: 1, 2, 3 and 5. That is 12 runs.

For each batch size, in this order:

1. Set `KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES` to the value in the staging `.env`. Do not print the file.
2. Restart FastAPI. The value is part of each run's pinned settings manifest, and a run whose pinned settings differ from the running settings refuses to start or resume (`audit_runtime_identity_drift`).
3. Start three runs, one after another. Wait for each to finish before starting the next.

```bash
conda run --no-capture-output -n faq python scripts/knowledge_coverage_pilot.py --owner-id OWNER pilot \
  --dataset-id DATASET_ID --snapshot-id SNAPSHOT_ID \
  --row-ids row_dedce881f722f95251e3f326f002f465 row_db3be7cdd0b505a4def0a73355236a6f \
  --entry-budget BUDGET --confirmed-staging
```

- `OWNER` is `0` for the operator namespace. The human check below needs the runs on the coverage page, which shows only runs owned by a real web user, so use that person's user ID if they will review there.
- Use the same `OWNER` for every run. The stability report reads runs from one owner.
- Record each run's `run_id`, printed on the first output line, next to its batch size.
- Each run must end in state `completed`. A run that does not complete is not used; start a replacement at the same batch size.

## Report

Run the read-only stability report over all 12 runs, then once per batch size over its 3 runs. Each report needs its own new output directory outside the repository, and it refuses to overwrite one.

```bash
conda run --no-capture-output -n faq python scripts/knowledge_coverage_stability_report.py --owner-id OWNER \
  --run-id RUN_1 --run-id RUN_2 ... --run-id RUN_12 \
  --row-id row_dedce881f722f95251e3f326f002f465 --row-id row_db3be7cdd0b505a4def0a73355236a6f \
  --output /root/projects/faq-private/stability/all-12
```

Repeat with the 3 run IDs of each batch size, writing to `.../batch-1`, `.../batch-2`, `.../batch-3` and `.../batch-5`.

The report never calls a model or a service. It writes `stability-report.json` and `stability-report.md`, both mode `0600`. They contain identifiers, labels and counts only: no query, aspect, sentence or explanation text.

For each row it reports:

- `aspect_checklist_agreement`: every run produced the same aspect checklist in the same order. When it fails, aspect IDs mean different things across runs.
- `verdict_agreement`: every run has the same outcome.
- The minimum and mean pairwise Jaccard similarity of the `(entry_id, aspect_id, applicability)` support triples. `support_agreement_pass` needs a minimum of at least 0.9.
- **Row passes** when all three are true.

Exit codes: `0` every row passes, `1` a row fails, `2` refused. A refusal prints only its code:

| Code | Meaning |
|---|---|
| `snapshot_mismatch` | The runs do not share one snapshot and one dataset. |
| `code_version_mismatch` | The runs' code versions differ, or their settings differ in a key other than batch size. |
| `run_not_completed` | A run is missing, owned by someone else, or not completed. |
| `row_missing` | A row was not selected in a run, or was not evaluated. |

## Human check

A person opens row 121 on the coverage page (`/knowledge-coverage`) for at least one run at each batch size whose outcome differs. They read its cited sentences against its requested aspects and record, for each outcome seen, whether it is right. Record the reading and the run IDs, not the text.

## Decision rule

- **Every row passes at every batch size.** Keep the current `KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES`.
- **A row fails.** Pin `KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES` to the value whose verdict matches the human reading. Set it in all five env files: `.env`, `env.example`, `.env.example.generated`, `Production_ENV` and `Production_ENV.example`. Then repeat the experiment at that value: three runs, and a report that passes.
- **Gate B**, the full run, requires a pass.

## Cost

Two verification passes add about one verification call per accepted proof. Rows with no accepted proof add nothing. On the staging runs recorded before step 08, a verification call used 1,270–2,969 prompt tokens (median 2,010) and at most 152 completion tokens; see the `[08]` entry in `READINESS_FIX_LOG.md`. A2's row 121 used 64 calls at batch size 5, so the extra verification is small next to the batch calls. Smaller batch sizes mean more batch calls per row.
