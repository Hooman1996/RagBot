# A2 rubric and structured responsibilities

Implemented rubric: `coverage-rubric-4` (A2.1). Canonical strict schemas are in
`knowledge_audit/schemas.py`; prompt templates are in `knowledge_audit/prompts.py`.
Each run records the rubric, individual schema versions and SHA-256 hashes of
templates and schemas. Filled prompts are never saved. Pydantic strict validation
forbids unknown fields and coercion. Generation requests the actual strict JSON
schema through `response_format.json_schema`; local schema, redaction, citation,
membership and semantic checks still apply. Invalid, incomplete or unsupported
outputs remain errors/review. Responsibility schema shapes/versions below are
unchanged; rubric 3 introduced shared evidence and rubric 4 records bounded
syntax recovery. Historical rubric-2 pilot artifacts are preserved.

| Responsibility | Version | Decision rules |
|---|---|---|
| Scope | `scope-1` | `kb_question`, `chitchat`, `out_of_scope`, `private_account`, `needs_context`, `uncertain`; separate self-contained/context-sufficient flags. First-person procedural wording stays eligible. Actual balance/application lookup requires private information. Missing assistant messages alone do not exclude a query. |
| Aspects | `aspects-2` | One to twelve required facts/steps, IDs `a1`… in order, relevant requested conditions, genuine subject ambiguities. Missing answer facts are aspects to check, not reasons to demand private transaction information. |
| Batch coverage | `batch-1` | At most five full Q/A entries. `full`, `partial`, `none`, `uncertain`; per-aspect source support, applicability, conditions, dependencies, exact numbered references; unresolved IDs and conflicts. |
| Compatibility | `reconciliation-1` | Actual source evidence plus support records, never labels alone. Select supplied support IDs; verify compatible conditions/dependencies/contradictions before proposing full coverage. |
| Full verification | `verification-1` | `accepted`, `rejected`, `uncertain`. Independently inspect every proposed full proof, including single-batch claims. Complete source answers accompany cited sentences to retain exceptions/conditions. |

All query/history/KB text is untrusted JSON data inside a separate user message.
The system rubric rejects embedded instructions, tool requests, schema changes
and fabricated references. No tool interface is supplied. Explanations describe
evidence succinctly; hidden reasoning and new factual customer answers are not
requested. Recommendations remain unassessed. These defenses and synthetic
injection tests do not establish immunity to adversarial models/content.

## Entirely synthetic examples

For an imaginary product, “What is the approval duration and submission cutoff?”
has two aspects; it does not require the customer's actual application status:

```json
{"version":"scope-1","decision":"kb_question","self_contained":true,"context_sufficient":true,"explanation":"A general procedure is requested."}
```

```json
{"version":"aspects-2","aspects":[{"aspect_id":"a1","description":"Approval duration","conditions":[]},{"aspect_id":"a2","description":"Submission cutoff","conditions":[]}],"ambiguities":[]}
```

A synthetic entry states “Approval takes two working days. Submit before 18:00.”
The segmenter assigns sentences 1 and 2. A support object for the first aspect
uses the immutable reference below, not a copied quotation as its ID:

```json
{"aspect_id":"a1","entry_id":"synthetic-1","citations":[{"snapshot_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","faq_entry_id":"synthetic-1","chunk_id":"synthetic-1","sentence_number":1}],"applicability":"applicable","conditions":[],"dependencies":[],"explanation":"The first sentence states the requested duration."}
```

The same entry needs another support object for `a2` citing sentence 2 before a
batch may propose full coverage. Alternatively, compatible entries in different
batches can supply the two aspects. Code preserves their aspect/source mapping,
constructs bounded complementary bundles and calls the reconciler. A full
reconciliation selects only provided `support_ids` and lists both supported IDs;
the verifier must independently accept both with no unresolved IDs. An aspect-ID
union alone never establishes full coverage.

If the duration applies to one mutually exclusive product and the cutoff to
another, reconciliation must report incompatible conditions; result needs review.
If sentence 2 is absent after broad search, only possible partial coverage is
reported within the recorded scope. “Submit a ticket” cannot establish a missing
fee or duration. It can support “How do I submit a ticket?” when the required
instructions are actually present. “How long does it take?” without a preceding
subject remains needs-context; a rewrite cannot invent the product.

