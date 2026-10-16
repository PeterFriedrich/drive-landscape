"""Requirements guard: every third-party import is pinned in requirements.txt.

A package installed by hand into ``.venv`` and never pinned works until the
venv is rebuilt, then is silently gone: the 2026-10-16 uv rollout dropped
pandas from one project this way (docs/TOKEN_EFFICIENCY.md §Disk). This reads
every committed ``.py`` and ``.ipynb`` without importing anything, so the merge
gate needs no project packages installed.

Rules:
  - A DIRECT import needs a DIRECT pin. A package present only as some other
    pin's dependency fails: that dependency can drop it in any release.
  - Skipped: the standard library, the repo's own modules (any top-level name
    in the repo or in ``src/``, ``scripts/``, ``tools/``, ``tests/``), relative
    imports, imports inside ``try:`` with an ``ImportError`` handler, notebook
    ``%`` / ``!`` lines, and a line marked ``# noqa: requirements``.
  - An import name that differs from its package name is mapped by ``ALIASES``,
    or by a note on the pin: ``pyshp==3.1.6  # import: shapefile``.

⚠️ Blind to what is never imported: CLI tools (pip-audit), packages loaded by
name at runtime (pandas' openpyxl engine), ``importlib`` imports. Before a
venv rebuild, the freeze diff in docs/TOKEN_EFFICIENCY.md §Disk covers those.

Exit codes: 0 ok; 7 an import is not pinned (2 is argparse's).

Usage:
    python scripts/check_requirements.py
    python scripts/check_requirements.py --root /path/to/checkout
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = "requirements.txt"
LOCAL_DIRS = ("src", "scripts", "tools", "tests")

EXIT_OK = 0
EXIT_FAIL = 7

# Import name -> package name, where they differ. Only names seen in the owner's
# projects or common in data work; a project adds its own with "# import: x".
ALIASES = {
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "fitz": "pymupdf",
    "googleapiclient": "google-api-python-client",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "osgeo": "gdal",
    "shapefile": "pyshp",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "umap": "umap-learn",
    "yaml": "pyyaml",
}

# ``google`` is a namespace several packages share; the next part names the package.
GOOGLE = {"auth": "google-auth", "oauth2": "google-auth", "protobuf": "protobuf",
          "genai": "google-genai", "api_core": "google-api-core"}

PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
IMPORT_NOTE = re.compile(r"#\s*import:\s*([A-Za-z0-9_., ]+)")
NOQA = re.compile(r"#\s*noqa:\s*requirements\b")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned(root: Path) -> tuple[set[str], dict[str, str]]:
    """Normalised pinned package names, and import -> package from "# import:" notes."""
    names: set[str] = set()
    notes: dict[str, str] = {}
    path = root / REQUIREMENTS
    if not path.exists():
        return names, notes
    for line in path.read_text().splitlines():
        if line.lstrip().startswith(("#", "-")):
            continue
        m = PIN.match(line)
        if not m:
            continue
        names.add(norm(m.group(1)))
        if note := IMPORT_NOTE.search(line):
            for imp in note.group(1).replace(",", " ").split():
                notes[imp] = m.group(1)
    return names, notes


def local_names(root: Path) -> set[str]:
    names = {p.stem for p in root.iterdir()}
    for d in LOCAL_DIRS:
        if (root / d).is_dir():
            names |= {p.stem for p in (root / d).iterdir()}
    return names


def tracked(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "--", "*.py", "*.ipynb"],
                         cwd=root, capture_output=True, text=True, check=True).stdout
    return [root / p for p in out.split("\0") if p]


def source(path: Path) -> str:
    text = path.read_text(errors="replace")
    if path.suffix != ".ipynb":
        return text
    cells = json.loads(text).get("cells", [])
    code = "\n".join("".join(c.get("source", [])) for c in cells if c.get("cell_type") == "code")
    # Magics and shell lines aren't Python; blank them so line numbers hold.
    return "\n".join("" if l.lstrip().startswith(("%", "!")) else l for l in code.splitlines())


def _guarded(tree: ast.AST) -> set[int]:
    """ids of import nodes inside a try whose handlers catch ImportError."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
                "ImportError" in ast.dump(h) or "ModuleNotFoundError" in ast.dump(h)
                for h in node.handlers):
            for stmt in node.body:
                ids |= {id(n) for n in ast.walk(stmt)}
    return ids


def imports(text: str) -> list[tuple[int, str]]:
    """(line, top-level module) for each absolute, unguarded import. Raises SyntaxError."""
    tree = ast.parse(text)
    lines = text.splitlines()
    guarded = _guarded(tree)
    found = []
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # Keep the imported names: "from google.cloud import storage" names its package there.
            mods = [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        if NOQA.search(lines[node.lineno - 1]):
            continue
        found += [(node.lineno, m) for m in mods]
    return found


def package_for(module: str, notes: dict[str, str]) -> str:
    top, _, rest = module.partition(".")
    if top in notes:
        return notes[top]
    if top == "google" and rest:
        parts = rest.split(".")
        if parts[0] == "cloud" and len(parts) > 1:
            return f"google-cloud-{parts[1]}"
        return GOOGLE.get(parts[0], f"google-{parts[0]}")
    return ALIASES.get(top, top)


def check(root: Path) -> list[str]:
    pins, notes = pinned(root)
    local = local_names(root)
    failures = []
    for path in tracked(root):
        rel = path.relative_to(root)
        try:
            found = imports(source(path))
        except (SyntaxError, ValueError) as e:
            # Unreadable is not "no imports": say so rather than pass silently.
            failures.append(f"{rel}: cannot parse ({e.__class__.__name__}); fix it or untrack it")
            continue
        for line, module in found:
            mod = module.split(".")[0]
            if mod in sys.stdlib_module_names or mod in local:
                continue
            package = package_for(module, notes)
            msg = (f"{rel}:{line}: imports {mod!r}, but {package!r} "
                   f"is not pinned in {REQUIREMENTS}")
            if norm(package) not in pins and msg not in failures:
                failures.append(msg)
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=ROOT)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures = check(args.root)
    for f in failures:
        print(f"FAIL  {f}")
    if failures:
        print(f"\n{len(failures)} unpinned import(s). Pin the package in {REQUIREMENTS} "
              f"(add '# import: <name>' if the names differ), or mark a deliberate "
              f"exception '# noqa: requirements'.")
        return EXIT_FAIL
    print(f"OK  {REQUIREMENTS}: every third-party import is pinned")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
