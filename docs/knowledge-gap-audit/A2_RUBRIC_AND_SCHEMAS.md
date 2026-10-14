# A2 rubric and structured responsibilities

Implemented rubric: `coverage-rubric-2`. Canonical strict schemas are in
`knowledge_audit/schemas.py`; prompt templates are in `knowledge_audit/prompts.py`.
Each run records the rubric, individual schema versions and SHA-256 hashes of
templates and schemas. Filled prompts are never saved. Pydantic strict validation
forbids unknown fields and coercion. Server JSON-object mode does not replace
local validation. Invalid, incomplete or unsupported outputs remain errors/review.

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
