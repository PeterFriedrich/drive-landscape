"""Guards on `scripts/template_drift.py`, the SessionStart notice that the
template has moved. Network calls are stubbed: these pin the decisions (when
to speak, what to list), and that every failure is silent. The ignore list's
agreement with copier.yml is pinned in `tests/test_copier.py`."""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("template_drift", REPO / "scripts" / "template_drift.py")
td = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(td)

SRC = "gh:PeterFriedrich/cc-data-project-template"


def _project(tmp_path, commit="bf5f568", src=SRC):
    (tmp_path / ".copier-answers.yml").write_text(
        f"# Written by copier\n_commit: {commit}\n_src_path: {src}\n")
    return tmp_path


@pytest.fixture
def remote(monkeypatch):
    state = {"head": "abcdef0123456789", "files": ["scripts/make_brief.py"], "status": "ahead",
             "compared": 0}

    def compare(repo, base, head):
        state["compared"] += 1
        return {"status": state["status"], "files": [{"filename": f} for f in state["files"]]}

    monkeypatch.setattr(td, "remote_head", lambda repo: state["head"])
    monkeypatch.setattr(td, "compare", compare)
    return state


@pytest.mark.parametrize("src,repo", [
    ("gh:o/r", "o/r"), ("https://github.com/o/r.git", "o/r"), ("https://github.com/o/r", "o/r"),
    ("git@github.com:o/r.git", "o/r"), ("/home/opc/cc-data-project-template", None), (".", None),
])
def test_github_repo(src, repo):
    assert td.github_repo(src) == repo


@pytest.mark.parametrize("commit,base", [
    ("bf5f568", "bf5f568"), ("0.0.0.post22.dev0+gedf970e", "edf970e"),
    ("0.0.0.post22.dev0+edf970e", "edf970e"), ("v1.2.0-3-g1a2b3c4", "1a2b3c4"), ("v1.2.0", "v1.2.0"),
])
def test_base_ref(commit, base):
    assert td.base_ref(commit) == base


def test_speaks_when_project_facing_files_changed(tmp_path, remote, capsys):
    td.main(["--session-start", "--root", str(_project(tmp_path))])
    out = json.loads(capsys.readouterr().out)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "`scripts/make_brief.py`" in ctx and "compare/bf5f568...abcdef0" in ctx
    assert "Evaluate before taking it" in ctx


def test_silent_when_only_template_own_state_changed(tmp_path, remote, capsys):
    remote["files"] = ["TODO.md", "session-summary/2026-10-01_S04.md", "docs/FINDINGS_x.md", "README.md"]
    td.main(["--root", str(_project(tmp_path))])
    assert capsys.readouterr().out == ""


def test_silent_and_no_api_call_when_current(tmp_path, remote, capsys):
    remote["head"] = "bf5f568aaaaaaaa"
    td.main(["--root", str(_project(tmp_path))])
    assert capsys.readouterr().out == "" and remote["compared"] == 0


@pytest.mark.parametrize("setup", ["no_answers", "local_src", "behind"])
def test_silent_when_it_cannot_or_need_not_say(tmp_path, remote, capsys, setup):
    root = tmp_path
    if setup == "local_src":
        _project(tmp_path, src="/home/opc/cc-data-project-template")
    elif setup == "behind":
        _project(tmp_path)
        remote["status"] = "behind"
    td.main(["--root", str(root)])
    assert capsys.readouterr().out == ""


def test_network_failure_is_silent_and_exits_zero(tmp_path, monkeypatch, capsys):
    def boom(repo):
        raise OSError("no network")
    monkeypatch.setattr(td, "remote_head", boom)
    assert td.main(["--session-start", "--root", str(_project(tmp_path))]) == 0
    assert capsys.readouterr().out == ""
