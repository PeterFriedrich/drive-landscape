"""src/ui.py: the review page's server, against a made-up document on a free port."""
import json
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from src import distill, state, ui
from tests.test_distill import TEXTS, VECTORS


@pytest.fixture
def site(tmp_path):
    doc = tmp_path / "doc-1"
    (doc / "work").mkdir(parents=True)
    texts = TEXTS[:5] + ["Learn the accordion. Tune the piano."]
    (doc / "items.jsonl").write_text("".join(json.dumps({"n": n, "text": t, "detail": None}) + "\n" for n, t in enumerate(texts, 1)))
    np.save(doc / "work" / "vectors.npy", VECTORS)
    assert distill.main(["--root", str(tmp_path), "propose", "doc-1"]) == 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui.handler(doc))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield doc, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def call(url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})} if data else (headers or {}))
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_the_page_and_the_state_are_served_uncached(site):
    doc, url = site
    code, body = call(url + "/")
    assert code == 200 and b"<title>Review</title>" in body
    with urllib.request.urlopen(url + "/api/state") as r:
        assert r.headers["Cache-Control"] == "no-store"
        snap = json.loads(r.read())
    assert snap["doc"] == "doc-1" and snap["counts"]["items"] == 6
    assert [(t["id"], t["groups"], t["items"]) for t in snap["themes"]] == [("t1", ["g1"], [3]), ("t2", [], [4, 5])]
    assert snap["groups"]["g1"]["theme"] == "t1"
    assert (snap["items"]["1"]["where"], snap["items"]["1"]["theme"], snap["items"]["1"]["split"]) == ("g1", "t1", None)
    assert snap["items"]["6"]["split"] == ["Learn the accordion.", "Tune the piano."]
    assert snap["items"]["6"]["theme"] is None


def test_an_action_is_one_log_line_signed_owner(site):
    doc, url = site
    before = len(state.read_log(doc / "work" / "log.jsonl"))
    code, body = call(url + "/api/log", {"op": "break", "item": 6, "parts": ["Learn the accordion", "Tune the piano"], "who": "agent"})
    assert code == 200 and json.loads(body)["logged"]["who"] == "owner"
    code, body = call(url + "/api/log", {"op": "assign", "item": "6.2", "theme": "t1"})
    assert code == 200
    code, body = call(url + "/api/log", {"op": "create", "name": "music", "items": ["6.1"], "group": "g1"})
    assert json.loads(body)["logged"]["group"] == "g2"  # the server numbers it, whatever the page sent
    code, body = call(url + "/api/log", {"op": "confirm", "group": "g2"})
    assert code == 200
    assert len(state.read_log(doc / "work" / "log.jsonl")) == before + 4
    snap = json.loads(call(url + "/api/state")[1])
    assert "6" not in snap["items"] and snap["items"]["6.2"]["theme"] == "t1"
    assert snap["groups"]["g2"]["confirmed"] is True
    assert call(url + "/api/log", {"op": "later", "item": "6.2", "on": True})[0] == 200
    assert call(url + "/api/log", {"op": "later", "group": "g2", "on": True})[0] == 200
    snap = json.loads(call(url + "/api/state")[1])
    assert (snap["items"]["6.2"]["later"], snap["items"]["6.2"]["where"], snap["items"]["6.2"]["theme"]) == (True, "kept", "t1")
    assert snap["groups"]["g2"]["later"] is True and snap["groups"]["g2"]["confirmed"] is True and snap["counts"]["later"] == 2
    code, body = call(url + "/api/log", {"op": "theme", "name": "music", "groups": [], "items": ["6.2"]})  # as the page's "(a new theme…)" sends it
    new = json.loads(body)["logged"]["theme"]
    assert code == 200 and json.loads(call(url + "/api/state")[1])["items"]["6.2"]["theme"] == new != "t1"


def test_a_decision_that_makes_no_sense_is_refused_and_not_written(site):
    doc, url = site
    before = (doc / "work" / "log.jsonl").read_text()
    code, body = call(url + "/api/log", {"op": "move", "item": 6, "group": "g9"})
    assert code == 400 and "no group 'g9'" in json.loads(body)["error"]
    assert (doc / "work" / "log.jsonl").read_text() == before


def test_requests_from_another_site_are_turned_away(site):
    doc, url = site
    before = (doc / "work" / "log.jsonl").read_text()
    assert call(url + "/api/state", headers={"Host": "example.org"})[0] == 403
    assert call(url + "/api/log", {"op": "keep", "item": 6}, headers={"Host": "example.org"})[0] == 403
    assert call(url + "/api/log", {"op": "keep", "item": 6}, headers={"Content-Type": "text/plain"})[0] == 404
    assert (doc / "work" / "log.jsonl").read_text() == before


def test_neighbours_of_an_item(site):
    doc, url = site
    code, body = call(url + "/api/neighbours?item=3")
    out = json.loads(body)
    assert code == 200 and out["item"] == 3
    assert out["nearest_outside"][0]["where"] == "g1" and out["nearest_outside"][0]["theme"] == "t1"
    assert call(url + "/api/neighbours?item=99")[0] == 400
    assert call(url + "/api/log", {"op": "assign", "item": 3, "theme": None})[0] == 200
    assert json.loads(call(url + "/api/suggest")[1]) == {"items": {"3": ["t1"]}, "groups": {}, "new": []}


def test_save_commits_the_log_and_pushes_it_and_nothing_else_does(site, tmp_path_factory):
    doc, url = site
    assert json.loads(call(url + "/api/state")[1])["unsaved"] is None  # not in a repository yet
    assert call(url + "/api/save", {})[0] == 400

    remote = tmp_path_factory.mktemp("remote")
    git = lambda where, *args: subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True, text=True).stdout.strip()
    git(remote, "init", "-q", "--bare", "-b", "main")
    git(doc, "init", "-q", "-b", "main")
    git(doc, "config", "user.name", "Test")
    git(doc, "config", "user.email", "test@example.org")
    git(doc, "add", "items.jsonl", "work/log.jsonl")
    git(doc, "commit", "-q", "-m", "start")
    git(doc, "remote", "add", "origin", str(remote))
    git(doc, "push", "-q", "-u", "origin", "main")
    assert json.loads(call(url + "/api/state")[1])["unsaved"] is False

    assert call(url + "/api/log", {"op": "keep", "item": 6})[0] == 200
    (doc / "notes.txt").write_text("not the log")
    git(doc, "add", "notes.txt")
    assert json.loads(call(url + "/api/state")[1])["unsaved"] is True
    assert git(remote, "rev-list", "--count", "main") == "1"  # the decision alone saved nothing

    code, body = call(url + "/api/save", {})
    assert code == 200 and json.loads(body) == {"committed": True, "pushed": True, "error": None}
    assert git(remote, "log", "-1", "--format=%s", "main").startswith("doc-1: decisions from the review page (1 kept")
    assert git(remote, "show", "--name-only", "--format=", "main") == "work/log.jsonl"
    assert git(remote, "show", "main:work/log.jsonl") == (doc / "work" / "log.jsonl").read_text().strip()
    assert json.loads(call(url + "/api/state")[1])["unsaved"] is False
    assert json.loads(call(url + "/api/save", {})[1])["committed"] is False

    assert call(url + "/api/save", {}, headers={"Host": "example.org"})[0] == 403
