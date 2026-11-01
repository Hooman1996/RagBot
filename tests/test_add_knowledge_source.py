"""Offline add-only ingestion tests. All service clients are disposable mocks."""
import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from new_architecture import data_insertion_with_api as imp

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("add_source", ROOT / "scripts/add_knowledge_source.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
NAME = "NegahBoom_FAQ"
COLUMNS = ["سوال استاندارد", "موضوع اصلی", "کلید کنترل تجمیع", "سوال شفاف‌سازی شده", "پاسخ"]


def source_csv(tmp_path, rows=None, columns=COLUMNS):
    source = tmp_path / "input.csv"
    with source.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(columns)
        writer.writerows(rows if rows is not None else [["standard", "category", "sub", "question", "answer"]])
    return source


def existing(root):
    for name in ["General_FAQ", "Other_Source"]:
        (root / "DOCUMENTS").mkdir(parents=True, exist_ok=True)
        (root / "DOCUMENTS" / f"{name}.csv").write_text("existing document")
        folder = root / "CHUNKS" / name
        folder.mkdir(parents=True)
        (folder / f"{name}_0.txt").write_text("existing chunk")
    return snapshot(root)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def args(source, root, apply=False):
    return ["--source", str(source), "--source-name", NAME, "--output-root", str(root)] + (["--apply"] if apply else [])


def convert(source, root):
    runner.checked_command([sys.executable, str(ROOT / "hihelp_knowledge_changer.py"),
                            "--source", str(source), "--source-name", NAME, "--output-root", str(root)])


def test_real_converter_and_exclusive_publish(tmp_path):
    root, staging = tmp_path / "shared", tmp_path / "staging"
    before = existing(root)
    convert(source_csv(tmp_path), staging)
    document, chunks = runner.validate(staging, NAME)
    assert chunks[0].read_text() == 'question : question\nanswer : answer\nquestion category : category. sub_category : sub'
    with document.open() as src:
        assert next(csv.reader(src)) == ["question_and_answer", "category", "sub_category"]
    runner.publish(root, NAME, document, chunks)
    for path, content in before.items():
        assert (root / path).read_bytes() == content
    after = snapshot(root)
    with pytest.raises(FileExistsError):
        runner.publish(root, NAME, document, chunks)
    assert snapshot(root) == after


def test_dry_run_real_cli_never_calls_importer_or_publishes(tmp_path, monkeypatch):
    root = tmp_path / "shared"
    before = existing(root)
    real = runner.checked_command
    commands = []
    def check(cmd):
        commands.append(cmd)
        assert "hihelp_knowledge_changer.py" in cmd[1]
        real(cmd)
    monkeypatch.setattr(runner, "checked_command", check)
    assert runner.main(args(source_csv(tmp_path), root)) == 0
    assert len(commands) == 1 and commands[0][0] == sys.executable
    assert snapshot(root) == before


@pytest.mark.parametrize("kind", ["missing", "empty", "invalid", "no-file", "converter-failure"])
def test_bad_conversion_leaves_shared_data_intact(tmp_path, monkeypatch, kind):
    root = tmp_path / "shared"
    before = existing(root)
    source = source_csv(tmp_path)
    if kind == "missing":
        source = source_csv(tmp_path, columns=["wrong"], rows=[["invalid"]])
    elif kind == "empty":
        source.write_bytes(b"")
    elif kind == "invalid":
        source = source_csv(tmp_path, rows=[["s", "c", "sub", "", ""]])
    elif kind == "no-file":
        source = tmp_path / "absent.csv"
    else:
        monkeypatch.setattr(runner, "checked_command", Mock(side_effect=RuntimeError("secret")))
    assert runner.main(args(source, root, True)) == 1
    assert snapshot(root) == before


@pytest.mark.parametrize("destination", ["document", "folder", "other-extension"])
def test_existing_destination_refuses_before_subprocess(tmp_path, monkeypatch, destination):
    root = tmp_path / "shared"
    existing(root)
    if destination == "folder":
        (root / "CHUNKS" / NAME).mkdir()
    else:
        (root / "DOCUMENTS" / (NAME + (".csv" if destination == "document" else ".pdf"))).write_text("keep")
    before = snapshot(root)
    command = Mock()
    monkeypatch.setattr(runner, "checked_command", command)
    assert runner.main(args(source_csv(tmp_path), root, True)) == 1
    command.assert_not_called()
    assert snapshot(root) == before


@pytest.mark.parametrize("fail", ["preflight", "import", None])
def test_apply_subprocess_order_scope_and_honest_failure(tmp_path, monkeypatch, capsys, fail):
    root = tmp_path / "shared"
    before = existing(root)
    real, commands = runner.checked_command, []
    def command(cmd):
        commands.append(cmd)
        if "hihelp_knowledge_changer.py" in cmd[1]:
            return real(cmd)
        assert cmd[0] == sys.executable
        assert cmd[1] == str(ROOT / "new_architecture/data_insertion_with_api.py")
        assert cmd[cmd.index("--source-name") + 1] == NAME
        assert "--insert-only" in cmd and "--yes" in cmd
        if "--preflight-only" in cmd:
            assert not (root / "DOCUMENTS" / f"{NAME}.csv").exists()
            if fail == "preflight":
                raise RuntimeError("credential-bearing URL")
        else:
            assert cmd[cmd.index("--data-root") + 1] == str(root)
            assert (root / "DOCUMENTS" / f"{NAME}.csv").exists()
            if fail == "import":
                raise RuntimeError("private source text")
    monkeypatch.setattr(runner, "checked_command", command)
    assert runner.main(args(source_csv(tmp_path), root, True)) == (1 if fail else 0)
    output = capsys.readouterr().out
    assert "credential-bearing" not in output and "private source" not in output
    assert ("Partial NEW" in output) == (fail == "import")
    for path, content in before.items():
        assert (root / path).read_bytes() == content
    if fail != "preflight":
        commands.clear()
        assert runner.main(args(tmp_path / "input.csv", root, True)) == 1
        assert not commands


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setattr(imp, "INSERT_ONLY", True)
    monkeypatch.setattr(imp, "SOURCE_NAME", NAME)
    monkeypatch.setattr(imp, "DOCUMENTS", [{"title": NAME, "owner": "admin", "collection": "Hi_Help",
                                            "file_path": str(tmp_path / f"{NAME}.csv"), "chunk_dir": NAME}])
    monkeypatch.setattr(imp, "CHUNKS_ROOT_DIR", str(tmp_path / "CHUNKS"))
    (tmp_path / f"{NAME}.csv").write_text("document")
    folder = tmp_path / "CHUNKS" / NAME
    folder.mkdir(parents=True)
    (folder / f"{NAME}_0.txt").write_text("chunk")
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    db = Mock()
    db.pg.cursor.return_value = cursor
    cursor.fetchone.return_value = None
    cursor.fetchall.side_effect = [[(1,)], [(2,)]]
    db.minio.bucket_exists.return_value = True
    db.qdrant.get_collection.return_value.config.params.vectors = SimpleNamespace(
        size=imp.Config.QDRANT_VECTOR_SIZE, distance=imp.Distance.COSINE)
    db.qdrant.retrieve.return_value = []
    return db, cursor


def test_preflight_uses_existing_owner_group_and_session_lock(service):
    db, cursor = service
    assert imp.insert_only_preflight(db) == ({"admin": 1}, {"Hi_Help": 2})
    sql = " ".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "pg_advisory_lock" in sql
    assert not any(word in sql.upper() for word in ["INSERT", "UPDATE", "DELETE", "DROP"])


@pytest.mark.parametrize("failure", ["title", "owner", "group", "bucket", "vector-config"])
def test_preflight_refuses_unsuitable_targets(service, failure):
    db, cursor = service
    if failure == "title": cursor.fetchone.return_value = (99,)
    if failure == "owner": cursor.fetchall.side_effect = [[], [(2,)]]
    if failure == "group": cursor.fetchall.side_effect = [[(1,)], []]
    if failure == "bucket": db.minio.bucket_exists.return_value = False
    if failure == "vector-config": db.qdrant.get_collection.return_value.config.params.vectors.size = 3
    with pytest.raises(imp.InsertOnlyRefusal): imp.insert_only_preflight(db)
    db.minio.fput_object.assert_not_called()
    db.qdrant.upload_points.assert_not_called()


def test_object_and_vector_collision_refuse_before_write(service):
    db, cursor = service
    with pytest.raises(imp.InsertOnlyRefusal, match="Object key"):
        imp.insert_documents(db.pg, db.minio, {"admin": 1}, {"Hi_Help": 2})
    db.minio.fput_object.assert_not_called()
    db.qdrant.retrieve.return_value = [SimpleNamespace(id=1)]
    with pytest.raises(imp.InsertOnlyRefusal, match="Vector ID"):
        imp.require_vectors_absent(db.qdrant, [1])
    db.qdrant.upload_points.assert_not_called()


def test_document_failure_preserves_new_object_and_legacy_cleanup_compatible(service, monkeypatch):
    db, cursor = service
    monkeypatch.setattr(imp, "require_object_absent", Mock())
    cursor.execute.side_effect = [None, RuntimeError("db failure")]
    with pytest.raises(RuntimeError):
        imp.insert_documents(db.pg, db.minio, {"admin": 1}, {"Hi_Help": 2})
    db.minio.fput_object.assert_called_once()
    db.minio.remove_object.assert_not_called()
    monkeypatch.setattr(imp, "INSERT_ONLY", False)
    cursor.execute.side_effect = [None, RuntimeError("db failure")]
    with pytest.raises(RuntimeError):
        imp.insert_documents(db.pg, db.minio, {"admin": 1}, {"Hi_Help": 2})
    db.minio.remove_object.assert_called_once()


def test_filtered_cli_preflight_never_seeds_or_inspects_other_chunks(tmp_path, monkeypatch):
    existing(tmp_path)
    convert(source_csv(tmp_path), tmp_path / "generated")
    doc, chunks = runner.validate(tmp_path / "generated", NAME)
    runner.publish(tmp_path, NAME, doc, chunks)
    run = Mock(return_value=0)
    monkeypatch.setattr(imp, "run_import", run)
    assert imp.main(["--data-root", str(tmp_path), "--source-name", NAME,
                     "--insert-only", "--yes", "--preflight-only"]) == 0
    assert [d["title"] for d in imp.DOCUMENTS] == [NAME]
    run.assert_called_once_with(yes=True, preflight_only=True)


def test_flags_omitted_legacy_seeding_and_confirmation(service, monkeypatch):
    db, cursor = service
    monkeypatch.setattr(imp, "INSERT_ONLY", False)
    monkeypatch.setattr(imp, "Config", SimpleNamespace(TEI_EMBED_URL="http://offline.test"))
    monkeypatch.setattr("builtins.input", Mock(return_value="no"))
    connect = Mock()
    monkeypatch.setattr(imp, "Connections", connect)
    assert imp.run_import() == 0
    connect.assert_not_called()
    monkeypatch.setattr("builtins.input", Mock(return_value="yes"))
    connect.return_value = db
    users, groups = Mock(return_value={}), Mock(return_value={})
    monkeypatch.setattr(imp, "insert_users", users)
    monkeypatch.setattr(imp, "insert_collections", groups)
    monkeypatch.setattr(imp, "insert_documents", Mock(side_effect=RuntimeError("stop")))
    assert imp.run_import() == 1
    users.assert_called_once_with(db.pg)
    groups.assert_called_once()


def test_insert_only_run_never_seeds_and_reports_failure(service, monkeypatch, capsys):
    db, cursor = service
    monkeypatch.setattr(imp.Config, "TEI_EMBED_URL", "http://offline.test")
    monkeypatch.setattr(imp, "Connections", Mock(return_value=db))
    users, groups = Mock(), Mock()
    monkeypatch.setattr(imp, "insert_users", users)
    monkeypatch.setattr(imp, "insert_collections", groups)
    monkeypatch.setattr(imp, "insert_documents", Mock(side_effect=RuntimeError("private credential")))
    with pytest.raises(RuntimeError): imp.run_import(yes=True)
    users.assert_not_called()
    groups.assert_not_called()
    db.minio.remove_object.assert_not_called()
    db.qdrant.delete.assert_not_called()
    db.close.assert_called_once()


def test_insert_only_connections_never_create_missing_storage(monkeypatch):
    monkeypatch.setattr(imp.psycopg2, "connect", Mock(return_value=Mock()))
    minio = Mock()
    minio.bucket_exists.return_value = False
    monkeypatch.setattr(imp, "Minio", Mock(return_value=minio))
    db = imp.Connections()
    with pytest.raises(imp.InsertOnlyRefusal): db.connect(insert_only=True)
    minio.make_bucket.assert_not_called()
    minio.bucket_exists.return_value = True
    qdrant = Mock()
    qdrant.get_collections.return_value.collections = []
    monkeypatch.setattr(imp, "QdrantClient", Mock(return_value=qdrant))
    with pytest.raises(imp.InsertOnlyRefusal): db.connect(insert_only=True)
    qdrant.create_collection.assert_not_called()
    minio.make_bucket.assert_not_called()


@pytest.mark.parametrize("collision", [True, False])
def test_embedding_collision_and_failure_keep_new_vectors(service, monkeypatch, collision):
    db, cursor = service
    monkeypatch.setitem(sys.modules, "parsivar", SimpleNamespace(
        Normalizer=lambda: SimpleNamespace(normalize=lambda text: text), Tokenizer=Mock(), FindStems=Mock()))
    cursor.fetchone.return_value = (0,)
    cursor.fetchall.side_effect = [[(7, 0, "synthetic chunk")]]
    session = Mock()
    session.embed_documents.return_value = [[0.0] * imp.Config.QDRANT_VECTOR_SIZE]
    db.qdrant.retrieve.return_value = [SimpleNamespace(id=7)] if collision else []
    # Stop on embedding metadata INSERT after upload, exercising former deletion path.
    def sql(statement, *args):
        if "INSERT INTO embeddings" in statement:
            raise RuntimeError("metadata failed")
    cursor.execute.side_effect = sql
    with pytest.raises(RuntimeError):
        imp.insert_embeddings(db.pg, db.qdrant, {NAME: 3}, {NAME: [7]}, session)
    if collision:
        db.qdrant.upload_points.assert_not_called()
        session.embed_documents.assert_not_called()
    else:
        db.qdrant.upload_points.assert_called_once()
        assert db.qdrant.upload_points.call_args.kwargs["wait"] is True
    db.qdrant.delete.assert_not_called()


@pytest.mark.parametrize("failure", [None, "metadata", "vectors", "object"])
def test_completion_requires_all_stores(service, failure):
    db, cursor = service
    db.minio.stat_object.return_value.size = 8 if failure != "object" else 0
    cursor.fetchone.side_effect = [("new-object-key", 8), (0 if failure == "metadata" else 1,), ("completed",)]
    db.qdrant.retrieve.return_value = ([] if failure == "vectors" else
        [SimpleNamespace(id=7, payload={"document_id": 3})])
    if failure:
        with pytest.raises(imp.InsertOnlyRefusal): imp.verify_insert_only(db, {NAME: 3}, {NAME: [7]})
    else:
        imp.verify_insert_only(db, {NAME: 3}, {NAME: [7]})
    db.qdrant.delete.assert_not_called()
    db.minio.remove_object.assert_not_called()


def test_cli_defaults_preserve_all_source_selection(tmp_path, monkeypatch):
    existing(tmp_path)
    monkeypatch.setattr(imp, "DATA_DIR", str(tmp_path))
    run = Mock(return_value=0)
    monkeypatch.setattr(imp, "run_import", run)
    assert imp.main([]) == 0
    run.assert_called_once_with(yes=False)
    assert imp.INSERT_ONLY is False
    assert {d["title"] for d in imp.DOCUMENTS} == {"General_FAQ", "Other_Source"}


def test_subprocess_failure_code_is_not_success(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=9)))
    with pytest.raises(RuntimeError): runner.checked_command(["offline-fake"])


