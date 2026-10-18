"""Bounded evidence audit. This module never generates customer factual answers."""
from __future__ import annotations
from collections import defaultdict
import time

from knowledge_audit import dedupe as repeated
from knowledge_audit.evidence import EvidenceIndex
from knowledge_audit.history import AuditHistoryProvider
from knowledge_audit.privacy import AuditError
from knowledge_audit.failures import TRANSPORT_CODES, VALIDATION_CODES, VERSION as FAILURE_VERSION, category
from knowledge_audit.referrals import classify_aspect, is_referral_only
from utils.read_only_audit import canonical_sha256


class CoverageEvaluator:
    def __init__(self, *, snapshot, model, retrieval, preparer, redactor, dataset,
                 entry_budget=None, documents=None, checkpoint=None, batch_max_entries=2,
                 initial_depth=150, broader_depth=300, max_entry_budget=300, verification_passes=2, dedupe=False):
        entry_budget = max_entry_budget if entry_budget is None else entry_budget
        if type(entry_budget) is not int or not 1 <= entry_budget <= max_entry_budget:
            raise AuditError("invalid_entry_budget")
        self.initial_depth, self.broader_depth = initial_depth, broader_depth
        self.index = EvidenceIndex(snapshot)
        self.model, self.retrieval, self.preparer, self.redactor = model, retrieval, preparer, redactor
        self.dataset, self.entry_budget, self.documents = dataset, entry_budget, documents
        self.checkpoint = checkpoint
        if type(batch_max_entries) is not int or not 1 <= batch_max_entries <= 5:
            raise AuditError("invalid_coverage_batch_max_entries")
        self.batch_max_entries = batch_max_entries
        if type(verification_passes) is not int or verification_passes not in {1, 2}:
            raise AuditError("invalid_verification_passes")
        self.verification_passes = verification_passes
        # Jobs set the run identity and an async key -> source-row lookup per run.
        self.dedupe, self.dedupe_identity, self.dedupe_lookup = dedupe, None, None
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
        self.aspect_classes, self.referral_excluded_ids, self.referral_unclassified_ids = {}, set(), set()
        result = {**initial, "processing_status": "running", "coverage_status": "not_evaluated",
                  "outcome": "pending", "requested_aspects": [], "supporting_sentence_refs": [],
                  "recommendations": [], "recommendation_status": "unassessed", "explanation": "",
                  "evaluated_entry_ids": [], "evaluated_entry_count": 0,
                  "support_arrangement": "unknown", "production_context_sufficiency": "not_evaluated",
                  "production_reachability": "unknown", "verification_result": "not_run",
                  "kb_snapshot_id": self.index.snapshot_id, "batch_results": [], "review_codes": [],
                  "residual_review_codes": [], "deduplicated_from_row_id": ""}
        try:
            prepared = await self.preparer.prepare(event, self.history, self.redactor, model_prepare=True)
            result.update(prepared)
            result["processing_status"] = "running"
            if prepared["preparation_status"] in {"invalid_input", "failed"}:
                result.update(processing_status="invalid_input" if prepared["preparation_status"] == "invalid_input" else "failed",
                              outcome="error", stopping_reason="invalid_input")
                return result
            # A repeated eligible question copies the same run's completed result;
            # preparation already ran because the key needs its texts and intent.
            dedupe_key = repeated.key(self.dedupe_identity, prepared) if self.dedupe and self.dedupe_lookup else None
            if dedupe_key is not None:
                result["dedupe_key_sha256"] = dedupe_key
                source = await self.dedupe_lookup(dedupe_key)
                if source is not None:
                    result = repeated.copy_result(source, result)
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
            self.aspect_classes = {a["aspect_id"]: classify_aspect(a) for a in aspects}
            retrieval_query = prepared["canonical_retrieval_query_redacted"]
            baseline = await self.retrieval.fetch(retrieval_query, production=True, documents=self.documents)
            initial_pool = await self.retrieval.fetch(retrieval_query, depth=self.initial_depth, documents=self.documents)
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
                    expanded = await self.retrieval.fetch(retrieval_query, depth=self.broader_depth, documents=self.documents)
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
            # A copy keeps its source's coverage fields; only its own accounting is set.
            if not result.get("deduplicated_from_row_id"):
                result.setdefault("question_evidence", {"version": "question-evidence-1", "batches": self.evidence_batches,
                    "entry_phases": dict(self.entry_phases), "entry_status": self.entry_status})
                result["batch_results"] = self.evidence_batches
                result.update(evaluated_entry_ids=sorted(self.evaluated_ids), evaluated_entry_count=len(self.evaluated_ids),
                              verifications=self.verifications, review_codes=list(dict.fromkeys(result.get("review_codes", []) + self.review_codes)))
            result.update(model_metrics=self.model.metrics[metric_start:], retrieval_metrics=self.retrieval.metrics[retrieval_start:],
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
                result["failure_diagnostics"].append({"failure_policy":FAILURE_VERSION,
                    "failure_category":"citation_validation" if result["error_code"] == "invalid_citation" else "semantic_validation",
                    "boundary":"evidence_validation"})
            if result.get("error_code") in TRANSPORT_CODES and not result["failure_diagnostics"]:
                result["failure_diagnostics"].append({"failure_policy":FAILURE_VERSION,
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
            # A referral alone is no evidence for a substantive fact. The model
            # output in "result" stays as returned; only the usable supports change.
            excluded = []
            for support in current:
                if not all(is_referral_only(self.index.resolve(r)["text"]) for r in support["citations"]):
                    continue
                kind = self.aspect_classes[support["aspect_id"]]
                if kind == "substantive_fact":
                    excluded.append(support)
                    self.referral_excluded_ids.add(support["support_id"])
                elif kind == "unclassified":
                    self.referral_unclassified_ids.add(support["support_id"])
            current = [s for s in current if s not in excluded]
            stored = {"batch_id": label, "source_phase": phase, "entry_ids": batch_ids, "result": batch, "supports": current}
            if excluded:
                stored["excluded_referral_supports"] = excluded
            self.evidence_batches.append(stored)
            self.review_codes = []
            remaining = {s["aspect_id"] for s in current if s["applicability"] != "uncertain"}
            if batch["coverage"] == "full" and remaining == self.required:
                # A full batch has no conflicts (validate_batch). Each wider
                # view re-verifies the proof against all of its own conflicts.
                await self.verify(question, aspects, current, [], label)
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
        inside = [p for p in self.proofs if set(p["entry_ids"]) <= allowed]
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
        # A scrubbed fact cannot be told apart from a missing one.
        if any(self.index.records[cid].get("redaction_changed") for cid in allowed & self.evaluated_ids):
            codes.append("kb_redaction_affected")
        for proof in inside:
            if proof["verdict"]["verdict"] != "accepted":
                codes.append("verification_unresolved")
            # Each proof keeps its own codes, so a later view cannot drop them.
            codes.extend(proof["codes"])
        self.review_codes = codes
        self.last_verdict = None
        witness, explanation, accepted = [], "", None
        search = {"method": "greedy-seeds-1", "seed_limit": 8, "exhaustive": False,
                  "candidate_entry_count": len({s["entry_id"] for s in usable}), "bundles_considered": 0,
                  "model_calls": 0, "cache_hits": 0}
        for proof in inside:
            if proof["verdict"]["verdict"] != "accepted":
                continue
            # A proof stands in this view only after the verifier gave every
            # conflict of this view an explicit verdict.
            records = self.view_conflicts(batches, supports, allowed, {s["aspect_id"] for s in proof["witness"]},
                                          set(proof["witness_entry_ids"]))
            verdict = proof["verdict"]
            if not {conflict_key(r) for r in records} <= proof["conflict_ids_seen"]:
                verdict = await self.verify(question, aspects, proof["witness"], records, "conflict_reverification")
            if verdict["verdict"] == "accepted":
                witness, explanation, accepted = proof["witness"], verdict["explanation"], verdict
                break
        if not witness and supported == self.required:
            records = self.view_conflicts(batches, supports, allowed, self.required, set())
            witness, explanation = await self.reconcile(question, aspects, usable, records, search)
            if not witness:
                self.review_codes.extend(["compatibility_unverified", "bounded_bundle_search_unresolved"])
        final = accepted or self.last_verdict or (inside[-1]["verdict"] if inside else {})
        review = list(dict.fromkeys(self.review_codes))
        residual = sorted(c for c in review if c in RESIDUAL_CODES)
        # A note never enters review, never blocks and is never resolved.
        if any(b.get("excluded_referral_supports") for b in batches):
            residual.append("referral_only_support")
        coverage = "full" if witness else "uncertain" if review else "partial" if supported else "unsupported"
        return {"phase": phase, "coverage": coverage, "supports": supports, "witness": witness,
                "supported_aspect_ids": sorted(self.required if witness else supported),
                "unresolved_aspect_ids": sorted(set() if witness else self.required - supported),
                "batches": batches, "conflicts": conflicts, "explanation": explanation,
                "review_codes": [] if witness else review,
                "resolved_review_codes": [c for c in review if c in BLOCKING_CODES] if witness else [],
                "residual_review_codes": residual, "conflict_assessments": final.get("conflict_assessments", []),
                "bundle_search": search,
                "budget_exhausted": bool(allowed - self.evaluated_ids - self.oversized_ids) and len(self.evaluated_ids) >= self.entry_budget,
                "candidates_exhausted": not (allowed - self.evaluated_ids - self.oversized_ids)}

    def view_conflicts(self, batches, supports, allowed, witness_aspects, proof_entry_ids):
        """Conflict records of one evidence view, deduplicated, ordered and numbered."""
        keys = set()
        for batch in batches:
            sources = tuple(sorted(cid for cid in batch["entry_ids"] if cid in allowed))
            keys.update(("batch_conflict", text, sources, "") for text in batch["result"]["conflicts"])
        # Uncertain support for an aspect the witness relies on, from an entry
        # outside the proof, is a conflict that the verifier must assess.
        keys.update(("uncertain_support", s["explanation"], (s["entry_id"],), s["aspect_id"]) for s in supports
                    if s["applicability"] == "uncertain" and s["aspect_id"] in witness_aspects
                    and s["entry_id"] not in proof_entry_ids)
        records = []
        for number, (kind, text, sources, aspect_id) in enumerate(sorted(keys), 1):
            record = {"conflict_id": "c" + str(number), "kind": kind, "text": text, "source_entry_ids": list(sources)}
            if kind == "uncertain_support":
                record["aspect_id"] = aspect_id
            records.append(record)
        return records

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
        sources = {s["entry_id"] for s in supports} | {cid for r in conflicts for cid in r["source_entry_ids"]}
        return {"question": question, "aspects": aspects, "supports": stable,
                "source_evidence": [self.index.entry(cid) for cid in sorted(sources)],
                "observed_conflicts": list(conflicts)}

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
            self.last_verdict = self.verification_cache[identity]
            return self.last_verdict
        verdict, proof_codes = await self._verification_pass(payload, conflicts, entries)
        self.verifications.append({"origin": origin, "bundle_id": identity, **verdict})
        if verdict["verdict"] == "accepted" and self.verification_passes == 2:
            # The same model checks its own work; an acceptance that depends on
            # evidence order is not evidence. Conflict IDs keep their numbers.
            reversed_payload = {**payload, "supports": payload["supports"][::-1],
                                "source_evidence": payload["source_evidence"][::-1],
                                "observed_conflicts": payload["observed_conflicts"][::-1]}
            second, second_codes = await self._verification_pass(reversed_payload, conflicts, entries)
            self.verifications.append({"origin": origin + ":reversed", "bundle_id": identity, **second})
            if second["verdict"] != "accepted":
                verdict = {**verdict, "verdict": "uncertain", "explanation": "Verification changed with evidence order; review required."}
                proof_codes = list(dict.fromkeys(proof_codes + second_codes + ["verification_order_unstable"]))
        if verdict["verdict"] != "accepted":
            proof_codes.append("verification_unresolved")
        self.verification_cache[identity] = verdict
        self.last_verdict = verdict
        self.proofs.append({"entry_ids": [e["chunk_id"] for e in entries],
                            "witness_entry_ids": sorted({s["entry_id"] for s in supports}),
                            "witness": list(supports), "verdict": verdict, "bundle_id": identity, "codes": proof_codes,
                            "conflict_ids_seen": frozenset(conflict_key(r) for r in conflicts)})
        self.review_codes.extend(proof_codes)
        return verdict

    async def _verification_pass(self, payload, conflicts, entries) -> tuple[dict, list]:
        """One verification of one evidence order; the verdict and its proof codes."""
        proof_codes = []
        if len(conflicts) > MAX_VIEW_CONFLICTS:
            proof_codes.append("conflict_limit_exceeded")
            verdict = {"verdict": "uncertain", "conflict_assessments": [], "explanation": "Too many observed conflicts to verify."}
        elif not await self.model.fits("verification", payload):
            proof_codes.append("verification_token_overflow")
            verdict = {"verdict": "uncertain", "conflict_assessments": [], "explanation": "Evidence exceeds the verified context budget."}
        else:
            verdict = await self.model.call("verification", payload)
            if not set(verdict["supported_aspect_ids"]) <= self.required or not set(verdict["unresolved_aspect_ids"]) <= self.required:
                raise AuditError("invalid_aspect_identity")
            if verdict["verdict"] == "accepted" and (set(verdict["supported_aspect_ids"]) != self.required or verdict["unresolved_aspect_ids"]):
                raise AuditError("invalid_full_claim")
            assessed = [a["conflict_id"] for a in verdict["conflict_assessments"]]
            if len(assessed) != len(set(assessed)) or not set(assessed) <= {r["conflict_id"] for r in conflicts}:
                raise AuditError("invalid_conflict_identity")
            # The code, not the model's verdict, decides that every conflict was
            # explicitly assessed and none contradicts or remains undetermined.
            found = {a["assessment"] for a in verdict["conflict_assessments"]}
            if verdict["verdict"] == "accepted":
                if "contradicts" in found:
                    proof_codes.append("conflict_contradicts_proof")
                if "cannot_determine" in found or len(assessed) != len(conflicts):
                    proof_codes.append("conflict_undetermined")
                if proof_codes:
                    verdict = {**verdict, "verdict": "rejected" if "contradicts" in found else "uncertain"}
            if verdict["verdict"] == "accepted" and any(entry["redaction_changed"] for entry in entries):
                verdict = {**verdict, "verdict": "uncertain", "explanation": "Source redaction may affect conditions; review required."}
        return verdict, proof_codes

    def apply_result(self, result, audit, production, broadened):
        if production["coverage"] == "full":
            audit = production
        coverage = audit["coverage"]
        result["residual_review_codes"] = list(audit.get("residual_review_codes", []))
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
            if any(s["support_id"] in self.referral_unclassified_ids for s in witness):
                result.update(outcome="needs_review", processing_status="needs_review",
                              review_codes=result["review_codes"] + ["referral_support_unclassified"])
        else:
            uncertain = coverage == "uncertain" or not broadened or bool(audit.get("review_codes")) or not audit["unresolved_aspect_ids"]
            if coverage == "partial":
                result["explanation"] = "Evidence supports " + ", ".join(audit["supported_aspect_ids"]) + "; unresolved aspects: " + ", ".join(audit["unresolved_aspect_ids"]) + ". Conditions require review in the cited evidence."
            result.update(outcome="needs_review" if uncertain else "possible_partial_gap" if coverage == "partial" else "possible_gap",
                processing_status="needs_review" if uncertain else "completed",
                verification_result="rejected" if any(v["verdict"] == "rejected" for v in self.verifications) else "not_run",
                stopping_reason="compatibility_unresolved" if "compatibility_unverified" in audit.get("review_codes", []) else
                    "evaluation_uncertain" if uncertain else "evaluation_limit" if audit["budget_exhausted"] else "candidate_exhausted" if audit["candidates_exhausted"] else "needs_review")
        result["evaluation_scope"] = {"initial_depths": [self.initial_depth] * 3, "broader_depths": [self.broader_depth] * 3 if broadened else [],
            "distinct_entry_budget": self.entry_budget, "whole_kb_absence_proven": False,
            "snapshot_id": self.index.snapshot_id, "bundle_search": audit.get("bundle_search", {}),
            "proof_reuse_version": "question-ledger-2"}
        result["verification_reason"] = audit["explanation"] if coverage == "full" else "; ".join(audit.get("review_codes", []))
        # The production baseline ran on redacted text production never saw, so
        # no reachability or gap claim from it is certain. KB coverage stands.
        if PRODUCTION_QUERY_REDACTION_CODES & set(result.get("uncertainty_codes", [])):
            added = ["redaction_changed_production_query"]
            if result["outcome"] in {"covered_reachable", "covered_not_reachable"}:
                added = ["production_reachability_unresolved"] + added
            result.update(outcome="needs_review", processing_status="needs_review", production_reachability="uncertain",
                          review_codes=list(dict.fromkeys(result["review_codes"] + added)))


MAX_VIEW_CONFLICTS = 40
# Every review code that view can emit belongs to exactly one set. Blocking
# codes concern the proof itself; residual codes are shown but never block a
# verified proof and are never called resolved; search codes describe a proof
# search that did not finish; note codes are informational residual codes.
BLOCKING_CODES = frozenset({"evidence_conflict", "verification_unresolved", "incompatible_conditions",
    "conflict_contradicts_proof", "conflict_undetermined", "conflict_limit_exceeded",
    "referral_support_unclassified", "verification_order_unstable"})
RESIDUAL_CODES = frozenset({"entry_too_long", "evaluation_failed", "subset_batch_uncertainty",
    "batch_support_unresolved", "batch_uncertain", "kb_redaction_affected"})
SEARCH_CODES = frozenset({"compatibility_unverified", "bounded_bundle_search_unresolved",
    "reconciliation_token_overflow", "verification_token_overflow"})
NOTE_CODES = frozenset({"referral_only_support"})
# Row-level, not view codes: the production query differs from the customer's.
PRODUCTION_QUERY_REDACTION_CODES = frozenset({"redaction_changed_query", "redaction_changed_rewrite", "redaction_changed_history"})


def conflict_key(record):
    return (record["kind"], record["text"], tuple(record["source_entry_ids"]), record.get("aspect_id", ""))


ERROR_CODES = frozenset({"coverage_disabled", "coverage_enabled_in_production", "invalid_citation", "invalid_evidence_support", "invalid_full_claim", "invalid_aspect_identity",
    "invalid_reconciliation_identity", "invalid_conflict_identity", "invalid_model_schema", "model_input_token_overflow", "incomplete_structured_output",
    "token_count_serving_mismatch", "unsupported_snapshot_entry", "reranker_capability_unavailable", "unverified_context_limit", "input_artifact_drift"}) | TRANSPORT_CODES


def explicit_subject(query):
    """Conservative prerequisite for overriding A1's broad ellipsis guard.

    Scope cannot invent a subject for a subject-free turn. Unrecognized product
    wording stays review-needed; this is not a new production classifier.
    """
    import re
    return bool(re.search(r"\b(?:account|card|loan|approval|transfer|deposit|ticket|fee)\b|"
        r"(?:حساب|کارت|وام|تسهیلات|انتقال|سپرده|تیکت|کارمزد|افتتاح|شبا)", query, re.I))
