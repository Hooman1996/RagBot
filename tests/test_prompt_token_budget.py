"""Offline token budget for answer system prompts, counted with the served model's tokenizer.

The answer request carries the system prompt, ten retrieved chunks and the
reserved RAG_MAX_NEW_TOKENS. A NegahBoom prompt that grew to 2208 tokens pushed
every NegahBoom request past vLLM's 4000-token limit (MODEL_CONTEXT_LIMIT).
The NegahBoom prompt must stay no larger than the Hibank prompt, which fits.
"""
import os
from pathlib import Path

import pytest

from new_architecture.app.config import Config, NegahBoomPrompts

TOKENIZER = Path(os.getenv(
    "PROMPT_BUDGET_TOKENIZER",
    "/root/models/models--google--gemma-4-E4B-it/tokenizer.json",
))
# Worst-case 10-chunk NegahBoom context is 1657 tokens; with chat overhead and
# 500 output tokens, a system prompt above this does not fit a 4000-token limit.
NEGAHBOOM_SYSTEM_PROMPT_MAX_TOKENS = 1700


@pytest.fixture(scope="module")
def count_tokens():
    tokenizers = pytest.importorskip("tokenizers")
    if not TOKENIZER.is_file():
        pytest.skip(f"served-model tokenizer not found at {TOKENIZER}")
    tokenizer = tokenizers.Tokenizer.from_file(str(TOKENIZER))
    return lambda text: len(tokenizer.encode(text).ids)


def test_negahboom_answer_prompt_is_not_larger_than_hibank(count_tokens):
    negahboom = count_tokens(NegahBoomPrompts.GENERAL_RAG_SYSTEM_PROMPT)
    hibank = count_tokens(Config.GENERAL_RAG_SYSTEM_PROMPT)
    assert negahboom <= hibank, (negahboom, hibank)


def test_negahboom_answer_prompt_fits_the_worst_case_budget(count_tokens):
    assert count_tokens(NegahBoomPrompts.GENERAL_RAG_SYSTEM_PROMPT) <= NEGAHBOOM_SYSTEM_PROMPT_MAX_TOKENS
