# Release evaluation runbook (Gate C)

The branch changes production ranking. This runbook produces the retrieval and answer-quality evidence that Gate C requires. It runs on **staging only**. Both tools refuse to start unless `ENVIRONMENT=staging` and `QDRANT_HOST`, `POSTGRES_HOST`, `TEI_EMBED_URL`, `TEI_RERANK_URL` and `VLLM_URL` equal this checkout's `.env` values and point to loopback. A refusal prints `staging guard: refused (KEY)` and exits 3.

Tools:

- `scripts/retrieval_eval.py` with `freeze`, `run`, `label-sheet` and `compare`.
- `scripts/answer_quality_eval.py` with `collect`, `blind` and `score`.

## Data handling

- **Private directories.** Questions, answers, chunk IDs, titles, label sheets, grading sheets and keys go only into owner-only directories (mode `0700`) outside the repository. The tools refuse anything else and write files with mode `0600`. They never overwrite an existing output.
- **The repository** receives only the two aggregate reports under `docs/performance/`: counts, rates, intervals and latencies.
- **The terminal** shows counts and fixed status lines only. Don't paste private files into tickets, chats or logs.
- **Retention.** Delete the private directory once the release decision is recorded, unless the data owner says otherwise.

Run every command from `/root/projects/faq` on `knowledge-gap-audit`, through `conda run --no-capture-output -n faq`. The examples use `E=/root/release-eval`:

```bash
E=/root/release-eval
install -d -m 700 "$E"
PY="conda run --no-capture-output -n faq python"
```

## 1. Worktrees for the five configurations

| Label | Commit | Change |
|---|---|---|
| `baseline` | `681cc95` | `main` |
| `p1` | `c833805` | An absent retrieval branch adds 0 to RRF scoring. |
| `p2` | `d45ddf6` | Lexical and dense depths are request-local and configurable. |
| `p3` | `e15761f` | Batched TEI reranking with merged global scores. |
| `rc` | tip of `knowledge-gap-audit` | Release candidate. |

```bash
git fetch origin
install -d -m 700 "$E/wt"
git worktree add --detach "$E/wt/baseline" 681cc95
git worktree add --detach "$E/wt/p1" c833805
git worktree add --detach "$E/wt/p2" d45ddf6
git worktree add --detach "$E/wt/p3" e15761f
git worktree add --detach "$E/wt/rc" origin/knowledge-gap-audit
git -C "$E/wt/rc" rev-parse HEAD   # record this hash as rc
```

`run` refuses a worktree with uncommitted changes. It also exits 2 if `git diff 681cc95 HEAD -- main.py` in the worktree touches the `RAGSystem(` call in `lifespan`, because then one driver can no longer build that configuration as the application does.

`e15761f` predates the reranker capability hardening, so it may fail closed against the staging reranker. Its `run` then ends with `status=failed`, or with an error count equal to the case count. If that happens, record it in the release log and leave `p3` out. `compare` then lists `baseline p1 p2 rc`, so `rc` is compared with `p2` directly.

## 2. Retrieval question set

1. **Select the questions.** Take 150 to 300 FAQ questions from `Eval_System_Test.csv`. Stratify by its category column (`دسته بندی`) and include fee, limit and duration questions.
2. **Save them privately.** Write them as a UTF-8 CSV with the columns `question_id` and `question` to `$E/input/retrieval-questions.csv`, with `$E/input` at mode `0700`.
3. **Freeze the queries:**

   ```bash
   $PY scripts/retrieval_eval.py freeze --questions "$E/input/retrieval-questions.csv" --output "$E/cases"
   ```

`freeze` builds each case's retrieval query exactly as `answering_service.py` does for a first-turn `general` question on this checkout: Parsivar normalization (`PersianTextProcessor(use_stemming=False).normalize`), `normalize_persian_text`, then `canonicalize_retrieval_query`. It writes `query_rule: "general_canonical"`. Every configuration receives the identical query string, so the only variable is the ranking code. The normalizer, the canonicalizer and the alias file are unchanged between `681cc95` and the tip.

