# NegahBoom Step 2: isolated platform prompts

> Historical report: platform restrictions and session binding described here are superseded by the [knowledge selection correction](KNOWLEDGE_SELECTION_CORRECTION_REPORT.md). Approved NegahBoom prompts remain in use.

## Scope and prompt selection

`negahboom_prompts.py` contains separate `GENERAL_RAG_SYSTEM_PROMPT`,
`CHITCHAT_SYSTEM_PROMPT`, and `QUERY_REWRITE_PROMPT` variants. Their structures
come from the existing Hibank templates. Platform-neutral general/chit-chat user
templates retain exactly the same bytes and placeholders. Answer roles remain
system/user; rewriting retains the existing helpful-assistant system role and
rewrite template in the user message, with the same `<rewrite>` output contract.

Both platforms keep the assistant name Hibot. NegahBoom introduces it exactly as:

> من Hibot هستم، دستیار هوشمند بانکداری باز

The approved company background is included verbatim in both answer system
prompts, restricted to company identity/about-us responses. NegahBoom is described
as serving businesses and organizations through digital services, including
banking APIs, and explicitly not as a bank. Service details require retrieved
NegahBoom context. The prompts prohibit invented capabilities, support promises,
and claims that operations actually occurred; they protect against instructions
embedded in retrieved content/history. Rewriting preserves API names, identifiers,
endpoint paths, versions, and English terms. Examples are hypothetical, not
capability claims.

Selected missing-information wording (also used for a service question reaching
the context-free chit-chat route):

> اطلاعات موردنیاز برای پاسخ به این پرسش در مستندات فعلی نگاه بوم موجود نیست.

Selected out-of-scope wording:

> من در زمینه خدمات دیجیتال و بانکداری باز نگاه بوم به کسب‌وکارها و سازمان‌ها کمک می‌کنم. لطفاً پرسش خود را در این زمینه مطرح کنید.

Normal substantive FAQ answers retain the `کاربر گرامی، ` prefix and Persian
plaintext structure. The introduction is not prepended to every answer. The
missing-information fallback makes no ticketing or support commitment.

## Minimal shared changes

- `agent_graph.py` reconstructs the immutable `PlatformContext` from the Step 1
  graph platform ID and passes it to the two answer calls. Legacy graph states
  lacking the ID retain Hibank compatibility. It recognizes NegahBoom's separate
  fallback for the existing `LLM_CONTEXT_REFUSAL` diagnostic; Hibank still uses
  the original fragment unchanged.
- `RAGSystem.answer` accepts optional keyword-only `platform_context` and selects
  a local prompt namespace. Omitted context retains the exact Hibank path.
  Explicit NegahBoom selects its own templates. Hibank-owned contract/circular
  categories with explicit NegahBoom fail closed rather than selecting Hibank
  document prompts. Step 1 ownership checks already prevent that combination.
- `HistoryRewritingService.rewrite_query` uses its already-passed context to
  select a local template. No-history handling, normalization, parsing, failure
  handling, generation parameters, and summary workflow remain unchanged.

Web, mobile, batch, and internal evaluation already share the Step 1 answering
and agent paths, so their HTTP entrypoints need no changes. Session-derived
platform binding and fixed/auto resolution are reused. Platform is never used as
a FAQ/document category. No shared Config or prompt global is mutated per request.
No API schemas, identifier validation, source ownership, model/retrieval settings,
service limits, persistence, setup, infrastructure, or private env files change.

## Preservation evidence

The original `new_architecture/app/config.py` is byte-identical to the baseline.
`tests/fixtures/step2_existing_prompt_hashes.json` freezes all eight original
Config prompt strings before implementation, including document/OCR/rewrite
prompts. Tests compare SHA-256 values without weakening prior fixtures or tests.
Existing answer-role golden checks continue to apply.

