# Answering-path parity audit

Baseline: `30385f23b0511a395bc25e0046d471d5461db1f4`. Line references describe that baseline. This report compares `POST /api/query`, `POST /api/mobile/v1/talk`, and `POST /api/mass-answer`; it does not propose identical HTTP response schemas.

## Path summary

- Web: wrapper admission/deadline → normalize/classify/history rewrite → persist user message → `AgentService.process_message` → LangGraph classifies again and routes → persist answer → expose related questions/feedback (`main.py:545-650`).
- Mobile: total deadline around admission and operation → provision user/resolve mobile session → classify/history rewrite → persist user message → same `AgentService`/LangGraph → persist answer → mobile response (`mobile_api.py:80-210`).
- Mass: admission/deadline around whole file → parse → for each row normalize/no-history rewrite/retrieve/context/answer directly → write file (`main.py:974-1118`).

## Behavior matrix

| Behavior | Web `/api/query` | Mobile `/api/mobile/v1/talk` | Mass `/api/mass-answer` | Classification |
|---|---|---|---|---|
| Query validation | Pydantic `str`; trimmed at `main.py:572`; no explicit empty rejection | Explicit truthy check at `mobile_api.py:103-105`; whitespace-only passes | No named required column; cell stringified at `main.py:1047-1054` | Missing behavior/correctness defect in web and mass |
| Query normalization | Parsivar normalization before rewrite (`main.py:572-586`); original is sent to graph | No wrapper normalization (`mobile_api.py:128-140`); retrieval later normalizes semantic text | Parsivar normalization becomes generation/retrieval query (`main.py:1050-1082`) | Accidental divergence |
| Authentication/user resolution | Route itself does not resolve auth; integer session is assumed (`main.py:570`, `589-627`) | No gateway auth dependency; national code can JIT-create user and UUID session (`mobile_api.py:103-126`) | No auth, user, or session | Intentional channel difference, with separate auth risks outside this repair |
| Intent classification | Wrapper classifies for rewrite (`main.py:573`), graph classifies original again (`agent_graph.py:86-112`) | Same duplicate classification (`mobile_api.py:128-140`; graph) | None | Missing behavior and performance defect; online duplicate call is obsolete/performance defect |
| Chit-chat route | Graph skips retrieval and uses chit-chat prompt/history (`agent_graph.py:191-217`) | Same | Always retrieval/general prompt | Missing behavior/correctness defect |
| History retrieval | Up to 3 turns from session metadata (`main.py:581-587`; `new_architecture/app/services/history/rewriting.py:81-142`) | Same through resolved internal session (`mobile_api.py:133-140`) | None; constant sentinel (`main.py:1061-1064`) | Intentional for independent batch rows, but undocumented |
| Query rewriting | Non-chitchat only; only calls vLLM when history is non-empty (`new_architecture/app/services/history/rewriting.py:244-251`) | Same policy, raw rather than wrapper-normalized query | Calls rewriter for every valid row but sentinel makes it a no-op | Semantically equivalent no-history result; unnecessary call abstraction |
| Selected documents | Request list passed to graph; graph defaults empty to `General_FAQ` (`main.py:607`; `agent_graph.py:144-153`) | Defaults to `General_FAQ`; passed to graph (`mobile_api.py:29`, `155-160`) | Request-level JSON list is mandatory (`main.py:1008-1025`) | Intentional input difference; default divergence is compatibility defect |
| Retrieval top-k | Configured `RAG_RETRIEVAL_TOP_K`, default 10 (`agent_graph.py:149-153`; `utils/performance_config.py:146`) | Same shared graph | Same setting (`main.py:1066-1069`) | Equivalent |
| Semantic candidates | Configured 50 (`utils/persian_hybrid_search.py:517-520`; `utils/performance_config.py:147-149`) | Same | Same shared `retrieve` | Equivalent |
| Query embedding policy | Shared `TeiEmbeddingClient.embed_query` through `_encode_query` (`utils/persian_hybrid_search.py:287-300`) | Same | Same | Equivalent once retrieval is reached |
| Hybrid retrieval | Cached BM25 + TEI query embedding + Qdrant + reciprocal-rank fusion (`utils/persian_hybrid_search.py:492-549`) | Same | Same | Equivalent once retrieval is reached |
| Retrieval-result reranking | No cross-encoder rerank of retrieved chunks; `rerank` argument is ignored by `RAGSystem.retrieve` (`utils/RagSystem.py:159-166`) | Same | Same | Obsolete API/possible missing intended behavior, but parity is equal |
| Related-question reranking | FAQ graph extracts 5 and sends one batched TEI rerank at threshold 0.1 (`agent_graph.py:116-175`; `utils/persian_hybrid_search.py:560-620`) | Same graph threshold 0.1; configured mobile threshold 0.5 is unused (`utils/performance_config.py:153-155`) | None | Mass missing behavior; mobile threshold setting obsolete/accidental divergence from documented intent |
| Context construction | FAQ: `generate_context`; other category: first 3 results (`agent_graph.py:116-182`) | Same | Same shape manually (`main.py:1072-1089`) | Equivalent algorithm, duplicated implementation defect |
| Prompt selection | `RAGSystem.answer`, category-dependent (`utils/RagSystem.py:251-367`) | Same | Same for retrieved categories, but cannot select chit-chat | Missing chit-chat behavior in mass |
| Tone/response type | `friendly` / `normal` (`agent_graph.py:176-182`, `202-210`) | Same | Same (`main.py:1080-1089`) | Equivalent |
| Generation cap | General 500, chit-chat 200 by default (`utils/performance_config.py:156-159`; `utils/RagSystem.py:257-261`) | Same | General 500 only | Missing chit-chat cap/route in mass |
| Response cleanup | `RAGSystem.answer` cleans once (`utils/RagSystem.py:367`) | Same | Cleans again at `main.py:1090` | Obsolete duplicate cleanup in mass |
| Related questions returned | FAQ only from agent metadata (`main.py:625-639`) | FAQ only (`mobile_api.py:174-201`) | Not output | Missing behavior/output choice; batch field can be optional |
| Persistence | User query row, agent metadata, assistant response (`main.py:589-627`; `agent_service.py:70-169`) | JIT user/session plus same writes (`mobile_api.py:110-177`) | None | Intentional channel difference for `persist_messages=false` batch policy |
| Chat state/history mutation | Yes, serialized per internal session by `AgentService` lock (`agent_service.py:34-50`) | Yes | None | Intentional for independent rows |
| Feedback flags | Graph sets general true/chit-chat false (`agent_graph.py:184-187`, `213-216`); wrapper returns it | Same | None | Intentional response difference; optional batch diagnostic missing |
| Exception handling | Timeout mapped to service timeout; other errors handled by FastAPI/global handlers (`main.py:545-562`) | Preserves HTTP/service/cancellation; masks unexpected details (`mobile_api.py:203-210`) | Per-row raw exception text in answer; outer timeout aborts file (`main.py:980-990`, `1093-1094`) | Correctness/security defect in mass |
| Timeout scope | 50 s per interactive request after admission (`main.py:545-562`) | 50 s includes admission plus request (`mobile_api.py:80-100`) | 50 s for complete file (`main.py:980-996`) | Performance/correctness defect; web/mobile admission scope also differs |
| HTTP response | JSON dict with web fields (`main.py:643-650`) | `TalkResponse` schema (`mobile_api.py:32-38`, `195-202`) | Downloaded CSV/Excel (`main.py:1114-1118`) | Intentional channel-specific difference |

