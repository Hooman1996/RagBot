"""Evaluation-owned transport stage names and canonical ordering."""

CANONICAL_STAGE_NAMES = (
    "NORMALIZATION",
    "HISTORY",
    "REWRITE",
    "INTENT",
    "RETRIEVAL",
    "RERANK",
    "CONTEXT_SELECTION",
    "PROMPT_BUILD",
    "GENERATION",
)

STAGE_ORDER = {
    stage_name: index * 10
    for index, stage_name in enumerate(CANONICAL_STAGE_NAMES, start=1)
}