## Evidence and budgeting

`answer-sentences-1` preserves every character of the redacted snapshot answer,
with sentence number and start/end offsets. It recognizes line boundaries and
Persian/Latin sentence punctuation while avoiding decimal splits. It is a
deterministic citation segmenter, not a linguistic assertion that every segment
is a grammatical sentence. References resolve the exact snapshot/FAQ/chunk and
sentence number; batch references must belong to that batch's entries.

`/tokenize` on the actual vLLM server counts complete messages with its chat
template and generation prompt, including rubric/schema and full evidence.
Reserved output and safety margin must fit the served `/v1/models` context limit.
Completion usage must match the preflight token count. Oversized entries/bundles
are review-needed; facts and conditions are never truncated to force a verdict.
Reconciliation tries at most eight complementary seed bundles per invocation;
this bounded strategy is not exhaustive evidence-combination search. Uncertainty
and rejected full proofs remain review-needed. The same model family performs
evaluation and verification; acceptance is not calibrated accuracy or human review.

## A2.1 question-level evidence and uncertainty

`question-ledger-1` records validated entry supports and their production,
initial-audit and broader-audit provenance. Phase views filter actual entry
evidence; a joint batch's full label cannot establish a subset's full coverage.
Verified production coverage establishes both KB coverage and reachability even
if audit retrieval misses its witness. Compatible complementary evidence across
phases can establish KB coverage through reconciliation and verification;
production sufficiency still uses production-selected entries only. An identical
proof has one verification result, including rejected/uncertain results; caches
never turn a different evidence subset into that proof.

Uncertain batches, failed/oversized entries, unresolved verification and conflicts
remain review codes until explicitly resolved by valid evidence. Production-only
failure does not destroy an independent audit proof; it leaves reachability
uncertain. Apparent support for every aspect without a verified compatible
combination is `needs_review`, with compatibility/bounded-search reasons, never a
partial gap with zero missing aspects. Possible gaps require identifiable missing
aspects and no evaluation uncertainty that invalidates that conclusion. Entries
actually sent to evaluation count once against 300, including malformed outputs;
output validation is a separate entry status.

## Structured output and bounded recovery

Five sequential synthetic responsibility probes check staging's schema support
before selected-query evaluation. Successful probes demonstrate observed support,
not guaranteed correctness of every subsequent response. Safe diagnostics record
responsibility/schema version, validation stage, allowlisted field path and error
type, token counts and finish reason. They exclude validation values, raw outputs,
filled prompts and exception messages. JSON syntax diagnostics contain only a
static category, numeric position, and object/start/end flags.

`json-invalid-stop-one-fresh-response-1` permits **one** fresh request only when
local JSON parsing fails before redaction with finish reason `stop`. The request
uses the identical original input, schema and generation settings; no content is
repaired or coerced. Both attempts are separately counted and retain the first
failure diagnostic. Length, redaction, field/type, citation, semantic, network and
token-budget failures do not receive this recovery. Capability probes use the same
bounded policy. This fixed policy is recorded in runtime manifests, not a new env
setting. A second syntax failure remains an error.

