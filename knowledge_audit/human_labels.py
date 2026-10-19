"""Declared independent human labels bound to protected A2.2 review observations."""
import hashlib
import re
import secrets
from pathlib import Path
from typing import Literal
from pydantic import Field, ValidationError, model_validator

from knowledge_audit.schemas import StrictModel, Aspect, SentenceReference
from knowledge_audit.privacy import AuditError, private_directory, private_json
from knowledge_audit.evidence import EvidenceIndex
from knowledge_audit.calibration_scores import fraction


class Reviewer(StrictModel):
    identity: str = Field(min_length=1,max_length=200)
    provenance: Literal["declared_independent_human"]
    attests_independent_human_review: Literal[True]
    affiliation: str = Field(max_length=300)


class HumanSupport(StrictModel):
    aspect_id: str
    citations: list[SentenceReference] = Field(min_length=1,max_length=12)
    applicability: Literal["applicable","conditional","uncertain"]
    conditions: list[str] = Field(max_length=8)


class Review(StrictModel):
    source_row_id: str = Field(pattern=r"^row_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^r_[0-9a-f]{32}$")
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["not_reviewed","completed"] = "not_reviewed"
    intended_question: str = Field(default="",max_length=4000)
    aspect_agreement: Literal["agree","corrected"] | None = None
    aspects: list[Aspect] = Field(default_factory=list,max_length=12)
    applicability_conditions: list[str] = Field(default_factory=list,max_length=24)
    coverage: Literal["full","partial","unsupported","uncertain","excluded","needs_context"] | None = None
    production_context_sufficiency: Literal["full","partial","unsupported","uncertain","not_evaluated"] | None = None
    missing_aspect_ids: list[str] = Field(default_factory=list,max_length=12)
    missing_facts: list[str] = Field(default_factory=list,max_length=12)
    evidence: list[HumanSupport] = Field(default_factory=list,max_length=60)
    notes: str = Field(default="",max_length=6000)

    @model_validator(mode="after")
    def complete_or_blank(self):
        ids = [a.aspect_id for a in self.aspects]
        if len(set(ids)) != len(ids) or not set(self.missing_aspect_ids) <= set(ids) or any(s.aspect_id not in ids for s in self.evidence):
            raise ValueError("review_aspect_membership")
        if self.status == "not_reviewed":
            if any((self.intended_question,self.aspect_agreement,self.aspects,self.applicability_conditions,self.coverage,
                    self.production_context_sufficiency,self.missing_aspect_ids,self.missing_facts,self.evidence,self.notes)):
                raise ValueError("unreviewed_fields_must_be_blank")
        elif not self.intended_question.strip() or self.aspect_agreement is None or self.coverage is None or self.production_context_sufficiency is None:
            raise ValueError("incomplete_review")
        elif self.coverage in {"full","partial","unsupported"} and not ids:
            raise ValueError("review_aspects_required")
        if self.coverage == "full" and (self.missing_facts or self.missing_aspect_ids or set(s.aspect_id for s in self.evidence) != set(ids)):
            raise ValueError("full_review_requires_evidence")
        if self.coverage == "partial" and (not self.missing_aspect_ids or not self.missing_facts):
            raise ValueError("partial_review_requires_missing_facts")
        if self.coverage == "unsupported" and (set(self.missing_aspect_ids) != set(ids) or not self.missing_facts):
            raise ValueError("unsupported_review_requires_missing_facts")
        return self


class Submission(StrictModel):
    version: Literal["human-label-import-1"]
    package_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: Reviewer | None = None
    reviews: list[Review] = Field(max_length=15)


def package(store, package_id):
    if not re.fullmatch(r"review_[0-9a-f]{32}",package_id):
        raise AuditError("invalid_review_package")
    directory = store.root / "reviews" / package_id
    manifest = store.read(directory / "manifest.json")
    observations = {}
    for name, expected in manifest["files"].items():
        if Path(name).name != name:
            raise AuditError("invalid_review_package")
        file = directory / name
        if file.is_symlink() or file.stat().st_mode & 0o077 or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise AuditError("review_package_drift")
        if name.endswith(".json"):
            row = store.read(file)
            for value in row["observations"]:
                key = (row["source_row_id"],value["run_id"],value["snapshot_id"])
                if key in observations:
                    raise AuditError("duplicate_review_observation")
                observations[key] = value
    return manifest, observations, hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()


def template(store, package_id):
    _, observations, digest = package(store,package_id)
    return {"version":"human-label-import-1","package_manifest_sha256":digest,"reviewer":None,
        "reviews":[Review(source_row_id=row,run_id=run,snapshot_id=snapshot).model_dump() for row,run,snapshot in observations]}


def import_labels(store, package_id, payload, owner=0):
    _, observations, digest = package(store,package_id)
    try:
        labels = Submission.model_validate(payload)
    except ValidationError:
        raise AuditError("invalid_human_labels") from None
    if labels.package_manifest_sha256 != digest:
        raise AuditError("human_label_package_mismatch")
    completed = []
    seen = set()
    for review in labels.reviews:
        key = (review.source_row_id,review.run_id,review.snapshot_id)
        if key not in observations or key in seen:
            raise AuditError("human_label_observation_mismatch")
        seen.add(key)
        if review.status != "completed":
            continue
        if labels.reviewer is None:
            raise AuditError("human_reviewer_required")
        meta = store.owned("runs",review.run_id,owner)
        if meta["snapshot_id"] != review.snapshot_id:
            raise AuditError("human_label_snapshot_mismatch")
        index = EvidenceIndex(store.snapshot(review.snapshot_id,owner))
        for support in review.evidence:
            for reference in support.citations:
                index.resolve(reference.model_dump())
        completed.append((review,observations[key]))
    def coverage_matches(review, observation):
        if observation.get("outcome") == "error":
            return False
        if review.coverage in {"excluded","needs_context"}:
            return observation.get("outcome") == review.coverage
        return observation.get("coverage_status") == review.coverage
    report = {"version":"human-label-scores-1","status":"pending_not_reviewed" if not completed else "declared_human_review_supplied",
        "package_observation_count":len(observations),"completed_observations":len(completed),
        "unreviewed_observations":len(observations)-len(completed),"independence":"declared_not_independently_authenticated",
        "coverage_agreement":fraction(sum(coverage_matches(review,observation) for review,observation in completed),len(completed)),
        "production_sufficiency_agreement":fraction(sum(observation.get("outcome")!="error" and observation.get("production_context_sufficiency")==review.production_context_sufficiency for review,observation in completed),len(completed)),
        "aspect_agreement":fraction(sum(review.aspect_agreement=="agree" for review,_ in completed),len(completed)),
        "observation_comparisons":[{"source_row_id":r.source_row_id,"run_id":r.run_id,"snapshot_id":r.snapshot_id,
            "aspect_agreement":r.aspect_agreement,"coverage_agrees":coverage_matches(r,o),
            "model_error":o.get("outcome")=="error","review_status":r.status} for r,o in completed],
        "human_labels_not_model_or_codex":True}
    directory = private_directory(private_directory(store.root / "human-labels") / ("labels_"+secrets.token_hex(16)))
    _, redactor = store.dataset(store.owned("runs",next(iter(observations))[1],owner)["dataset_id"],owner)
    from knowledge_audit.export import _redact
    private_json(directory / "submission.json",_redact(labels.model_dump(),redactor))
    private_json(directory / "scores.json",report)
    return {"directory":str(directory),"summary":report}
