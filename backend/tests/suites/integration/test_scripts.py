"""The operational scripts, run in-process with the same fakes, as the runbook uses them."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.models import EvaluationRun, Message, Report

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def run_script(name: str, *args: str, cwd: Path, monkeypatch):
    """Run scripts/<name> as `python scripts/<name> args`, with files written under cwd."""
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", [name, *args])
    runpy.run_path(str(SCRIPTS / name), run_name="__main__")


def test_seed_then_analyse_by_organisation(indexed, db, tmp_path, monkeypatch):
    """seed_conversations then run_analytics with --organization-id, as in the runbook."""
    run_script("seed_conversations.py", "--questions", "90", "--periods", "3",
               "--organization-id", indexed.org, cwd=tmp_path, monkeypatch=monkeypatch)
    audit = json.loads((tmp_path / "data" / f"seed_questions_{indexed.default_workspace}.json").read_text())
    assert audit["emerging_topic"] == "upi autopay mandates"
    logged = db.query(Message).filter(Message.organization_id == indexed.org, Message.role == "customer").count()
    assert logged > 60

    run_script("run_analytics.py", "--organization-id", indexed.org, cwd=tmp_path, monkeypatch=monkeypatch)
    reports = db.query(Report).filter(Report.organization_id == indexed.org).all()
    assert len(reports) == 3
    assert indexed.get("/api/reports/latest").status_code == 200


def test_seed_dry_run_writes_questions_but_logs_nothing(indexed, db, tmp_path, monkeypatch):
    """--dry-run stops after writing the audit file."""
    run_script("seed_conversations.py", "--questions", "30", "--dry-run",
               "--organization-id", indexed.org, cwd=tmp_path, monkeypatch=monkeypatch)
    assert (tmp_path / "data" / f"seed_questions_{indexed.default_workspace}.json").exists()
    assert db.query(Message).filter(Message.organization_id == indexed.org).count() == 0


def test_build_eval_set_then_run_evaluation(indexed, db, tmp_path, monkeypatch):
    """build_eval_set writes a question file; run_evaluation scores it and the API serves it."""
    run_script("build_eval_set.py", "--count", "6", "--workspace", indexed.default_workspace,
               cwd=tmp_path, monkeypatch=monkeypatch)
    eval_file = tmp_path / "data" / f"eval_set_{indexed.default_workspace}.json"
    questions = json.loads(eval_file.read_text())
    assert len(questions) == 6 and all(q["source_chunk_id"] for q in questions)

    run_script("run_evaluation.py", "--workspace", indexed.default_workspace,
               cwd=tmp_path, monkeypatch=monkeypatch)
    run = db.query(EvaluationRun).filter(EvaluationRun.organization_id == indexed.org).one()
    assert run.question_count == 6
    latest = indexed.get("/api/evaluation/latest").json()
    assert latest["faithfulness"] == pytest.approx(0.9)


def test_scripts_refuse_a_workspace_from_another_organisation(indexed, tmp_path, monkeypatch):
    """--workspace and --organization-id that disagree stop the script."""
    with pytest.raises(SystemExit, match="does not belong"):
        run_script("run_analytics.py", "--workspace", indexed.default_workspace,
                   "--organization-id", "org_someone_else", cwd=tmp_path, monkeypatch=monkeypatch)


def test_scripts_default_to_the_default_organisation(db, tmp_path, monkeypatch):
    """With no tenant flags, scripts work on org_default / ws_default as before."""
    run_script("run_analytics.py", cwd=tmp_path, monkeypatch=monkeypatch)  # no data: warns, does not fail
    from app.models import Workspace

    ws = db.get(Workspace, "ws_default")
    assert ws is not None and ws.organization_id == settings.default_organization_id
