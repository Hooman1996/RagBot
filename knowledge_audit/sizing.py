"""Pre-start cost estimate from completed reference runs on the same setup.

Reads only budget ledgers, row outcomes and row durations. Never reads or
returns a text field. Arithmetic is exact (fractions), so rounding up never
adds one because of float error.
"""
from fractions import Fraction
import math

from knowledge_audit.privacy import AuditError

VERSION = "coverage-sizing-1"
# The keys versions() returns for a new run; a started run also gains serving
# and runtime_configuration, which a run that has not started does not have.
VERSION_KEYS = frozenset({"prompts", "code", "code_id"})
# Limits only cap a run, and the selection method is the only setting that
# legitimately differs between a pilot and a full run.
UNCOMPARED_SETTINGS = frozenset({"operational_limits", "selection_method", "sizing"})
CLASSES = ("covered", "non_covered", "other")
MEASURES = ("completions", "tokens", "seconds")
LIMIT_KEYS = {"completions": "completion_attempts", "tokens": "token_allowance", "seconds": "execution_seconds"}
MIN_ROWS = 5


def comparable(meta_or_config):
    """The parts two runs must share to count as the same setup."""
    settings, versions = meta_or_config["settings"], meta_or_config["versions"]
    return {"settings": {k: v for k, v in settings.items() if k not in UNCOMPARED_SETTINGS},
            "versions": {k: v for k, v in versions.items() if k in VERSION_KEYS}}


def outcome_class(outcome):
    if outcome in {"covered_reachable", "covered_not_reachable"}:
        return "covered"
    if outcome in {"possible_gap", "possible_partial_gap", "needs_review"}:
        return "non_covered"
    return "other"


def _number(value):
    return float(value) if isinstance(value, Fraction) and value.denominator != 1 else int(value)


def _p90(values):
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1] if ordered else Fraction(0)


def _ledger_use(store, run_id):
    path = store._path("runs", run_id) / "budget.json"
    use = {}
    if not path.exists():
        return use
    for request in store.read(path).get("requests", {}).values():
        row_id = request.get("source_row_id")
        if not row_id or request.get("state") == "not_sent":
            continue
        completions, tokens = use.get(row_id, (0, 0))
        use[row_id] = (completions + 1, tokens + int(request.get("charged_tokens") or 0))
    return use


def _observe(store, meta, observed):
    """Outcome class, ledger completions and tokens, and duration of each finished row."""
    use = _ledger_use(store, meta["run_id"])
    rows = store._path("runs", meta["run_id"]) / "rows"
    for row_id in meta.get("selected_row_ids", []):
        row = store.read(rows / (row_id + ".json"))
        outcome = row.get("outcome", "pending")
        if outcome == "pending" or row.get("processing_status") in {"pending", "running"}:
            continue
        completions, tokens = use.get(row_id, (0, 0))
        seconds = Fraction(str(row.get("duration_ms") or 0)) / 1000
        observed[outcome_class(outcome)].append({"completions": Fraction(completions),
                                                  "tokens": Fraction(tokens), "seconds": seconds})


def reference_stats(store, owner, snapshot_id, dataset_id, settings, versions):
    from knowledge_audit.retention import artifact_access
    target = comparable({"settings": settings, "versions": versions})
    observed = {name: [] for name in CLASSES}
    # One shared artifact lock, as store readers take, for the whole read.
    with artifact_access(store.root):
        runs = [m for m in store.list_owned("runs", owner) if m.get("state") == "completed"
                and m.get("snapshot_id") == snapshot_id and m.get("dataset_id") == dataset_id
                and comparable(m) == target]
        for meta in runs:
            _observe(store, meta, observed)
    total = sum(len(v) for v in observed.values())
    if total < MIN_ROWS:
        return None
    classes = {}
    for name, rows in observed.items():
        entry = {"rows": len(rows), "share": _number(Fraction(len(rows), total))}
        for measure in MEASURES:
            values = [r[measure] for r in rows]
            entry[measure] = {"total": _number(sum(values, Fraction(0))),
                              "mean": _number(sum(values, Fraction(0)) / len(values)) if values else 0,
                              "p90": _number(_p90(values))}
        classes[name] = entry
    return {"version": VERSION, "classes": classes, "reference_run_ids": [m["run_id"] for m in runs],
            "reference_row_count": total}


def _exact(value):
    return Fraction(str(value)) if isinstance(value, float) else Fraction(value)


def estimate(row_count, stats, *, non_covered_share=None):
    classes, total = stats["classes"], stats["reference_row_count"]
    shares = {name: Fraction(classes[name]["rows"], total) for name in CLASSES}
    if non_covered_share is not None:
        override = _exact(non_covered_share)
        if not 0 <= override <= 1:
            raise AuditError("invalid_non_covered_share")
        rest = total - classes["non_covered"]["rows"]
        shares = {name: (override if name == "non_covered" else
                         (1 - override) * Fraction(classes[name]["rows"], rest) if rest else Fraction(0))
                  for name in CLASSES}
        if sum(shares.values()) != 1:
            raise AuditError("sizing_class_without_reference")
    if any(shares[name] and not classes[name]["rows"] for name in CLASSES):
        raise AuditError("sizing_class_without_reference")
    result = {"version": VERSION, "row_count": row_count, "shares": {k: _number(v) for k, v in shares.items()}}
    for measure in MEASURES:
        mean = sum((shares[c] * _exact(classes[c][measure]["total"]) / classes[c]["rows"]
                    for c in CLASSES if classes[c]["rows"]), Fraction(0))
        high = sum((shares[c] * _exact(classes[c][measure]["p90"]) for c in CLASSES), Fraction(0))
        result[measure] = {"expected": math.ceil(row_count * mean), "high": math.ceil(row_count * high)}
    return result


def compare(estimate, limits):
    result = {}
    for measure, key in LIMIT_KEYS.items():
        limit, values = limits[key], estimate[measure]
        result[measure] = {"limit": limit, "expected": values["expected"], "high": values["high"],
                           "fits_expected": values["expected"] <= limit, "fits_high": values["high"] <= limit}
    result["fits"] = all(result[m]["fits_expected"] for m in LIMIT_KEYS)
    return result