def test_staging_validation_refuses_gaps_and_empty_chunks(tmp_path):
    convert(source_csv(tmp_path), tmp_path / "stage")
    folder = tmp_path / "stage/CHUNKS" / NAME
    file = folder / f"{NAME}_0.txt"
    file.rename(folder / f"{NAME}_2.txt")
    with pytest.raises(ValueError): runner.validate(tmp_path / "stage", NAME)
    (folder / f"{NAME}_2.txt").rename(file)
    file.write_text("   ")
    with pytest.raises(ValueError): runner.validate(tmp_path / "stage", NAME)


def test_missing_column_reports_safe_reason_through_real_converter(tmp_path, capsys):
    root = tmp_path / "shared"
    before = existing(root)
    source = source_csv(tmp_path, columns=["private-column"], rows=[["private customer content"]])
    assert runner.main(args(source, root)) == 1
    output = capsys.readouterr().out
    assert "exact required column names" in output
    assert "private-column" not in output and "private customer content" not in output
    assert snapshot(root) == before


def test_unknown_converter_error_is_never_relayed(monkeypatch):
    def failed(command, **kwargs):
        kwargs["stderr"].write(b"ValueError: private source text and credential URL\n")
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(runner.subprocess, "run", failed)
    with pytest.raises(runner.CommandFailure) as caught:
        runner.checked_command([sys.executable, str(ROOT / "hihelp_knowledge_changer.py")])
    assert "private source text" not in str(caught.value)
    assert "credential URL" not in str(caught.value)


def test_unused_standard_question_is_optional_and_output_identical(tmp_path, capsys):
    source = source_csv(tmp_path)
    with_standard = tmp_path / "with-standard"
    convert(source, with_standard)
    source = source_csv(tmp_path, columns=COLUMNS[1:], rows=[["category", "sub", "question", "answer"]])
    without_standard = tmp_path / "without-standard"
    convert(source, without_standard)
    assert snapshot(with_standard) == snapshot(without_standard)
    shared = tmp_path / "shared"
    before = existing(shared)
    assert runner.main(args(source, shared)) == 0
    assert "Dry run validated 1 chunks" in capsys.readouterr().out
    assert snapshot(shared) == before


@pytest.mark.parametrize("missing", COLUMNS[1:])
def test_each_used_column_still_required_by_real_converter(tmp_path, missing):
    required = COLUMNS[1:]
    row = dict(zip(required, ["category", "sub", "question", "answer"]))
    columns = [column for column in required if column != missing]
    source = source_csv(tmp_path, columns=columns, rows=[[row[column] for column in columns]])
    shared = tmp_path / "shared"
    before = existing(shared)
    assert runner.main(args(source, shared)) == 1
    assert snapshot(shared) == before
