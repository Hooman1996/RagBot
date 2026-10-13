"""FAQ editor parse/compose rules. Retrieval scoring/parsers remain unchanged.

Only a dedicated trailing metadata block is structural. Inline/quoted prose and
non-FAQ text are not reinterpreted as taxonomy. No title-based inference.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from utils.rag_utils import _clean_category_field


class FaqContentError(ValueError):
    """Content-safe validation error; messages never include submitted values."""


_META_LINE = re.compile(r'^\s*(?:question\s+category|sub\s*_\s*category)\s*:', re.I)
_META_TOKEN = re.compile(r'(question\s+category|sub\s*_\s*category)\s*:\s*', re.I)
_QUESTION = re.compile(r'^\s*question\s*:\s*(.*?)(?=\s+answer\s*\d*\s*:|$)', re.I | re.S)
_ANSWER = re.compile(r'\s+answer\s*(\d*)\s*:[ \t]*', re.I)


def clean_taxonomy(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FaqContentError('Taxonomy fields must be text or null.')
    if '\n' in value or '\r' in value or _META_TOKEN.search(value):
        raise FaqContentError('Taxonomy fields must be single-line labels without metadata markers.')
    return _clean_category_field(value) or None


def split_taxonomy_suffix(value: str) -> tuple[str, dict[str, str | None], str | None]:
    lines=value.rstrip().splitlines(keepends=True)
    start=len(lines)
    while start and (_META_LINE.match(lines[start-1]) or not lines[start-1].strip()):
        start-=1
    metadata={}
    error=None
    for line in lines[start:]:
        if not line.strip():continue
        tokens=list(_META_TOKEN.finditer(line))
        for index,token in enumerate(tokens):
            key='main_category' if token.group(1).lower().startswith('question') else 'sub_category'
            end=tokens[index+1].start() if index+1<len(tokens) else len(line)
            label=_clean_category_field(line[token.end():end]) or None
            if key in metadata and metadata[key]!=label:
                error='Conflicting trailing taxonomy entries; review the source before saving.'
            metadata[key]=label
    if error:
        # Ambiguity never silently removes source text or chooses a taxonomy.
        return value.strip(),{},error
    return ''.join(lines[:start]).strip(),metadata,None


@dataclass(frozen=True)
class FaqParts:
    is_qa: bool
    question: str | None
    answer: str
    main_category: str | None = None
    sub_category: str | None = None
    taxonomy_error: str | None = None

    def as_dict(self) -> dict:
        return dict(is_qa=self.is_qa,question=self.question,answer=self.answer,
            main_category=self.main_category,sub_category=self.sub_category,
            taxonomy_error=self.taxonomy_error)


def parse_faq_content(content: str) -> FaqParts:
    original=content
    value=content.strip()
    # Retain compatibility with the old editor's singleton bracket wrappers.
    if value.startswith('[') and value.endswith(']'):
        candidate=value[1:-1].strip()
        if candidate[:1] in ('"', "'") and candidate[-1:]==candidate[:1]:
            candidate=candidate[1:-1]
        if _QUESTION.match(candidate):value=candidate
    q=_QUESTION.match(value)
    a=_ANSWER.search(value) if q else None
    if not q or not a:
        return FaqParts(False,None,original)
    body,metadata,error=split_taxonomy_suffix(value)
    # Supported numbered answers stay inside one canonical outer answer field
    # when composed, so the unchanged generation parser keeps every section.
    answer=body[a.start():].strip() if a.group(1) else body[a.end():].strip()
    return FaqParts(True,q.group(1).strip(),answer,
        metadata.get('main_category'),metadata.get('sub_category'),error)


def compose_faq(question: str, answer: str, taxonomy: dict[str, str | None],
                *, current_content: str | None = None) -> str:
    """Create: explicit fields > unique legacy footer > absent.

    Update: explicit fields > locked record; a differing omitted legacy field is
    rejected as stale/conflicting instead of overwriting the current taxonomy.

    Omission preserves; null/empty clears. A changed parent clears an omitted
    child. Legacy orphan metadata is retained honestly, never given a parent.
    """
    current=parse_faq_content(current_content) if current_content is not None else None
    body,legacy,error=split_taxonomy_suffix(answer)
    if error or (current is not None and current.taxonomy_error):
        raise FaqContentError(error or current.taxonomy_error)
    question=question.strip()
    if not question or not body:
        raise FaqContentError('FAQ question and answer must not be empty.')
    explicit={key:clean_taxonomy(value) for key,value in taxonomy.items()}
    legacy=dict(legacy)
    if ('main_category' in explicit and 'sub_category' not in explicit
            and (explicit['main_category'] is None or
                 ('main_category' in legacy and legacy['main_category']!=explicit['main_category']))):
        legacy.pop('sub_category',None)
    if current and current.is_qa:
        for key,value in legacy.items():
            if key not in explicit and value!=getattr(current,key):
                raise FaqContentError('Embedded taxonomy differs from the current FAQ; refresh or use explicit taxonomy fields.')
    supplied={**legacy,**explicit}
    old_main=current.main_category if current and current.is_qa else None
    old_sub=current.sub_category if current and current.is_qa else None
    main=supplied.get('main_category',old_main)
    sub=supplied.get('sub_category',old_sub)
    if ('main_category' in explicit and 'sub_category' not in explicit
            and 'main_category' in legacy and legacy['main_category']!=main):
        # A legacy child belongs to its legacy parent, not an explicit new one.
        supplied.pop('sub_category',None)
        sub=None
    if main!=old_main and 'sub_category' not in supplied:
        sub=None
    if 'main_category' in explicit and main is None and 'sub_category' not in explicit:
        supplied.pop('sub_category',None)
        sub=None
    if main is None and sub is not None and ('main_category' in explicit or 'sub_category' in explicit):
        raise FaqContentError('A subcategory requires a category; clear the subcategory or provide its parent.')
    if 'main_category' in supplied and main is None:
        if 'sub_category' in supplied and sub is not None:
            raise FaqContentError('A cleared category cannot retain a supplied subcategory.')
        sub=None
    if (current and current.is_qa and question==current.question and body==current.answer
            and main==old_main and sub==old_sub):
        return current_content
    content=f'question: {question}\nanswer: {body}'
    if main is not None:
        content+=f'\nquestion category: {main}'
        if sub is not None:content+=f'. sub_category: {sub}'
    elif sub is not None:
        # Legacy orphan information is preserved without inventing taxonomy.
        content+=f'\nsub_category: {sub}'
    return content