## Shared semantic contract required by the repair

The common service should own exactly one classification and the shared semantic decisions: validate/normalize; optionally load history; rewrite only under the existing non-chitchat/non-empty-history policy; route chit-chat versus retrieval; run the existing hybrid search, context builder, related-question reranking, category prompt, generation cap, and cleanup; and return structured internal data.

Wrappers should retain these intentional differences:

- Web keeps its existing request/response fields and web session/message persistence.
- Mobile keeps national-code user resolution, UUID-to-internal-session resolution, `TalkResponse`, and mobile persistence.
- Batch defaults to independent rows, no history, and no chat persistence; it preserves source columns and adds file-oriented result diagnostics.
- Authentication and session creation remain channel concerns.
- Related-question inclusion remains a channel option. If a distinct mobile threshold is truly required, it must be explicitly passed to the shared semantic method and tested; the current `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` variable is not consumed by the active graph.

## Defects that must not be preserved as “parity”

1. Mass bypasses classification/LangGraph and therefore treats chit-chat as a retrieval question.
2. Online wrappers classify once for rewriting and the graph classifies the same turn again, causing two TEI embeddings and two classifier passes.
3. Web normalizes before rewrite while mobile rewrites raw input; mass changes the actual model question to normalized text.
4. Mass uses the interactive timeout and limiter around a whole file.
5. Mass returns internal exception messages in answer cells and has no stable per-row failure schema.
6. The configured mobile related-question threshold is unused.
7. `RAGSystem.retrieve(..., rerank=...)` exposes an argument that does not alter retrieval.

Refactoring these issues must preserve retrieval and answer-generation policy. Because the repository has no identified retrieval-test or answer-quality-test command (`AGENTS.md:126-129`), no behavior-changing retrieval/prompt adjustment is authorized. The extraction should first lock behavior with mocked parity tests and avoid changing model prompts, top-k, semantic candidates, rerank thresholds, context rules, or token caps.

## Repaired state

Commits after this baseline introduce `answering_service.py` as the single application semantic entry point. Web and mobile use persistent `AgentService.process_message_detailed`; mass uses `AgentService.process_stateless_message`. Both execute the same LangGraph, and the graph consumes the already classified intent instead of issuing a duplicate classifier call. Batch history and persistence remain deliberately disabled. Public web/mobile response models are unchanged; the batch file adds per-row diagnostics. See `docs/architecture/MASS_ANSWER.md` and `docs/performance/17-mass-answer-repair-report.md` for the current contract.
