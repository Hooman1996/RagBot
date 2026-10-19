"""Post-evaluation scoring only; labels never enter evaluator/model inputs."""
import hashlib
import json
from knowledge_audit.privacy import AuditError
from knowledge_audit.calibration import FIXTURES


def load_labels(lock, directory=FIXTURES):
    body = (directory / "labels.hidden.json").read_bytes()
    if hashlib.sha256(body).hexdigest() != lock["files"]["labels.hidden.json"]:
        raise AuditError("calibration_label_drift")
    return json.loads(body)


def fraction(correct, denominator):
    return {"count":correct,"denominator":denominator,"fraction":correct/denominator if denominator else None}


def score(rows, labels):
    baseline = [r for r in rows if not r.get("comparison_of")]
    kb = [r for r in baseline if labels["cases"][r["case_id"]]["expected_scope"] == "kb_question"]
    done = [r for r in baseline if r.get("prediction",{}).get("processing_status") in {"completed","needs_review","needs_context","excluded"}]
    completed_ids = {r["case_id"] for r in done}
    def correct(row):
        return row.get("prediction",{}).get("coverage_status") == labels["cases"][row["case_id"]]["expected_coverage"]
    errors = [r for r in baseline if r.get("prediction",{}).get("outcome") == "error"]
    full = [r for r in kb if r.get("prediction",{}).get("coverage_status") == "full"]
    unsafe = [r for r in kb if labels["cases"][r["case_id"]]["expected_coverage"] in {"partial","unsupported","uncertain"}]
    sufficient = [r for r in kb if labels["cases"][r["case_id"]]["expected_coverage"] == "full"]
    false_full = [r for r in unsafe if r in full]
    false_gap = [r for r in sufficient if r.get("prediction",{}).get("outcome") in {"possible_gap","possible_partial_gap"}]
    partial = [r for r in kb if labels["cases"][r["case_id"]]["expected_coverage"] == "partial"]
    missing_correct = sum(r.get("prediction",{}).get("coverage_status") == "partial" and
        len(r["prediction"].get("requested_aspects",[])) == len(labels["cases"][r["case_id"]]["aspects"]) and
        sorted(a["aspect_id"] for a in r["prediction"].get("unresolved_aspects",[])) == sorted(labels["cases"][r["case_id"]]["missing_aspect_ids"]) for r in partial)
    reach = [r for r in kb if labels["cases"][r["case_id"]]["expected_coverage"] == "full"]
    scope = [r for r in baseline if labels["cases"][r["case_id"]]["expected_scope"] != "kb_question"]
    scope_correct = sum(r.get("prediction",{}).get("outcome") == ("needs_context" if labels["cases"][r["case_id"]]["expected_scope"]=="needs_context" else "excluded") for r in scope)
    def fact_citations_match(row):
        refs={(ref.get("chunk_id"),ref.get("sentence_number")) for ref in row.get("prediction",{}).get("supporting_sentence_refs",[])}
        relationships=labels["cases"][row["case_id"]]["support_relationships"]
        return row.get("prediction",{}).get("coverage_status")=="full" and all(
            any(any((s["entry_id"],number) in refs for number in s["sentences"]) for s in alternatives)
            for alternatives in relationships.values())
    return {"version":"controlled-scores-1","selected_cases":len(baseline),
        "completed":fraction(len(done),len(baseline)),"errors":fraction(len(errors),len(baseline)),
        "unexecuted":fraction(sum(r.get("state")=="unexecuted" for r in baseline),len(baseline)),
        "abstentions":fraction(sum(r.get("prediction",{}).get("outcome") in {"needs_review","needs_context"} for r in baseline),len(baseline)),
        "coverage_all_selected_kb":fraction(sum(correct(r) and r["case_id"] in completed_ids for r in kb),len(kb)),
        "coverage_completed_kb":fraction(sum(correct(r) for r in kb if r["case_id"] in completed_ids),sum(r["case_id"] in completed_ids for r in kb)),
        "false_full_on_unsafe_cases":fraction(len(false_full),len(unsafe)),
        "false_full_among_full_predictions":fraction(len(false_full),len(full)),
        "false_gap_on_sufficient_cases":fraction(len(false_gap),len(sufficient)),
        "partial_missing_ids_correct":fraction(missing_correct,len(partial)),
        "production_sufficiency_on_covered_gold":fraction(sum(r.get("prediction",{}).get("production_context_sufficiency")==labels["cases"][r["case_id"]]["expected_production"] for r in reach),len(reach)),
        "full_required_fact_citations_present":fraction(sum(fact_citations_match(r) for r in sufficient),len(sufficient)),
        "exclusion_context_correct":fraction(scope_correct,len(scope)),
        "false_full_case_ids":[r["case_id"] for r in false_full],"false_gap_case_ids":[r["case_id"] for r in false_gap],
        "metric_limitations":["Controlled candidate sets; no live hybrid recall measurement.",
            "Missing-aspect metric uses ordered IDs and aspect-count agreement, not independent semantic alignment.",
            "Fact-citation presence checks authored source/sentence relationships, not independent entailment review.",
            "Errors and unexecuted cases remain in overall denominators.","Fixture-derived labels are not human real-query labels."]}
