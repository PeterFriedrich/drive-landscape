"""Inventory Google Drive: one row per file and folder, metadata only.

    python -m src.inventory [--out data/raw/private/inventory] [--config-dir DIR]

Writes <out>/<YYYY-MM-DD>/files.jsonl.gz and manifest.json. The output is
private (names, ids) and belongs in the private data repo — see data/DATA.md.

Read-only: the OAuth scope cannot change anything in Drive.
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("inventory")

# drive.readonly rather than drive.metadata.readonly: the text-export step needs
# file content, and one consent is better than two.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER = "application/vnd.google-apps.folder"
FIELDS = (
    "id,name,mimeType,parents,ownedByMe,owners(emailAddress),shared,trashed,"
    "createdTime,modifiedTime,viewedByMeTime,size,quotaBytesUsed,md5Checksum,"
    "webViewLink,shortcutDetails"
)
DEFAULT_CONFIG_DIR = Path(os.environ.get("DRIVE_LANDSCAPE_CONFIG", "~/.config/drive-landscape")).expanduser()
DEFAULT_OUT = Path("data/raw/private/inventory")


def build_service(config_dir: Path):
    """OAuth client in config_dir/credentials.json; the token is cached beside it.

    Both stay outside the repo. Imports are local so tests need no Google libs.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_path = config_dir / "token.json"
    creds = Credentials.from_authorized_user_file(token_path, SCOPES) if token_path.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(config_dir / "credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    token_path.chmod(0o600)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_files(service):
    """Every file and folder the account can see in My Drive and Shared with me, trashed included."""
    token = None
    while True:
        page = service.files().list(
            corpora="user",
            spaces="drive",
            pageSize=1000,
            fields=f"nextPageToken,incompleteSearch,files({FIELDS})",
            pageToken=token,
        ).execute()
        if page.get("incompleteSearch"):
            raise RuntimeError("Drive reported an incomplete listing; refusing to write a partial inventory")
        yield from page.get("files", [])
        token = page.get("nextPageToken")
        if not token:
            return


def summarize(files: list[dict]) -> dict:
    """Counts for the manifest. Orphans and shared files are counted, never dropped."""
    ids = {f["id"] for f in files}
    no_parent = [f for f in files if not f.get("parents")]
    # A parent we cannot see: someone else's folder, shared one file at a time.
    parent_unseen = [f for f in files if f.get("parents") and not any(p in ids for p in f["parents"])]
    return {
        "total": len(files),
        "folders": sum(f["mimeType"] == FOLDER for f in files),
        "owned_by_me": sum(bool(f.get("ownedByMe")) for f in files),
        "not_owned_by_me": sum(not f.get("ownedByMe") for f in files),
        "trashed": sum(bool(f.get("trashed")) for f in files),
        "no_parent": len(no_parent),
        "no_parent_owned_by_me": sum(bool(f.get("ownedByMe")) for f in no_parent),
        "parent_not_in_inventory": len(parent_unseen),
        "bytes": sum(int(f.get("size", 0)) for f in files),
        "by_mime_type": dict(Counter(f["mimeType"] for f in files).most_common()),
    }


def write_snapshot(files: list[dict], out: Path, day: date) -> Path:
    dest = out / day.isoformat()
    dest.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest / "files.jsonl.gz", "wt", encoding="utf-8") as fh:
        for f in files:
            fh.write(json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields": FIELDS,
        **summarize(files),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    files = list(list_files(build_service(args.config_dir)))
    dest = write_snapshot(files, args.out, date.today())
    summary = summarize(files)
    summary.pop("by_mime_type")
    log.info("wrote %s %s", dest, json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
