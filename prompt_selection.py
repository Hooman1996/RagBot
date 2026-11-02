"""Request-local prompt associations, never an access or source whitelist.

Unassociated sources retain Hibank/category fallback. No environment, header,
metadata or arbitrary category hash participates in identity selection.
"""
from dataclasses import dataclass
from types import MappingProxyType

from utils.faq_fallback import FAQ_FALLBACK_FRAGMENT

# Optional associations belong here; availability remains the document registry's job.
SOURCE_PROMPT_FAMILIES = MappingProxyType({"NegahBoom_FAQ": "negahboom"})


@dataclass(frozen=True)
class PromptContext:
    family: str = "hibank"

    @property
    def faq_fallback(self):
        if self.family == "negahboom":
            from new_architecture.app.config import MISSING_INFORMATION
            return MISSING_INFORMATION
        if self.family == "mixed":
            from mixed_source_prompts import MISSING_INFORMATION
            return MISSING_INFORMATION
        return FAQ_FALLBACK_FRAGMENT


def select_prompt_context(documents=()) -> PromptContext:
    families = {
        SOURCE_PROMPT_FAMILIES.get(str(title).strip(), "hibank")
        for title in documents if str(title).strip()
    }
    return PromptContext(next(iter(families)) if len(families) == 1 else
                         "mixed" if families else "hibank")


def prompt_templates(context, *, fallback, category=None):
    if context is None:
        return fallback
    # A mixed family remains neutral even when a document workflow is selected.
    if context.family == "mixed":
        from mixed_source_prompts import MixedSourcePrompts
        return MixedSourcePrompts
    # Single-family document workflows retain their established templates.
    if category in ("قرارداد ها", "ابلاغیه ها"):
        return fallback
    if context.family == "negahboom":
        from new_architecture.app.config import NegahBoomPrompts
        return NegahBoomPrompts
    return fallback
