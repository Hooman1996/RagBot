# rag_utils.py
# Contains helper functions used by both main.py and agent_graph.py
# No FastAPI imports – safe to import from anywhere.

import re
from collections import defaultdict
from typing import List, Dict

from utils.persian_normalization import normalize_persian_text


_QUESTION_PATTERN = re.compile(
    r"(?:^|\n)\s*question\s*:\s*"
    r"(.+?)(?=(?:\n\s*)?answer\s*\d*\s*:|"
    r"(?:\n\s*)?question\s+category\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_CATEGORY_PATTERN = re.compile(
    r"question\s+category\s*:\s*"
    r"(.+?)(?=\s*[.،؛|]?\s*sub\s*_\s*category\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_SUBCATEGORY_PATTERN = re.compile(
    r"sub\s*_\s*category\s*:\s*(.*?)\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _clean_category_field(value: str) -> str:
    return value.strip().strip(" .،؛:|«»")


def parse_faq_relevance_fields(content: str) -> dict[str, str]:
    """Extract only the FAQ fields used to judge retrieval relevance."""

    value = str(content or "")
    question_match = _QUESTION_PATTERN.search(value)
    category_match = _CATEGORY_PATTERN.search(value)
    subcategory_match = _SUBCATEGORY_PATTERN.search(value)
    return {
        "question": question_match.group(1).strip() if question_match else "",
        "main_category": (
            _clean_category_field(category_match.group(1))
            if category_match
            else ""
        ),
        "sub_category": (
            _clean_category_field(subcategory_match.group(1))
            if subcategory_match
            else ""
        ),
    }


def build_faq_rerank_text(content: str) -> str:
    """Build normalized BGE scoring text without including an FAQ answer."""

    fields = parse_faq_relevance_fields(content)
    lines = []
    for label, key in (
        ("سوال", "question"),
        ("دسته‌بندی", "main_category"),
        ("زیردسته", "sub_category"),
    ):
        normalized_value = normalize_persian_text(fields[key])
        if normalized_value:
            lines.append(f"{label}: {normalized_value}")
    if lines:
        return "\n".join(lines)
    return normalize_persian_text(content)

def parse_content(content: str) -> dict:
    """Extract question, answers and category from a chunk text."""
    question_match = re.search(r'question\s*:\s*(.+?)(?=answer\s*\d*\s*:|question category\s*:|$)', content, re.DOTALL)
    answers = re.findall(r'answer\s*\d*\s*:\s*(.+?)(?=answer\s*\d*\s*:|question category\s*:|$)', content, re.DOTALL)
    category_match = re.search(r'question category\s*:\s*(.+?)$', content, re.DOTALL)
    return {
        "question": question_match.group(1).strip() if question_match else "",
        "answers": [a.strip() for a in answers],
        "category": category_match.group(1).strip() if category_match else "unknown"
    }

def aggregate_results(search_results, top_k: int = 5) -> list:
    """Group search results by question category, keep top_k groups."""
    groups = defaultdict(lambda: {"matched_questions": [], "answers": [], "scores": []})
    for result in search_results:
        parsed = parse_content(result.content)
        category = parsed["category"]
        if parsed["question"] and parsed["question"] not in groups[category]["matched_questions"]:
            groups[category]["matched_questions"].append(parsed["question"])
        for ans in parsed["answers"]:
            if ans not in groups[category]["answers"]:
                groups[category]["answers"].append(ans)
        groups[category]["scores"].append(result.score)

    sorted_groups = sorted(
        groups.items(),
        # key=lambda x: sum(x[1]["scores"]) / len(x[1]["scores"]),
        key=lambda x: max(x[1]["scores"]),
        reverse=True
    )[:top_k]
    return [
        {"intent": category, "matched_questions": data["matched_questions"], "answers": data["answers"]}
        for category, data in sorted_groups
    ]

def chunk_fetcher_factory(db_manager):
    """Return a chunk_fetcher function bound to a specific db_manager."""
    def fetcher(document_titles: List[str]) -> Dict[str, dict]:
        rows = db_manager.get_chunks_by_document_titles(document_titles)
        return {str(row["chunk_id"]): {"text": row["text"], "document_name": row["document_name"]}
                for row in rows}
    return fetcher


def chunk_revision_fetcher_factory(db_manager):
    """Return the shared PostgreSQL revision observed by every app worker."""
    def fetcher(document_titles: List[str]) -> str:
        return db_manager.get_chunks_revision_by_document_titles(
            document_titles
        )
    return fetcher


# utils/rag_utils.py
import re

def clean_llm_answer(answer: str) -> str:
    if not answer:
        return answer
    # remove any leaked chain-of-thought block, not just the literal word
    answer = re.sub(r"<thought_process>.*?</thought_process>", "", answer, flags=re.DOTALL)
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL)
    return answer.strip()