vLLM documents the JSON-schema request mechanism in its
[structured-output reference](https://docs.vllm.ai/en/latest/features/structured_outputs/).
The A2.1 report distinguishes actual capability checks, non-reproduced transient
syntax failures, and remaining output-length failures; it does not claim a serving
root cause or a guaranteed repair.

## A2.2 reliability policy (rubric/schema shapes unchanged)

The schema's five-entry ceiling remains valid; the implementation now uses a
narrower **two-entry maximum**, `full-entries-two-1`, based on bounded paired
output-budget checks. Every full Q/A and condition is preserved, and all remaining
candidates retain their own evaluation. Complete served input counting, 1,200
reserved output tokens by default, strict output/citation/semantic checks and
verification of full proofs remain unchanged. No network retry or global timeout
increase was introduced. A two-entry request can still be incomplete/malformed.

`audit-failures-1` records typed transport causes and phase timings separately from
schema/citation/semantic validation and output-length termination. These failures
never establish a gap or insufficient production reachability. Failed production
assessment remains uncertain if an independent audit proof succeeds. The same
one-fresh-response syntax recovery is explicit, counted and may be blocked by a
diagnostic dispatch cap; it does not repair content or retry network failures.

The [A2.2 report](A2_2_MODEL_RELIABILITY_REPORT.md) records a maximum-12-dispatch
diagnosis and one new same-five-query pilot, including unknown usage. The protected
review package supplies blank human-label fields; automated inspection is not
independent human validation or calibrated accuracy.


## A3 controlled calibration policy

The current baseline remains `coverage-rubric-4`; all five responsibility schema
versions and prompt templates are unchanged. No rubric candidate or prompt tuning
is introduced. `full-entries-configurable-1` replaces the fixed implementation
cap with `KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES` (integer 1–5, default 2). Strict
schema ceiling 5, token budgeting, output limit, production defaults, deadlines,
syntax recovery and full-verification requirements remain unchanged.

Fictional fixture facts/conditions, expected aspect support and seeded missing
facts are frozen independently in an evaluator-hidden label manifest. The live
operator loads labels only after predictions complete. Controlled candidate
ordering is explicit and does not test hybrid recall. Cap-5 comparisons reuse
the cap-2 model-derived scope/aspects, never expected labels; other model settings
and candidate order stay fixed. Returned models can still differ nondeterministically.
The protected real-query package remains unlabeled until an independent reviewer
supplies completed fields; model/Codex outputs never become human ground truth.


## A4 separate recommendation responsibilities

Coverage remains `coverage-rubric-4`, with exactly the original five schemas and
prompt hashes. `AuditModel` accepts an instance-local schema/message registry;
its defaults retain coverage behavior, strict served-token counting, JSON schema,
local validation, safe diagnostics, admission/deadlines and bounded syntax recovery.
Recommendation templates/schemas live in `recommendation_prompts.py` and
`recommendation_schemas.py`; they are never inserted into old coverage manifests.

Current recommendation rubric: `question-recommendation-rubric-2`. Responsibility
schemas are `gap-analysis-1` and `question-recommendations-1`, both strict with
unknown fields forbidden. No answer field exists. Gap analysis returns up to
three gaps g1–g3, partitioning exactly the unresolved IDs, descriptions of needed
information, supplied conditions, validated partial-support references, bounded
search/human-label limitations and mandatory independent/knowledge-team review.
Its input contains resolved intent, requested/missing aspects, concise structured
supports, source IDs, scope/stopping/uncertainty, never full Q/A chunks.

The question responsibility returns up to three q1–q3 proposals: neutral question,
gap/missing IDs, original category/subcategory, existing/proposed-new path marker,
path ID, related/equivalent FAQ IDs, equivalence basis, action, justification and
uncertainty. It receives gaps, structured partial relationships, existing taxonomy
paths and up to twenty relevant snapshot titles/IDs, never answers. Empty
subcategory is a valid null. Exact normalized-word title matches, or declared
equivalent titles, require existing-FAQ/taxonomy review rather than duplication.
Title similarity cannot prove coverage or answer incompleteness; an evaluated
partial-support basis must actually be present. New paths are proposals requiring
review. Normalization collisions cannot be silently merged.

Local checks enforce gap/aspect membership, conditions, citation membership, all
missing IDs addressed, FAQ/path identities, explicit new-path flags, question
punctuation and no new numeric premises. Free prose still requires human review;
these guards cannot establish full semantic fidelity or immunity to injection.
Model/context/schema failures remain errors, never coverage gaps or drafts.

Rubric 1's partial-gap response violated the existing equivalent-title/action
rule and was retained as an error. Rubric 2 clarifies cross-field consistency;
a paired boundary check retained exactly the same structured input hash. That
response still selected a new question by dropping the equivalence flag. A
separate deterministic lookup defect was then corrected: production punctuation
spacing must not hide a lexical title match. `snapshot-titles-taxonomy-2` uses
normalized word tokens for titles, retaining original display strings and the
unchanged taxonomy normalization. A metadata-only paired check kept rubric 2
fixed. All attempts, hashes and limitations are in the A4 report.