The snapshot audit compares nine untouched files byte-for-byte with Git HEAD:
Config, both coverage prompt modules, intent classifier, scenarios, FAQ fallback,
RAG utilities, answering service, and agent service. Existing workflow prompts
and Hibank fallback wording are unchanged. Fake-client tests compare actual
Hibank message lists against original template construction for default, FAQ,
chit-chat, contracts, and circulars, with/without explicit Hibank context.
Hibank rewriting messages also match the original template exactly.

## Offline verification

All commands use the existing `/root/miniconda3/envs/faq/bin` environment;
no dependencies were installed.

- Focused regression command: `python -m pytest -p tests.offline_guard
  tests/test_negahboom_prompts.py tests/test_rag_answer_prompt_roles.py
  tests/test_platform_context.py tests/test_p0_p1_repairs.py -q` — **65 passed,
  8 subtests passed**. This includes all 13 new prompt checks. It verifies actual
  fake-client messages, exact identity/background, both rewrite variants,
  concurrent requests sharing one RAG client, session-only follow-ups, fixed
  profiles/shared auto mode, FAQ output/related questions, and fail-closed
  NegahBoom/document selection. Existing platform tests cover web/mobile,
  evaluation transport, UUID races, ownership, and persistence checks.
- `PATH=/root/miniconda3/envs/faq/bin:$PATH bash scripts/run_offline_tests.sh`
  in the worktree — **977 passed, 26 deselected, 295 subtests passed**;
  all four Node frontend harnesses, frontend audit, and tracked-secret check
  passed (**0 matches**). There were 86 warnings, including existing datetime
  deprecations and unavailable NVML; no test failures.
- The same required script in a disposable snapshot — **977 passed,
  26 deselected, 295 subtests passed**; all frontend harnesses/audit passed.
  The snapshot has no private env files, so its secret scanner explicitly reports
  **NOT RUN (no local env files)**; the worktree scan above supplies that check.
- Snapshot completeness: copied the current contents of all `git ls-files`
  entries plus the four new deliverables (prompt module, test module, hash
  fixture, this report), preserving tracked symlinks; **699 files**. SHA-256
  manifests verify the snapshot matches intended sources. A disposable Git index
  makes new modules/tests visible to repository checks. No commits were created.
  Unrelated untracked benchmarks and `test.json` are excluded and untouched.
- `git diff --check`, new-file whitespace checks, and Python compilation of
  changed/new Python modules passed. Nine untouched files passed byte-equality
  checks against HEAD, as listed above.

Initial attempts are recorded separately: default `python` lacked pytest; the
existing `faq` environment resolved that without installation. One new test fake
initially lacked a reranking method and was corrected before the passing run.
Sandboxed full-suite attempts stalled at an unchanged admin TestClient test;
a 20-second traceback reproduced AnyIO's cross-thread portal wait. Those attempts
were interrupted and are **not passing runs**. The full successful checks ran
outside that sandbox with `tests.offline_guard` still blocking network/database
connections. Collection alone found 1003 tests; the required markers exclude 26.
The final NegahBoom-only company-background clarification and source whitespace
cleanup were followed by focused regression and final snapshot verification.

These checks exercise construction, routing, and transport to fake model clients.
They do not establish live model adherence, retrieval relevance, or answer quality.
No application startup, database/service access, setup, ingestion, migration,
deployment, commit, or push is part of this work.

## Remaining staging evaluation

Before release, run the staging-only retrieval and answer-quality workflow from
`docs/performance/RELEASE_EVALUATION_RUNBOOK.md`: freeze labelled platform-specific
retrieval datasets, compare retrieval results, collect answers, blind and score
human answer-quality grades. Include identity/about-us, greetings, mixed
service/greeting requests, missing/irrelevant context, prompt injection, exact API
identifiers/versions, unsupported service claims, and out-of-scope cases. Verify
Hibank equivalence and NegahBoom grounding independently. This live/human-labelled
verification is pending because this task authorizes synthetic offline checks only.
