"""Read-only Hypothesis import. Never edits or deletes remote annotations."""
from __future__ import annotations

import os
from urllib.parse import urlencode

from .network import get_json
from .store import atomic_write, document_id, encoded, now, read_json, safe_id


class HypothesisClient:
    def __init__(self, user, token=None, get=get_json, page_size=200):
        self.user = user
        self.account = f"acct:{user}@hypothes.is"
        self.token = token
        self.get = get
        self.page_size = page_size

    def annotations(self, public_only=False):
        if not public_only:
            if not self.token:
                raise ValueError("Authenticated sync needs a developer token. Run ./notes configure, or use sync --public-only.")
            profile = self.get("https://hypothes.is/api/profile", token=self.token)
            if profile.get("userid") != self.account:
                raise ValueError("The token belongs to another Hypothesis user; no data was imported")
        token = None if public_only else self.token
        rows = {}
        cursor = None
        expected = None
        while True:
            params = {"user": self.account, "limit": self.page_size, "sort": "created", "order": "asc"}
            if cursor:
                params["search_after"] = cursor
            response = self.get("https://hypothes.is/api/search?" + urlencode(params), token=token)
            batch = response.get("rows")
            total = response.get("total")
            if not isinstance(batch, list) or not isinstance(total, int) or total < 0:
                raise ValueError("Unexpected Hypothesis search response")
            if expected is None:
                expected = total
            if not batch:
                break
            for annotation in batch:
                safe_id(annotation.get("id"))
                if annotation.get("user") != self.account:
                    raise ValueError("API returned another user's annotation")
                document_id(annotation.get("uri"))
                if not isinstance(annotation.get("created"), str) or not annotation["created"]:
                    raise ValueError("API returned an annotation without a created timestamp")
                rows[annotation["id"]] = annotation
            following = batch[-1]["created"]
            if cursor is not None and following <= cursor:
                raise ValueError("Pagination did not advance; previous backups are intact")
            cursor = following
            if len(batch) < self.page_size:
                break
        # Timestamp-only cursors can skip ties across a page boundary. Count
        # validation makes this a visible failure, never a claimed full backup.
        if len(rows) != expected:
            raise ValueError(f"Incomplete scan ({len(rows)}/{expected}); the collection changed or a timestamp boundary collided. Retry; previous backups are intact.")
        check = self.get("https://hypothes.is/api/search?" + urlencode({"user": self.account, "limit": 1}), token=token)
        if check.get("total") != expected:
            raise ValueError("Annotation count changed during sync; retry for a complete snapshot")
        return list(rows.values())


def sync(vault, *, public_only=False, client=None):
    config = vault.config()
    user = config.get("user")
    if not user:
        raise ValueError("Initialize a vault first: ./notes init --user luke_ai")
    client = client or HypothesisClient(user, vault.token())
    # Serialize full imports with browser edits and other scheduled imports.
    # No records or success marker change until all network pages validate.
    with vault.lock():
        annotations = client.annotations(public_only=public_only)
        previous = vault.records("raw")
        changed = 0
        for annotation in annotations:
            if previous.get(annotation["id"]) != annotation:
                changed += 1
            atomic_write(vault.path("raw", annotation["id"]), encoded(annotation))
        vault.render()
        status = {"completed": now(), "scope": "public-only" if public_only else "authenticated", "fetched": len(annotations), "changed": changed, "retained_total": len(vault.records("raw")), "latest_ids": sorted(a["id"] for a in annotations)}
        # Missing IDs are retained: deletion, visibility changes, search lag,
        # and public-only scans must not destroy a previous private backup.
        snapshot = vault.snapshot(status)
        status["snapshot"] = str(snapshot.relative_to(vault.root))
        atomic_write(vault.root / ".local/last-sync.json", encoded(status))
    from .organization import auto_organize
    status["organization"] = auto_organize(vault)
    return status