## 3. Retrieval runs, labels and comparison

1. **Prepare the host.** The host must be otherwise idle: no load tests, no coverage audit runs and no other GPU jobs. Check `uptime` and `nvidia-smi` before each run.
2. **Freeze the knowledge base.** Make no edits between the first run and the last. If an edit happens, repeat every run.
3. **Run each configuration once, one after another:**

   ```bash
   DOCS="<the FAQ datasource title>"
   for label in baseline p1 p2 p3 rc; do
     $PY scripts/retrieval_eval.py run --repo "$E/wt/$label" --cases "$E/cases" \
       --label "$label" --documents "$DOCS" --output "$E/runs"
   done
   ```

   Each run starts a child process in the worktree with that worktree's own code. The child builds `RAGSystem` as `main.py` `lifespan` does, but skips `init_db`, authentication, OCR, the intent classifier and the agent services. It then reproduces the production context selection for each case in turn:

   - `retrieve` with `rag_retrieval_top_k`;
   - `rerank_search_results` when `rag_context_rerank_enabled`;
   - the whole reranked list for an `FAQ` datasource, else the first 3.

   It records the ordered retrieved, reranked and context IDs and the retrieval-plus-reranking latency. A case that raises records only its exception class name. `run.json` holds the worktree commit, the `rag_*` and `tei_rerank_*` settings, the datasource, and the case and error counts.

4. **Build the label sheet:**

   ```bash
   $PY scripts/retrieval_eval.py label-sheet --cases "$E/cases" \
     --runs "$E/runs/baseline" "$E/runs/p1" "$E/runs/p2" "$E/runs/p3" "$E/runs/rc" --output "$E/labels"
   ```

5. **Label it.** For each question, the sheet lists the union of every run's retrieved and context chunks once, with no indication of which configuration returned them. A person who knows the FAQ puts `1` in `relevant` for every chunk that answers the question and leaves the cell empty otherwise. Save the labeled copy as `$E/labels/label-sheet-labeled.csv`. Questions with no relevant chunk are counted in the report and excluded from the rates.

6. **Compare:**

   ```bash
   $PY scripts/retrieval_eval.py compare --cases "$E/cases" --sheet "$E/labels/label-sheet-labeled.csv" \
     --runs "$E/runs/baseline" "$E/runs/p1" "$E/runs/p2" "$E/runs/p3" "$E/runs/rc" \
     --baseline baseline --report docs/performance/release-retrieval-evaluation.md
   ```

   **Metrics per question.** `hit_context`, `recall_context`, `mrr_context`, `recall_retrieved` (before reranking), `empty` and `latency_ms`. A failed case counts as an empty context.

   **Comparisons.** Each configuration is compared with the baseline and with the configuration listed just before it, so each step changes one variable. The paired differences of `hit_context`, `recall_context` and `mrr_context` get 95% percentile bootstrap intervals: 10,000 resamples with `random.Random(1234)`. p50 and p95 latency and their deltas are reported too.

   **Verdict against the baseline.** The defaults are below; each is a flag.

   | Flag | Default | Rule |
   |---|---|---|
   | `--min-hit-diff` | `-0.02` | Lower bound of the `hit_context` difference is at least this. |
   | `--min-recall-diff` | `-0.02` | Lower bound of the `recall_context` difference is at least this. |
   | `--max-p95-ms` | `45000` | p95 latency is at most this. |
   | `--max-p95-ratio` | `1.2` | p95 latency is at most this multiple of the baseline's p95. |

   `compare` exits 0 when every configuration passes, else 1.

## 4. Answer quality (blind)

1. **Pick the questions.** Take 50 to 100 of the same questions. Save their `question_id,question` rows as `$E/input/answer-questions.csv` and freeze them:

   ```bash
   $PY scripts/retrieval_eval.py freeze --questions "$E/input/answer-questions.csv" --output "$E/answer-cases"
   ```

