"""Bounded evidence audit. This module never generates customer factual answers."""
from __future__ import annotations
from collections import defaultdict
import time

from knowledge_audit.evidence import EvidenceIndex
from knowledge_audit.history import AuditHistoryProvider
from knowledge_audit.privacy import AuditError
from utils.read_only_audit import canonical_sha256


class CoverageEvaluator:
    def __init__(self, *, snapshot, model, retrieval, preparer, redactor, dataset,
                 entry_budget=300, documents=None, checkpoint=None):
        if type(entry_budget) is not int or not 1 <= entry_budget <= 300:
            raise AuditError("invalid_entry_budget")
        self.index = EvidenceIndex(snapshot)
        self.model, self.retrieval, self.preparer, self.redactor = model, retrieval, preparer, redactor
        self.dataset, self.entry_budget, self.documents = dataset, entry_budget, documents
        self.checkpoint = checkpoint
        self.history = AuditHistoryProvider(dataset, redactor)

    async def evaluate(self, event, initial):
        started = time.perf_counter()
        metric_start = len(self.model.metrics)
        retrieval_start = len(self.retrieval.metrics)
        self.evaluated_ids = set()
        self.verifications, self.review_codes, self.proof_attempts = [], [], set()
        result = {**initial, "processing_status": "running", "coverage_status": "not_evaluated",
                  "outcome": "pending", "requested_aspects": [], "supporting_sentence_refs": [],
                  "recommendations": [], "recommendation_status": "unassessed", "explanation": "",
                  "evaluated_entry_ids": [], "evaluated_entry_count": 0,
                  "support_arrangement": "unknown", "production_context_sufficiency": "not_evaluated",
                  "production_reachability": "unknown", "verification_result": "not_run",
                  "kb_snapshot_id": self.index.snapshot_id, "batch_results": [], "review_codes": []}
        try:
            prepared = await self.preparer.prepare(event, self.history, self.redactor, model_prepare=True)
            result.update(prepared)
            result["processing_status"] = "running"
            if prepared["preparation_status"] in {"invalid_input", "failed"}:
                result.update(processing_status="invalid_input" if prepared["preparation_status"] == "invalid_input" else "failed",
                              outcome="error", stopping_reason="invalid_input")
                return result
            context = self.history.before(event)
            scope = await self.model.call("scope", {"question": prepared["standalone_query_redacted"] or prepared["normalized_query_redacted"],
                "original_question": prepared["input_query_redacted"], "existing_intent": prepared["existing_intent"],
                "preceding_history": list(context.messages[-6:]), "history_provenance": context.provenance})
            result["scope_decision"] = scope
            result["scope_status"] = scope["decision"]
            if scope["decision"] in {"chitchat", "out_of_scope", "private_account"}:
                result.update(processing_status="excluded", outcome="excluded", stopping_reason="scope_excluded",
                              explanation=scope["explanation"])
                return result
            if scope["decision"] in {"uncertain", "needs_context"}:
                result.update(processing_status="needs_review" if scope["decision"] == "uncertain" else "needs_context",
                              coverage_status="uncertain", outcome="needs_context", stopping_reason="needs_context",
                              explanation=scope["explanation"])
                return result
            if prepared["preparation_status"] == "needs_context" and scope["self_contained"] and explicit_subject(prepared["normalized_query_redacted"]):
                prepared = await self.preparer.prepare(event, self.history, self.redactor,
                    model_prepare=True, context_reviewed=True)
                result.update(prepared)
                result["scope_status"] = scope["decision"]
            if prepared["preparation_status"] not in {"prepared", "uncertain_preparation"} or (
                not scope["self_contained"] and not scope["context_sufficient"]):
                result.update(processing_status="needs_context", coverage_status="uncertain",
                              outcome="needs_context", stopping_reason="needs_context")
                return result
            question = prepared["standalone_query_redacted"]
            checklist = await self.model.call("aspects", {"question": question})
            result["aspect_checklist"] = checklist
            result["requested_aspects"] = checklist["aspects"]
            if checklist["ambiguities"]:
                result.update(processing_status="needs_review", coverage_status="uncertain",
                              outcome="needs_context", stopping_reason="needs_context",
                              review_codes=["aspect_ambiguity"], explanation="; ".join(checklist["ambiguities"]))
                return result
            aspects = checklist["aspects"]
            self.required = {a["aspect_id"] for a in aspects}
            retrieval_query = prepared["canonical_retrieval_query_redacted"]
            baseline = await self.retrieval.fetch(retrieval_query, production=True, documents=self.documents)
            initial_pool = await self.retrieval.fetch(retrieval_query, depth=150, documents=self.documents)
            result.update(production_candidate_ids=baseline["candidate_ids"], production_context_ids=baseline["selected_ids"])
            # Independent baseline assessment recognizes equivalent evidence,
            # even if the audit later chooses different witness IDs.
            production = await self.assess(baseline["selected_ids"], question, aspects, "production")
            result["production_assessment"] = production
            result["production_context_sufficiency"] = production["coverage"]
            audit = await self.assess(initial_pool["selected_ids"], question, aspects, "initial")
            result["batch_results"] = audit["batches"]
            broadened = False
            if audit["coverage"] != "full":
                expanded = await self.retrieval.fetch(retrieval_query, depth=300, documents=self.documents)
                broadened = True
                audit = await self.assess(expanded["selected_ids"], question, aspects, "broader", prior=audit)
                result["batch_results"] = audit["batches"]
            await self.retrieval.check()
            self.apply_result(result, audit, production, broadened)
            result["audit_assessment"] = audit
        except AuditError as exc:
            code = str(exc)
            # Internal errors use fixed codes; external exceptions never use their
            # text/traceback. Store only identifiers and concise reviewed output.
            if code in {"source_or_index_drift", "candidate_snapshot_mismatch"}:
                result.update(processing_status="needs_review", coverage_status="uncertain", outcome="needs_context",
                              stopping_reason="snapshot_mismatch", error_code=code, evidence_visibility="snapshot_mismatch")
            else:
                result.update(processing_status="failed", coverage_status="uncertain", outcome="error",
                              stopping_reason="processing_error", error_code=code if code in ERROR_CODES else "audit_failed")
        except Exception:
            result.update(processing_status="failed", coverage_status="uncertain", outcome="error",
                          stopping_reason="processing_error", error_code="audit_failed")
        finally:
            result.update(evaluated_entry_ids=sorted(self.evaluated_ids), evaluated_entry_count=len(self.evaluated_ids),
                          verifications=self.verifications, review_codes=list(dict.fromkeys(result.get("review_codes", []) + self.review_codes)),
                          model_metrics=self.model.metrics[metric_start:], retrieval_metrics=self.retrieval.metrics[retrieval_start:],
                          duration_ms=round((time.perf_counter() - started) * 1000, 3))
            if self.checkpoint:
                await self.checkpoint(result)
        return result

    def validate_batch(self, batch, allowed):
        supported = set()
        for support in batch["supports"]:
            if support["aspect_id"] not in self.required or support["entry_id"] not in allowed:
                raise AuditError("invalid_evidence_support")
            for reference in support["citations"]:
                if reference["chunk_id"] != support["entry_id"]:
                    raise AuditError("invalid_citation")
                self.index.resolve(reference, allowed_ids=allowed)
            if support["applicability"] != "uncertain":
                supported.add(support["aspect_id"])
        if not set(batch["unresolved_aspect_ids"]) <= self.required:
            raise AuditError("invalid_aspect_identity")
        if batch["coverage"] == "full" and (supported != self.required or batch["unresolved_aspect_ids"] or batch["conflicts"]):
            raise AuditError("invalid_full_claim")

    async def assess(self, ids, question, aspects, phase, prior=None):
        supports = list(prior["supports"]) if prior else []
        batches = list(prior["batches"]) if prior else []
        consumed = {cid for b in batches for cid in b["entry_ids"]}
        pending = [cid for cid in ids if cid not in consumed]
        pending = list(dict.fromkeys(pending))
        conflicts = [c for b in batches for c in b["result"]["conflicts"]]
        selected_proof = []
        explanation = ""
        full = False
        position = 0
        limited = False
        local_uncertain = False
        while position < len(pending):
            pack = []
            while position < len(pending) and len(pack) < 5:
                cid = pending[position]
                position += 1
                new_ids = {x["chunk_id"] for x in pack} | {cid}
                if len(self.evaluated_ids | new_ids) > self.entry_budget:
                    limited = True
                    break
                entry = self.index.entry(cid)
                payload = {"question": question, "aspects": aspects, "entries": pack + [entry]}
                if not await self.model.fits("batch", payload):
                    if not pack:
                        self.review_codes.append("entry_too_long")
                        local_uncertain = True
                        continue
                    position -= 1
                    break
                pack.append(entry)
            if not pack:
                if limited:
                    break
                continue
            batch = await self.model.call("batch", {"question": question, "aspects": aspects, "entries": pack})
            explanation = batch["explanation"]
            batch_ids = [entry["chunk_id"] for entry in pack]
            self.evaluated_ids.update(batch_ids)
            self.validate_batch(batch, set(batch_ids))
            label = phase + ":" + str(len(batches) + 1)
            batches.append({"batch_id": label, "entry_ids": batch_ids, "result": batch})
            conflicts.extend(batch["conflicts"])
            local_uncertain |= batch["coverage"] == "uncertain"
            current = []
            for support in batch["supports"]:
                enriched = {**support, "batch_id": label, "support_id": "s_" + canonical_sha256([label, support])[:24]}
                supports.append(enriched)
                current.append(enriched)
            # Every model-proposed full batch is verified, regardless of whether
            # the final question decision comes from this batch or reconciliation.
            if batch["coverage"] == "full":
                verdict = await self.verify(question, aspects, current, conflicts, label)
                if verdict["verdict"] == "accepted" and not conflicts:
                    selected_proof, explanation, full = current, verdict["explanation"], True
                    break
            usable = [s for s in supports if s["applicability"] != "uncertain"]
            if {s["aspect_id"] for s in usable} == self.required:
                proof, reason = await self.reconcile(question, aspects, usable, conflicts)
                if proof:
                    selected_proof, explanation, full = proof, reason, True
                    break
            if limited:
                break
        usable = [s for s in supports if s["applicability"] != "uncertain"]
        supported = {s["aspect_id"] for s in usable}
        coverage = "full" if full else "uncertain" if conflicts or local_uncertain or self.review_codes else "partial" if supported else "unsupported"
        return {"coverage": coverage, "supports": supports, "witness": selected_proof,
                "supported_aspect_ids": sorted(self.required if full else supported),
                "unresolved_aspect_ids": sorted(set() if full else self.required - supported),
                "batches": batches, "conflicts": conflicts, "explanation": explanation,
                "budget_exhausted": limited, "candidates_exhausted": position >= len(pending)}

    def bundles(self, supports):
        by_entry = defaultdict(list)
        for support in supports:
            by_entry[support["entry_id"]].append(support)
        entries = sorted(by_entry, key=lambda cid: (-len({s["aspect_id"] for s in by_entry[cid]}), cid))
        seen = set()
        for seed in entries[:8]:
            selected, covered = [seed], {s["aspect_id"] for s in by_entry[seed]}
            while covered != self.required:
                candidates = [cid for cid in entries if cid not in selected]
                if not candidates:
                    break
                best = max(candidates, key=lambda cid: len({s["aspect_id"] for s in by_entry[cid]} - covered))
                gain = {s["aspect_id"] for s in by_entry[best]} - covered
                if not gain:
                    break
                selected.append(best)
                covered |= gain
            identity = tuple(sorted(selected))
            if covered == self.required and identity not in seen:
                seen.add(identity)
                yield [s for cid in selected for s in by_entry[cid]]

    async def reconcile(self, question, aspects, supports, conflicts):
        fit = False
        for bundle in self.bundles(supports):
            entries = [self.index.entry(cid) for cid in dict.fromkeys(s["entry_id"] for s in bundle)]
            payload = {"question": question, "aspects": aspects, "supports": bundle,
                       "source_evidence": entries, "observed_conflicts": conflicts}
            if not await self.model.fits("reconciliation", payload):
                continue
            fit = True
            decision = await self.model.call("reconciliation", payload)
            if decision["conflicts"] or not decision["compatible"]:
                self.review_codes.append("incompatible_conditions")
            by_id = {s["support_id"]: s for s in bundle}
            if not set(decision["support_ids"]) <= set(by_id) or not set(decision["supported_aspect_ids"]) <= self.required or not set(decision["unresolved_aspect_ids"]) <= self.required:
                raise AuditError("invalid_reconciliation_identity")
            chosen = [by_id[sid] for sid in decision["support_ids"]]
            if decision["coverage"] == "full":
                if {s["aspect_id"] for s in chosen} != self.required or set(decision["supported_aspect_ids"]) != self.required or decision["unresolved_aspect_ids"] or not decision["compatible"] or decision["conflicts"]:
                    raise AuditError("invalid_full_claim")
                verdict = await self.verify(question, aspects, chosen, conflicts, "reconciliation")
                if verdict["verdict"] == "accepted" and not conflicts:
                    return chosen, decision["explanation"]
        if not fit:
            self.review_codes.append("reconciliation_token_overflow")
        return [], ""

    async def verify(self, question, aspects, supports, conflicts, origin):
        for support in supports:
            for reference in support["citations"]:
                self.index.resolve(reference)
        entries = [self.index.entry(cid) for cid in dict.fromkeys(s["entry_id"] for s in supports)]
        payload = {"question": question, "aspects": aspects, "supports": supports,
                   "source_evidence": entries, "observed_conflicts": conflicts}
        identity = canonical_sha256(payload)
        if identity in self.proof_attempts:
            return {"verdict": "rejected", "explanation": "Previously checked evidence bundle."}
        self.proof_attempts.add(identity)
        if not await self.model.fits("verification", payload):
            self.review_codes.append("verification_token_overflow")
            verdict = {"verdict": "uncertain", "explanation": "Evidence exceeds the verified context budget."}
        else:
            verdict = await self.model.call("verification", payload)
            if not set(verdict["supported_aspect_ids"]) <= self.required or not set(verdict["unresolved_aspect_ids"]) <= self.required:
                raise AuditError("invalid_aspect_identity")
            if verdict["verdict"] == "accepted" and (set(verdict["supported_aspect_ids"]) != self.required or verdict["unresolved_aspect_ids"]):
                raise AuditError("invalid_full_claim")
            if verdict["verdict"] == "accepted" and any(entry["redaction_changed"] for entry in entries):
                verdict = {**verdict, "verdict": "uncertain", "explanation": "Source redaction may affect conditions; review required."}
        self.verifications.append({"origin": origin, "bundle_id": identity, **verdict})
        if verdict["verdict"] != "accepted":
            self.review_codes.append("verification_unresolved")
        return verdict

    def apply_result(self, result, audit, production, broadened):
        coverage = audit["coverage"]
        # Partial support is still evidence, without asserting that its
        # conditions form a compatible full proof.
        witness = audit["witness"] if coverage == "full" else [s for s in audit["supports"] if s["applicability"] != "uncertain"]
        ids = list(dict.fromkeys(s["entry_id"] for s in witness))
        refs = [r for s in witness for r in s["citations"]]
        result.update(processing_status="completed", coverage_status=coverage,
            supporting_faq_ids=ids, supporting_chunk_ids=ids, supporting_sentence_refs=refs,
            supported_aspects=[{**a, "supports": [s for s in witness if s["aspect_id"] == a["aspect_id"]]}
                for a in result["requested_aspects"] if a["aspect_id"] in audit["supported_aspect_ids"]],
            unresolved_aspects=[a for a in result["requested_aspects"] if a["aspect_id"] in audit["unresolved_aspect_ids"]],
            explanation=audit["explanation"], evidence_visibility="visible")
        if len(ids) == 1:
            arrangement = "single_entry"
        elif ids:
            arrangement = "within_batch_combination" if len({s["batch_id"] for s in witness}) == 1 else "cross_batch_combination"
        else:
            arrangement = "none"
        result["support_arrangement"] = arrangement
        if coverage == "full":
            result.update(outcome="covered_reachable" if production["coverage"] == "full" else
                "covered_not_reachable" if production["coverage"] in {"partial", "unsupported"} else "needs_context",
                verification_result="accepted", stopping_reason="verified_full",
                production_reachability="sufficient" if production["coverage"] == "full" else
                    "insufficient" if production["coverage"] in {"partial", "unsupported"} else "uncertain")
        else:
            uncertain = coverage == "uncertain" or not broadened or bool(self.review_codes)
            if coverage == "partial":
                result["explanation"] = "Evidence supports " + ", ".join(audit["supported_aspect_ids"]) + "; unresolved aspects: " + ", ".join(audit["unresolved_aspect_ids"]) + ". Conditions require review in the cited evidence."
            result.update(outcome="needs_context" if uncertain else "possible_partial_gap" if coverage == "partial" else "possible_gap",
                processing_status="needs_review" if uncertain else "completed",
                verification_result="rejected" if any(v["verdict"] == "rejected" for v in self.verifications) else "not_run",
                stopping_reason="evaluation_limit" if audit["budget_exhausted"] else "candidate_exhausted" if audit["candidates_exhausted"] else "needs_review")
        result["evaluation_scope"] = {"initial_depths": [150] * 3, "broader_depths": [300] * 3 if broadened else [],
            "distinct_entry_budget": self.entry_budget, "whole_kb_absence_proven": False,
            "snapshot_id": self.index.snapshot_id}


ERROR_CODES = frozenset({"invalid_citation", "invalid_evidence_support", "invalid_full_claim", "invalid_aspect_identity",
    "invalid_reconciliation_identity", "invalid_model_schema", "model_input_token_overflow", "incomplete_structured_output",
    "token_count_serving_mismatch", "unsupported_snapshot_entry", "unverified_context_limit", "input_artifact_drift"})


def explicit_subject(query):
    """Conservative prerequisite for overriding A1's broad ellipsis guard.

    Scope cannot invent a subject for a subject-free turn. Unrecognized product
    wording stays review-needed; this is not a new production classifier.
    """
    import re
    return bool(re.search(r"\b(?:account|card|loan|approval|transfer|deposit|ticket|fee)\b|"
        r"(?:حساب|کارت|وام|تسهیلات|انتقال|سپرده|تیکت|کارمزد|افتتاح|شبا)", query, re.I))
