"""A4 strict question-only responsibilities; separate from coverage schemas."""
from typing import Literal
from pydantic import Field
from knowledge_audit.schemas import StrictModel, SentenceReference

VERSION='question-recommendation-rubric-2'


class GapSpecification(StrictModel):
    gap_id: str = Field(pattern=r'^g[1-3]$')
    missing_aspect_ids: list[str] = Field(min_length=1,max_length=12)
    missing_information: str = Field(min_length=1,max_length=400)
    conditions: list[str] = Field(max_length=8)
    partial_support_references: list[SentenceReference] = Field(max_length=12)
    search_scope_limitations: list[Literal['bounded_search_not_exhaustive','human_labels_pending']] = Field(min_length=2,max_length=2)
    review_requirements: list[Literal['independent_gap_review','knowledge_team_confirmation','snapshot_revision_review']] = Field(min_length=2,max_length=3)


class GapAnalysis(StrictModel):
    version: Literal['gap-analysis-1']
    gaps: list[GapSpecification] = Field(min_length=1,max_length=3)


class QuestionRecommendation(StrictModel):
    recommendation_id: str = Field(pattern=r'^q[1-3]$')
    gap_ids: list[str] = Field(min_length=1,max_length=3)
    recommended_question: str = Field(min_length=1,max_length=350)
    missing_aspect_ids: list[str] = Field(min_length=1,max_length=12)
    category: str = Field(min_length=1,max_length=120)
    subcategory: str | None = Field(max_length=120)
    taxonomy_status: Literal['existing_path','proposed_new_subcategory','proposed_new_category']
    taxonomy_path_id: str | None = Field(pattern=r'^path_[0-9a-f]{24}$')
    related_faq_ids: list[str] = Field(max_length=5)
    equivalent_faq_ids: list[str] = Field(max_length=3)
    equivalence_basis: Literal['none','title_only_requires_review','evaluated_partial_support']
    action: Literal['new_question','review_existing_faq','taxonomy_review']
    justification: str = Field(min_length=1,max_length=350)
    uncertainty: list[str] = Field(min_length=1,max_length=4)


class QuestionRecommendations(StrictModel):
    version: Literal['question-recommendations-1']
    recommendations: list[QuestionRecommendation] = Field(min_length=1,max_length=3)


SCHEMAS={'gap_analysis':GapAnalysis,'question_recommendation':QuestionRecommendations}
