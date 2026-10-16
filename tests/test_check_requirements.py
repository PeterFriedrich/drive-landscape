"""Tests for scripts/check_requirements.py: an unpinned import fails the gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_requirements as cr  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    """A real git repo: the guard reads only tracked files."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    return tmp_path


def _write(repo, files: dict[str, str]):
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)


def test_this_repo_pins_every_import():
    assert cr.check(cr.ROOT) == []


def test_unpinned_import_fails(repo):
    _write(repo, {"requirements.txt": "numpy==2.5.4\n",
                  "src/a.py": "import numpy\nimport pandas as pd\n"})
    failures = cr.check(repo)
    assert len(failures) == 1 and "'pandas'" in failures[0] and "src/a.py:2" in failures[0]


def test_stdlib_local_relative_and_guarded_imports_pass(repo):
    _write(repo, {"requirements.txt": "",
                  "src/helpers.py": "",
                  "src/a.py": ("import os, json\nfrom pathlib import Path\nimport helpers\n"
                               "from . import x\ntry:\n    import tomllib_backport\n"
                               "except ImportError:\n    pass\n")})
    assert cr.check(repo) == []


def test_alias_and_import_note_map_to_the_package(repo):
    _write(repo, {"requirements.txt": "scikit-learn==1.8.0\nfoo-bar==1.0  # import: foobar\n",
                  "src/a.py": "from sklearn import linear_model\nimport foobar\n"})
    assert cr.check(repo) == []


def test_alias_still_needs_the_pin(repo):
    _write(repo, {"requirements.txt": "", "src/a.py": "import yaml\n"})
    assert "'pyyaml'" in cr.check(repo)[0]


def test_google_namespace_maps_by_its_second_part(repo):
    _write(repo, {"requirements.txt": "google-api-python-client==2.201.0\n",
                  "src/a.py": ("from google.oauth2.credentials import Credentials\n"
                               "from google.cloud import storage\n"
                               "import googleapiclient\n")})
    failures = cr.check(repo)
    assert len(failures) == 2
    assert "'google-auth'" in failures[0] and "'google-cloud-storage'" in failures[1]


def test_noqa_marks_a_deliberate_exception(repo):
    _write(repo, {"requirements.txt": "", "src/a.py": "import yaml  # noqa: requirements\n"})
    assert cr.check(repo) == []


def test_untracked_files_are_ignored(repo):
    _write(repo, {"requirements.txt": ""})
    (repo / "scratch.py").write_text("import pandas\n")
    assert cr.check(repo) == []


def test_notebook_imports_are_checked_and_magics_skipped(repo):
    nb = {"cells": [{"cell_type": "code", "source": ["%matplotlib inline\n", "!pip list\n",
                                                     "import matplotlib.pyplot as plt\n"]},
                    {"cell_type": "markdown", "source": ["import pandas"]}]}
    _write(repo, {"requirements.txt": "", "nb.ipynb": json.dumps(nb)})
    failures = cr.check(repo)
    assert len(failures) == 1 and "'matplotlib'" in failures[0] and "nb.ipynb:3" in failures[0]


def test_unparseable_file_fails_rather_than_passes(repo):
    _write(repo, {"requirements.txt": "", "src/a.py": "import (\n"})
    assert "cannot parse" in cr.check(repo)[0]


def test_main_exit_codes(repo, capsys):
    _write(repo, {"requirements.txt": "", "src/a.py": "import os\n"})
    assert cr.main(["--root", str(repo)]) == cr.EXIT_OK
    _write(repo, {"src/b.py": "import requests\n"})
    assert cr.main(["--root", str(repo)]) == cr.EXIT_FAIL
