"""Bounded evidence audit. This module never generates customer factual answers."""
from __future__ import annotations
from collections import defaultdict
import time

from knowledge_audit.evidence import EvidenceIndex
from knowledge_audit.history import AuditHistoryProvider
from knowledge_audit.privacy import AuditError
from knowledge_audit.failures import TRANSPORT_CODES, VALIDATION_CODES, category
from utils.read_only_audit import canonical_sha256


class CoverageEvaluator:
    def __init__(self, *, snapshot, model, retrieval, preparer, redactor, dataset,
                 entry_budget=300, documents=None, checkpoint=None, batch_max_entries=2):
        if type(entry_budget) is not int or not 1 <= entry_budget <= 300:
            raise AuditError("invalid_entry_budget")
        self.index = EvidenceIndex(snapshot)
        self.model, self.retrieval, self.preparer, self.redactor = model, retrieval, preparer, redactor
        self.dataset, self.entry_budget, self.documents = dataset, entry_budget, documents
        self.checkpoint = checkpoint
        if type(batch_max_entries) is not int or not 1 <= batch_max_entries <= 5:
            raise AuditError("invalid_coverage_batch_max_entries")
        self.batch_max_entries = batch_max_entries
        self.history = AuditHistoryProvider(dataset, redactor)

    async def evaluate(self, event, initial):
        started = time.perf_counter()
        metric_start = len(self.model.metrics)
        retrieval_start = len(self.retrieval.metrics)
        self.evaluated_ids = set()
        self.model.evaluation_phase = "unknown"
        self.verifications, self.review_codes = [], []
        self.evidence_batches, self.proofs = [], []
        self.verification_cache, self.reconciliation_cache = {}, {}
        self.entry_phases, self.oversized_ids = defaultdict(list), set()
        self.entry_status = {}
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
                              coverage_status="uncertain", outcome="needs_review" if scope["decision"] == "uncertain" else "needs_context",
                              stopping_reason="scope_uncertain" if scope["decision"] == "uncertain" else "needs_context",
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
                              outcome="needs_review", stopping_reason="aspect_ambiguity",
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
            try:
                production = await self.assess(baseline["selected_ids"], question, aspects, "production")
            except AuditError as exc:
                if str(exc) not in ERROR_CODES:
                    raise
                production = {"phase": "production", "coverage": "uncertain", "supports": [], "witness": [],
                    "supported_aspect_ids": [], "unresolved_aspect_ids": sorted(self.required), "batches": [],
                    "conflicts": [], "explanation": "Production evidence assessment requires review.",
                    "review_codes": ["production_evaluation_failed"], "error_code": str(exc),
                    "budget_exhausted": False, "candidates_exhausted": False, "bundle_search": {}}
            result["production_assessment"] = production
            result["production_context_sufficiency"] = production["coverage"]
            broadened = False
            phases = {"production": production}
            if production["coverage"] == "full":
                # A verified production witness is already a KB witness.
                audit = production
            else:
                initial_ids = initial_pool["selected_ids"]
                phases["initial"] = await self.assess(initial_ids, question, aspects, "initial")
                question_ids = list(dict.fromkeys(baseline["selected_ids"] + initial_ids))
                audit = await self.assess(question_ids, question, aspects, "question", evaluate_new=False)
                if audit["coverage"] != "full":
                    expanded = await self.retrieval.fetch(retrieval_query, depth=300, documents=self.documents)
                    broadened = True
                    phases["broader"] = await self.assess(expanded["selected_ids"], question, aspects, "broader")
                    question_ids = list(dict.fromkeys(question_ids + expanded["selected_ids"]))
                    audit = await self.assess(question_ids, question, aspects, "question", evaluate_new=False)
            await self.retrieval.check()
            self.review_codes = list(audit["review_codes"])
            self.apply_result(result, audit, production, broadened)
            result["audit_assessment"] = audit
            result["phase_assessments"] = phases
            result["question_evidence"] = {"version": "question-evidence-1", "batches": self.evidence_batches,
                "entry_phases": dict(self.entry_phases), "entry_status": self.entry_status}
            result["batch_results"] = self.evidence_batches
        except AuditError as exc:
            code = str(exc)
            # Internal errors use fixed codes; external exceptions never use their
            # text/traceback. Store only identifiers and concise reviewed output.
            if code in {"source_or_index_drift", "candidate_snapshot_mismatch"}:
                result.update(processing_status="needs_review", coverage_status="uncertain", outcome="needs_review",
                              stopping_reason="snapshot_mismatch", error_code=code, evidence_visibility="snapshot_mismatch")
            else:
                result.update(processing_status="failed", coverage_status="uncertain", outcome="error",
                              stopping_reason="processing_error", error_code=code if code in ERROR_CODES else "audit_failed")
        except Exception as error:
            result.update(processing_status="failed", coverage_status="uncertain", outcome="error",
                          stopping_reason="processing_error", error_code=category(error))
        finally:
            result.setdefault("question_evidence", {"version": "question-evidence-1", "batches": self.evidence_batches,
                "entry_phases": dict(self.entry_phases), "entry_status": self.entry_status})
            result["batch_results"] = self.evidence_batches
            result.update(evaluated_entry_ids=sorted(self.evaluated_ids), evaluated_entry_count=len(self.evaluated_ids),
                          verifications=self.verifications, review_codes=list(dict.fromkeys(result.get("review_codes", []) + self.review_codes)),
                          model_metrics=self.model.metrics[metric_start:], retrieval_metrics=self.retrieval.metrics[retrieval_start:],
                          validation_diagnostics=[d for m in self.model.metrics[metric_start:] for d in m.get("validation_diagnostics", [])],
                          output_recovery_count=sum(m.get("attempt", 1) > 1 for m in self.model.metrics[metric_start:]),
                          recovery_policy="json-invalid-stop-one-fresh-response-1",
                          duration_ms=round((time.perf_counter() - started) * 1000, 3))
            keys = {"failure_policy", "failure_category", "role", "evaluation_phase", "boundary", "attempt",
                "dispatched", "phase_timings_ms", "duration_ms", "prompt_tokens", "server_prompt_tokens",
                "completion_tokens", "finish_reason", "server_request_ref", "http_status"}
            keys.add("server_completion_state")
            result["failure_diagnostics"] = [{k:v for k,v in m.items() if k in keys}
                for m in self.model.metrics[metric_start:] if m.get("failure_category", "none") != "none"]
            if result.get("error_code") in VALIDATION_CODES and not result["failure_diagnostics"]:
                result["failure_diagnostics"].append({"failure_policy":"audit-failures-1",
                    "failure_category":"citation_validation" if result["error_code"] == "invalid_citation" else "semantic_validation",
                    "boundary":"evidence_validation"})
            if result.get("error_code") in TRANSPORT_CODES and not result["failure_diagnostics"]:
                result["failure_diagnostics"].append({"failure_policy":"audit-failures-1",
                    "failure_category":result["error_code"], "boundary":"preparation_or_retrieval"})
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

    async def assess(self, ids, question, aspects, phase, *, evaluate_new=True):
        """One question ledger, with independently scoped evidence views.

        Per-entry support can be reused. A verdict for a joint batch is never
        copied to a subset; full requires a verified proof wholly in that view.
        """
        self.model.evaluation_phase = phase
        ids = list(dict.fromkeys(ids))
        if phase != "question":
            for cid in ids:
                if phase not in self.entry_phases[cid]:
                    self.entry_phases[cid].append(phase)
        pending = [cid for cid in ids if cid not in self.evaluated_ids and cid not in self.oversized_ids] if evaluate_new else []
        position = 0
        limited = False
        while position < len(pending):
            pack = []
            while position < len(pending) and len(pack) < self.batch_max_entries:
                cid = pending[position]
                position += 1
                new_ids = {x["chunk_id"] for x in pack} | {cid}
                if len(self.evaluated_ids | set(getattr(self, "prior_evaluated_entry_ids", ())) | new_ids) > self.entry_budget:
                    limited = True
                    break
                entry = self.index.entry(cid)
                payload = {"question": question, "aspects": aspects, "entries": pack + [entry]}
                if not await self.model.fits("batch", payload):
                    if not pack:
                        self.oversized_ids.add(cid)
                        continue
                    position -= 1
                    break
                pack.append(entry)
            if not pack:
                if limited:
                    break
                continue
            batch_ids = [entry["chunk_id"] for entry in pack]
            # Count every distinct entry sent, even when output validation fails.
            # Such entries never become validated evidence.
            self.evaluated_ids.update(batch_ids)
            self.entry_status.update({cid: "model_requested" for cid in batch_ids})
            batch = await self.model.call("batch", {"question": question, "aspects": aspects, "entries": pack})
            self.validate_batch(batch, set(batch_ids))
            self.entry_status.update({cid: "validated" for cid in batch_ids})
            label = phase + ":" + str(len(self.evidence_batches) + 1)
            current = [{**s, "batch_id": label, "source_phase": phase,
                        "support_id": "s_" + canonical_sha256(s)[:24]} for s in batch["supports"]]
            self.evidence_batches.append({"batch_id": label, "source_phase": phase,
                "entry_ids": batch_ids, "result": batch, "supports": current})
            self.review_codes = []
            if batch["coverage"] == "full":
                await self.verify(question, aspects, current, batch["conflicts"], label)
            assessment = await self.view(ids, question, aspects, phase)
            if assessment["coverage"] == "full":
                return assessment
            if limited:
                break
        assessment = await self.view(ids, question, aspects, phase)
        unavailable = set(ids) - self.evaluated_ids - self.oversized_ids
        assessment["budget_exhausted"] = limited or (bool(unavailable) and len(self.evaluated_ids) >= self.entry_budget)
        assessment["candidates_exhausted"] = not unavailable
        return assessment

    async def view(self, ids, question, aspects, phase):
        allowed = set(ids)
        batches = [b for b in self.evidence_batches if allowed.intersection(b["entry_ids"])]
        supports = [s for b in batches for s in b["supports"] if s["entry_id"] in allowed]
        usable = [s for s in supports if s["applicability"] != "uncertain"]
        supported = {s["aspect_id"] for s in usable}
        conflicts = [c for b in batches for c in b["result"]["conflicts"]]
        codes = []
        if allowed.intersection(self.oversized_ids):
            codes.append("entry_too_long")
        if any(self.entry_status.get(cid) == "model_requested" for cid in allowed):
            codes.append("evaluation_failed")
        if any(b["result"]["coverage"] == "uncertain" for b in batches) or any(s["applicability"] == "uncertain" for s in supports):
            codes.append("batch_uncertain")
        if conflicts:
            codes.append("evidence_conflict")
        if any(s["aspect_id"] in b["result"]["unresolved_aspect_ids"] and s["applicability"] != "uncertain"
               for b in batches for s in b["supports"] if s["entry_id"] in allowed):
            codes.append("batch_support_unresolved")
        # An uncertain joint batch cannot establish a certain subset verdict.
        if any(not set(b["entry_ids"]) <= allowed and b["result"]["coverage"] == "uncertain" for b in batches):
            codes.append("subset_batch_uncertainty")
        for proof in self.proofs:
            if set(proof["entry_ids"]) <= allowed and proof["verdict"]["verdict"] != "accepted":
                codes.append("verification_unresolved")
        self.review_codes = codes
        witness, explanation = [], ""
        search = {"method": "greedy-seeds-1", "seed_limit": 8, "exhaustive": False,
                  "candidate_entry_count": len({s["entry_id"] for s in usable}), "bundles_considered": 0,
                  "model_calls": 0, "cache_hits": 0}
        for proof in self.proofs:
            if proof["verdict"]["verdict"] == "accepted" and set(proof["entry_ids"]) <= allowed:
                witness, explanation = proof["witness"], proof["verdict"]["explanation"]
                break
        if not witness and supported == self.required:
            witness, explanation = await self.reconcile(question, aspects, usable, conflicts, search)
            if not witness:
                self.review_codes.extend(["compatibility_unverified", "bounded_bundle_search_unresolved"])
        review = list(dict.fromkeys(self.review_codes))
        coverage = "full" if witness else "uncertain" if review else "partial" if supported else "unsupported"
        return {"phase": phase, "coverage": coverage, "supports": supports, "witness": witness,
                "supported_aspect_ids": sorted(self.required if witness else supported),
                "unresolved_aspect_ids": sorted(set() if witness else self.required - supported),
                "batches": batches, "conflicts": conflicts, "explanation": explanation,
                "review_codes": [] if witness else review, "resolved_review_codes": review if witness else [],
                "bundle_search": search,
                "budget_exhausted": bool(allowed - self.evaluated_ids - self.oversized_ids) and len(self.evaluated_ids) >= self.entry_budget,
                "candidates_exhausted": not (allowed - self.evaluated_ids - self.oversized_ids)}

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

    def proof_payload(self, question, aspects, supports, conflicts):
        # Phase/batch provenance is retained in the ledger, but does not change
        # the identity of an identical semantic proof. Canonical ordering lets
        # production and audit reuse the actual validated proof, not its label.
        stable = [{k: v for k, v in s.items() if k not in {"batch_id", "source_phase"}} for s in supports]
        stable.sort(key=lambda s: s["support_id"])
        return {"question": question, "aspects": aspects, "supports": stable,
                "source_evidence": [self.index.entry(cid) for cid in sorted({s["entry_id"] for s in supports})],
                "observed_conflicts": sorted(set(conflicts))}

    async def reconcile(self, question, aspects, supports, conflicts, search):
        fit = False
        for bundle in self.bundles(supports):
            payload = self.proof_payload(question, aspects, bundle, conflicts)
            search["bundles_considered"] += 1
            if not await self.model.fits("reconciliation", payload):
                continue
            fit = True
            identity = canonical_sha256(payload)
            if identity in self.reconciliation_cache:
                decision = self.reconciliation_cache[identity]
                search["cache_hits"] += 1
            else:
                decision = await self.model.call("reconciliation", payload)
                self.reconciliation_cache[identity] = decision
                search["model_calls"] += 1
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
                if verdict["verdict"] == "accepted":
                    return chosen, decision["explanation"]
        if not fit:
            self.review_codes.append("reconciliation_token_overflow")
        return [], ""

    async def verify(self, question, aspects, supports, conflicts, origin):
        for support in supports:
            for reference in support["citations"]:
                self.index.resolve(reference)
        payload = self.proof_payload(question, aspects, supports, conflicts)
        entries = payload["source_evidence"]
        identity = canonical_sha256(payload)
        if identity in self.verification_cache:
            return self.verification_cache[identity]
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
        self.verification_cache[identity] = verdict
        self.proofs.append({"entry_ids": [e["chunk_id"] for e in entries],
                            "witness": list(supports), "verdict": verdict, "bundle_id": identity})
        if verdict["verdict"] != "accepted":
            self.review_codes.append("verification_unresolved")
        return verdict

    def apply_result(self, result, audit, production, broadened):
        if production["coverage"] == "full":
            audit = production
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
                "covered_not_reachable" if production["coverage"] in {"partial", "unsupported"} else "needs_review",
                verification_result="accepted", stopping_reason="verified_full",
                production_reachability="sufficient" if production["coverage"] == "full" else
                    "insufficient" if production["coverage"] in {"partial", "unsupported"} else "uncertain")
            if production["coverage"] not in {"full", "partial", "unsupported"}:
                result.update(processing_status="needs_review", review_codes=["production_reachability_unresolved"])
        else:
            uncertain = coverage == "uncertain" or not broadened or bool(audit.get("review_codes")) or not audit["unresolved_aspect_ids"]
            if coverage == "partial":
                result["explanation"] = "Evidence supports " + ", ".join(audit["supported_aspect_ids"]) + "; unresolved aspects: " + ", ".join(audit["unresolved_aspect_ids"]) + ". Conditions require review in the cited evidence."
            result.update(outcome="needs_review" if uncertain else "possible_partial_gap" if coverage == "partial" else "possible_gap",
                processing_status="needs_review" if uncertain else "completed",
                verification_result="rejected" if any(v["verdict"] == "rejected" for v in self.verifications) else "not_run",
                stopping_reason="compatibility_unresolved" if "compatibility_unverified" in audit.get("review_codes", []) else
                    "evaluation_uncertain" if uncertain else "evaluation_limit" if audit["budget_exhausted"] else "candidate_exhausted" if audit["candidates_exhausted"] else "needs_review")
        result["evaluation_scope"] = {"initial_depths": [150] * 3, "broader_depths": [300] * 3 if broadened else [],
            "distinct_entry_budget": self.entry_budget, "whole_kb_absence_proven": False,
            "snapshot_id": self.index.snapshot_id, "bundle_search": audit.get("bundle_search", {}),
            "proof_reuse_version": "question-ledger-1"}
        result["verification_reason"] = audit["explanation"] if coverage == "full" else "; ".join(audit.get("review_codes", []))


ERROR_CODES = frozenset({"coverage_disabled", "coverage_enabled_in_production", "invalid_citation", "invalid_evidence_support", "invalid_full_claim", "invalid_aspect_identity",
    "invalid_reconciliation_identity", "invalid_model_schema", "model_input_token_overflow", "incomplete_structured_output",
    "token_count_serving_mismatch", "unsupported_snapshot_entry", "reranker_capability_unavailable", "unverified_context_limit", "input_artifact_drift"}) | TRANSPORT_CODES


def explicit_subject(query):
    """Conservative prerequisite for overriding A1's broad ellipsis guard.

    Scope cannot invent a subject for a subject-free turn. Unrecognized product
    wording stays review-needed; this is not a new production classifier.
    """
    import re
    return bool(re.search(r"\b(?:account|card|loan|approval|transfer|deposit|ticket|fee)\b|"
        r"(?:حساب|کارت|وام|تسهیلات|انتقال|سپرده|تیکت|کارمزد|افتتاح|شبا)", query, re.I))
