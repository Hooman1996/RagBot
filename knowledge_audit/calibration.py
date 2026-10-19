"""Controlled inputs and protected artifacts. This evaluator never loads labels."""
import copy
import hashlib
import io
import csv
import json
import re
import secrets
import os
from pathlib import Path

from knowledge_audit.inputs import CsvInputAdapter, ColumnMapping
from knowledge_audit.store import BytesInput, now
from knowledge_audit.privacy import AuditError, private_directory, private_json, private_write
from knowledge_audit.export import encode_csv
from utils.read_only_audit import canonical_sha256

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/knowledge_coverage_calibration"


def load_inputs(directory=FIXTURES):
    lock = json.loads((directory / "lock.json").read_text())
    data = (directory / "inputs.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != lock["files"]["inputs.json"]:
        raise AuditError("calibration_fixture_drift")
    spec = json.loads(data)
    if len(spec["live_selection"]) != 12 or len(set(spec["live_selection"])) != 12:
        raise AuditError("invalid_calibration_selection")
    return spec, lock


def snapshot_variant(spec, case):
    records = {r["chunk_id"]:r for r in spec["records"]}
    if not set(case["removed_ids"]) <= set(case["baseline_record_ids"]):
        raise AuditError("invalid_seeded_removal")
    def build(ids):
        values = []
        for identity in ids:
            r = copy.deepcopy(records[identity])
            r["content_sha256"] = canonical_sha256(r)
            values.append(r)
        return {"snapshot_id":canonical_sha256(values), "records":values}
    baseline = build(case["baseline_record_ids"])
    variant = build([i for i in case["baseline_record_ids"] if i not in case["removed_ids"]])
    allowed = {r["chunk_id"] for r in variant["records"]}
    if any(not set(case[key]) <= allowed for key in ("production_ids","initial_ids","broader_ids")):
        raise AuditError("candidate_outside_fixture_snapshot")
    return baseline, variant


def input_dataset(case, redactor):
    text = io.StringIO(newline="")
    writer = csv.writer(text);writer.writerow(["query"]);writer.writerow([case["query"]])
    return CsvInputAdapter(BytesInput(text.getvalue().encode()),ColumnMapping("query")).load(redactor)


class ControlledCandidates:
    """Frozen candidate-order adapter, explicitly not hybrid-search validation."""
    def __init__(self, snapshot, case, *, initial_depth=150):
        self.initial_depth = initial_depth
        self.snapshot = copy.deepcopy(snapshot)
        self.expected = canonical_sha256(snapshot)
        self.case = copy.deepcopy(case)
        self.metrics = []

    async def check(self):
        if canonical_sha256(self.snapshot) != self.expected:
            raise AuditError("source_or_index_drift")

    async def fetch(self, query, *, production=False, depth=None, documents=None):
        depth = self.initial_depth if depth is None else depth
        await self.check()
        ids = self.case["production_ids" if production else "initial_ids" if depth==self.initial_depth else "broader_ids"]
        value = {"candidate_ids":list(ids),"selected_ids":list(ids),"candidate_count":len(ids),
            "purpose":"production_baseline" if production else "initial_audit" if depth==self.initial_depth else "broader_audit",
            "depths":[50 if production else depth]*3,"scope":"controlled_candidate_manifest"}
        self.metrics.append(value)
        return value


class FrozenResponsibilities:
    """Comparisons freeze model-derived scope/aspects, never expected labels."""
    def __init__(self, model, baseline):
        self.model = model
        self.frozen = {"scope":baseline["scope_decision"],"aspects":baseline["aspect_checklist"]}

    def __getattr__(self, key):
        return getattr(self.model,key)

    @property
    def evaluation_phase(self):
        return getattr(self.model,"evaluation_phase","unknown")

    @evaluation_phase.setter
    def evaluation_phase(self,value):
        self.model.evaluation_phase = value

    async def call(self, role, data):
        if role in self.frozen:
            return copy.deepcopy(self.frozen[role])
        return await self.model.call(role,data)

    async def fits(self, role, data):
        return await self.model.fits(role,data)


class CampaignBudget:
    """One durable A3-wide allowance. Caller holds the existing global OS lease."""
    def __init__(self, store, directory):
        self.store, self.path = store, directory / "a3-budget.json"
        if not self.path.exists():
            private_json(self.path,{"version":"a3-dispatch-budget-1","limit":120,"used":0,"blocked":0})
        self.state = store.read(self.path)
        if self.state["limit"] != 120 or type(self.state["used"]) is not int or not 0 <= self.state["used"] <= 120:
            raise AuditError("invalid_calibration_budget")

    def reserve(self):
        if self.state["used"] >= 120:
            self.state["blocked"] += 1
            self.store.write(self.path,self.state)
            raise AuditError("diagnostic_budget_exhausted")
        self.state["used"] += 1
        self.store.write(self.path,self.state)


class CalibrationArtifacts:
    def __init__(self, store):
        self.store = store
        self.root = private_directory(store.root / "calibrations")

    def path(self, identity):
        if not re.fullmatch(r"cal_[0-9a-f]{32}",identity):
            raise AuditError("invalid_artifact_id")
        if not (self.root / identity).is_dir():
            raise AuditError("artifact_not_found")
        return private_directory(self.root / identity)

    def owned(self, identity, owner):
        meta = self.store.read(self.path(identity) / "meta.json")
        if meta["owner_id"] != owner:
            raise AuditError("artifact_not_found")
        return meta

    def create(self, owner, settings, lock, selection):
        identity = "cal_" + secrets.token_hex(16)
        path = private_directory(self.root / identity)
        meta = {"version":"controlled-calibration-1","calibration_id":identity,"owner_id":owner,
            "scope":"controlled_candidates_fictional_only","created_at":now(),"state":"preparing",
            "configuration":settings,"configuration_id":canonical_sha256(settings),"fixture_lock":lock,
            "selection":selection,"human_labels":"pending_not_supplied","summary":{}}
        private_json(path / "meta.json",meta)
        return meta

    def list_owned(self, owner):
        result = []
        for path in sorted(self.root.glob("cal_*")):
            try:
                result.append(self.owned(path.name,owner))
            except (AuditError,OSError):
                continue
        return result

    def freeze(self, meta, rows):
        path = self.path(meta["calibration_id"])
        for visible in (True,False):
            fields = ("source_row_id","export_id","calibration_id","configuration_id","run_identity_id",
                "case_id","comparison_of","batch_max_entries","source_record_ordinal","scope",
                "snapshot_id","baseline_snapshot_id","removed_ids","query","processing_status",
                "coverage_status","outcome","production_context_sufficiency","missing_aspects",
                "evidence","verifications","error_code","stopping_reason","model_calls","prompt_tokens",
                "completion_tokens","duration_ms","recommendation_status")
            projection = []
            for row in rows:
                p = row.get("prediction",{})
                metrics = p.get("model_metrics",[])
                value = {k:row.get(k,"") for k in fields}
                value.update(export_id="",calibration_id=meta["calibration_id"],configuration_id=row.get("configuration_id",meta["configuration_id"]),
                    run_identity_id=meta.get("run_identity_id",""),scope=meta["scope"],query=p.get("input_query_redacted",row.get("query","")),
                    processing_status=p.get("processing_status",row["state"]),coverage_status=p.get("coverage_status","not_evaluated"),
                    outcome=p.get("outcome","pending"),production_context_sufficiency=p.get("production_context_sufficiency","not_evaluated"),
                    missing_aspects=p.get("unresolved_aspects",[]) if visible else [],evidence=p.get("supporting_sentence_refs",[]) if visible else [],
                    verifications=p.get("verifications",[]) if visible else [],error_code=p.get("error_code",row.get("error_code","")),
                    stopping_reason=p.get("stopping_reason",row["state"]),model_calls=len(metrics),
                    prompt_tokens=sum(m.get("server_prompt_tokens") or 0 for m in metrics),
                    completion_tokens=sum(m.get("completion_tokens") or 0 for m in metrics),duration_ms=p.get("duration_ms",0),
                    recommendation_status="unassessed")
                if meta["state"] == "incompatible":
                    value.update(processing_status="needs_review",coverage_status="uncertain",outcome="needs_review",
                        production_context_sufficiency="uncertain",error_code="calibration_identity_drift",stopping_reason="identity_drift")
                projection.append(value)
            body, export_id = encode_csv(projection,fields,[r["source_row_id"] for r in rows])
            prefix = "evidence" if visible else "restricted"
            manifest = {**meta,"schema_version":"calibration-export-1","export_id":export_id,
                "row_ids":[r["source_row_id"] for r in rows],"row_count":len(rows),"evidence_visible":visible,
                "csv_sha256":hashlib.sha256(body).hexdigest()}
            private_write(path / (prefix+".csv"),body)
            private_json(path / (prefix+".manifest.json"),manifest)

    def download(self, identity, owner, visible):
        self.owned(identity,owner)
        path = self.path(identity)
        prefix = "evidence" if visible else "restricted"
        manifest = self.store.read(path / (prefix+".manifest.json"))
        file = path / (prefix+".csv")
        if file.is_symlink() or file.stat().st_uid != os.getuid() or file.stat().st_mode & 0o077:
            raise AuditError("artifact_file_permissions")
        body = file.read_bytes()
        if hashlib.sha256(body).hexdigest() != manifest["csv_sha256"]:
            raise AuditError("export_identity_mismatch")
        return body, manifest