2. **Start `baseline` as a staging app instance on loopback.** The worktree has no `.env`, so export this checkout's staging environment into the process. Wait until `GET /api/health` reports ready.

   ```bash
   cd "$E/wt/baseline"
   conda run --no-capture-output -n faq python -c 'import dotenv, os, sys; dotenv.load_dotenv("/root/projects/faq/.env"); os.execvp("uvicorn", ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8101"])'
   ```

   Start `rc` the same way from `$E/wt/rc` on port `8102`. Both instances use the same staging vLLM, TEI, Qdrant and PostgreSQL. If GPU memory doesn't allow both at once (the intent classifier loads in each instance), run them one at a time: collect from `baseline`, stop it, then start `rc`.

3. **Collect each instance's answers, one at a time:**

   ```bash
   $PY scripts/answer_quality_eval.py collect --base-url http://127.0.0.1:8101 --label baseline \
     --cases "$E/answer-cases" --documents "$DOCS" --identities "$E/input/staging-identities.json" --output "$E/answers"
   $PY scripts/answer_quality_eval.py collect --base-url http://127.0.0.1:8102 --label rc \
     --cases "$E/answer-cases" --documents "$DOCS" --identities "$E/input/staging-identities.json" --output "$E/answers"
   ```

   `--base-url` must be loopback. `--identities` is the operator-reserved staging identity fixture of the load test, read with the loader in `benchmarks/load/mobile_talk_load_test.py`. Never invent national codes.

   Each case is sent once, in sequence, as `POST /api/mobile/v1/talk` with:

   - a new session ID;
   - the original question;
   - the datasource;
   - a 50-second timeout.

   Each request creates staging chat sessions for the reserved identities.

4. **Blind the answers:**

   ```bash
   $PY scripts/answer_quality_eval.py blind --a "$E/answers/baseline" --b "$E/answers/rc" --seed <N> --output "$E/blind"
   ```

   `--a` must be the baseline and `--b` the release candidate. The order of the two answers is random per item, from the seed. The mapping is written only to `grading-key.json`.

5. **Grade.** Give the grader only `grading-sheet.csv`, and never the key. The grader must not have seen it. For every item they fill in:

   - `correct_1` and `correct_2`: `correct`, `partly` or `incorrect`;
   - `grounded_1` and `grounded_2`: `yes` or `no`, meaning every claim is supported by the FAQ;
   - `preference`: `1`, `2` or `same`.

   `[no answer]` marks a request that returned no answer; grade it `incorrect` and not grounded.

6. **Score:**

   ```bash
   $PY scripts/answer_quality_eval.py score --sheet "$E/blind/grading-sheet-graded.csv" --key "$E/blind/grading-key.json" \
     --report docs/performance/release-answer-quality.md
   ```

   The report gives, per configuration:

   - the correct, partly and incorrect rates;
   - the grounded rate;
   - the preference counts;
   - a two-sided exact sign test on the preferences, excluding `same`.

   The release candidate passes unless the sign test favors the baseline at p < `--alpha` (default `0.05`), or its `incorrect` count exceeds the baseline's by more than `--max-extra-incorrect` (default `2`). `score` exits 0 on pass, else 1.

## 5. Gate C (production release)

Production release requires all three:

1. `release-retrieval-evaluation.md` reports **PASS**.
2. `release-answer-quality.md` reports **PASS**.
3. **L6.** The production reranker's `--max-client-batch-size`, read from its deployment configuration by the owner of that deployment, is at least the production `TEI_RERANK_MAX_CLIENT_BATCH_SIZE`. Don't query production from staging to find it.

Record the two report paths, the five commit hashes, the label count, the grader and the L6 value in the release log. Then remove the worktrees with `git worktree remove "$E/wt/<label>"`.
