# Sizing a full or subset coverage run

Before a full-input or subset run starts, the knowledge coverage page shows what the run is likely to cost next to its limits. This page explains where that estimate comes from and what to do when it does not fit. It is for the staging operator. Pilot runs (five questions or fewer) are not sized.

## Why

One hard question can be expensive. In the A2 pilot, row 121 used 64 completions, 175,552 prompt tokens and 259 seconds, and since step 08 every accepted proof costs one more verification call. The default limits are 200 completions, 1,000,000 tokens and 3,600 seconds, which is about one or two such rows. A 918-row input needs far more, so a run started with the defaults pauses early.

## 1. Run a pilot first

The estimate is built from **completed** runs of the same setup. Without one, the page says "No reference runs on this snapshot" and the run can start only after you tick "I confirm an unsized run".

Run a 5-row pilot on the target snapshot and dataset, either:

- **from the page:** keep "Pilot · up to five questions" as the execution scope, select five questions and start; or
- **from the command line:** `scripts/knowledge_coverage_pilot.py pilot --dataset-id ... --snapshot-id ... --confirmed-staging` with `--owner-id` set to **your web user ID**. References are per owner: a pilot under operator namespace 0 is not a reference for a run you start on the page.

Let the pilot finish. Only runs in state `completed` count, and only their finished rows. At least 5 finished rows across the reference runs are needed. Pick pilot questions that look like the input: the estimate weights each outcome class by its share in the references.

### What counts as the same setup

A completed run is a reference when it has:

- the same snapshot and the same dataset;
- the same code and prompts (`versions`: `prompts`, `code`, `code_id`);
- the same audit settings: datasources, entry budget, batch size, verification passes and every other setting.

Two things may differ:

- **Limits** (`operational_limits`), because they only cap a run.
- **Selection method**, because a pilot and a full run select rows differently.

So run the pilot with the datasources and entry budget you will use for the full run. The page selects every datasource by default, which matches the command line.

## 2. Read the estimate

The table has one row each for completions, tokens and hours, with three columns:

| Column | Meaning |
|---|---|
| Limit | The run's limit: completion attempts, reserved/used tokens, execution seconds shown as hours. |
| Expected | Questions × the reference **mean** per question, weighted by outcome class. |
| High | Questions × the reference **90th percentile** per question, weighted the same way. |

The classes are covered (`covered_reachable`, `covered_not_reachable`), non-covered (`possible_gap`, `possible_partial_gap`, `needs_review`) and other. Non-covered questions are usually the expensive ones, because the audit searches further before it gives up. Completions and tokens come from the reference runs' budget ledgers. A connection that was refused (`not_sent`) is not counted. Hours come from each row's recorded duration.

Cells over the limit are marked "over limit". If **Expected** is over any limit, the run will pause before finishing, and it can start only after you tick "I accept that this run will pause before finishing". A run that pauses keeps its finished rows; the remaining rows stay pending, and exhausted allowance requires a new run.

The estimate shown when the run starts is saved in the run's metadata under `sizing`. It is an estimate from a small sample, not a promise.

## 3. Raise the limits

The page can lower the limits for one run, but never raise them above the configured allowance. To raise the allowance, set these in the staging `.env` and restart FastAPI:

| Variable | Default | Validated maximum |
|---|---:|---:|
| `KNOWLEDGE_COVERAGE_MAX_COMPLETIONS` | 200 | 100,000 |
| `KNOWLEDGE_COVERAGE_MAX_TOKENS` | 1,000,000 | 1,000,000,000 |
| `KNOWLEDGE_COVERAGE_MAX_EXECUTION_SECONDS` | 3,600 | 604,800 (7 days) |

Use the **High** column to choose values when the run must not pause. Check the result with `scripts/validate_environment.py --env-file .env --mode staging`.

## 4. Very large inputs

One run is capped at 7 days of execution. An input whose estimate is over 168 hours cannot finish in one run, even at the maximum limits. It needs the continuation from step 11.
