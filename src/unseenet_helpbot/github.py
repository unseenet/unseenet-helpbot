"""What the bot knows from GitHub: every public repository of the
organisation - its Markdown files, issues and pull requests.

The list of repositories is read again at every sync, so a new repository is
known at the next one. Private repositories are never read. Everything is
kept in one JSON cache, so a restart does not fetch it all again.

Only the standard library is used. Without a token GitHub allows 60 requests
an hour, which is enough for a sync every few hours of a small organisation;
set a token (read-only, public repositories) for more.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .docs import Chunk, chunk_text, tokens, url_for

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_FILE = 300_000
SKIP_PARTS = {"node_modules", "build", "dist", ".venv", "venv", "site", "tests",
              "ISSUE_TEMPLATE", "PULL_REQUEST_TEMPLATE"}
SKIP_NAMES = {"LICENSE.md", "NOTICE.md", "CODE_OF_CONDUCT.md"}
MAX_BODY = 6000           # of an issue or pull request

Fetch = Callable[[str], bytes]


@dataclass
class GitHub:
    org: str = "unseenet"
    token: str = ""
    exclude: set[str] = field(default_factory=set)
    issues: bool = True
    fetch: Fetch | None = None       # for tests

    def _get(self, url: str) -> bytes:
        if self.fetch is not None:
            return self.fetch(url)
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "unseenet-helpbot"})
        if self.token and url.startswith(API):
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def _json(self, url: str):
        return json.loads(self._get(url))

    def _pages(self, url: str, limit: int = 30) -> list:
        out = []
        sep = "&" if "?" in url else "?"
        for page in range(1, limit + 1):
            batch = self._json(f"{url}{sep}per_page=100&page={page}")
            out.extend(batch)
            if len(batch) < 100:
                break
        return out

    def repos(self) -> list[dict]:
        rs = self._pages(f"{API}/orgs/{self.org}/repos?type=public")
        return [r for r in rs if not r.get("private") and r["name"] not in self.exclude
                and not r.get("fork")]

    def sync(self, log=print) -> dict:
        """Everything, fresh: {"synced": time, "repos": [{name, archived, files, issues}]}."""
        out = {"synced": time.time(), "repos": []}
        for r in self.repos():
            name, branch = r["name"], r.get("default_branch") or "main"
            entry = {"name": name, "archived": bool(r.get("archived")),
                     "description": r.get("description") or "", "files": {}, "issues": []}
            try:
                tree = self._json(f"{API}/repos/{self.org}/{name}/git/trees/{branch}?recursive=1")
                for item in tree.get("tree", []):
                    p = item["path"]
                    if (item["type"] != "blob" or not p.endswith(".md")
                            or set(p.split("/")) & SKIP_PARTS or p.split("/")[-1] in SKIP_NAMES
                            or item.get("size", 0) > MAX_FILE):
                        continue
                    raw = self._get(f"{RAW}/{self.org}/{name}/{branch}/{urllib.parse.quote(p)}")
                    entry["files"][p] = raw.decode("utf-8", "replace")
                if self.issues:
                    for it in self._pages(f"{API}/repos/{self.org}/{name}/issues?state=all"):
                        entry["issues"].append(_issue(it))
            except (OSError, ValueError, KeyError) as exc:
                log(f"github: {name}: {exc}")
                continue
            out["repos"].append(entry)
            log(f"github: {name}: {len(entry['files'])} files, {len(entry['issues'])} issues and PRs")
        return out


def _issue(it: dict) -> dict:
    pr = it.get("pull_request")
    if pr:
        state = "merged" if pr.get("merged_at") else it["state"]
    else:
        state = "fixed" if it.get("state_reason") == "completed" else (
            "not planned" if it.get("state_reason") == "not_planned" else it["state"])
    return {"number": it["number"], "pr": bool(pr), "title": it["title"], "state": state,
            "labels": [l["name"] for l in it.get("labels", [])],
            "milestone": (it.get("milestone") or {}).get("title"),
            "url": it["html_url"], "body": (it.get("body") or "")[:MAX_BODY],
            "updated": it.get("updated_at", "")}


def file_url(org: str, repo: str, path: str) -> str:
    if repo == "unseenet" and path.startswith("docs/"):
        return url_for(path[len("docs/"):])         # the docs are on unseenet.org
    if repo == "unseenet" and path.startswith("rfc/un-rfc-"):
        return url_for(path)
    return f"https://github.com/{org}/{repo}/blob/HEAD/{path}"


def chunks(cache: dict, org: str = "unseenet") -> list[Chunk]:
    out = []
    for r in cache.get("repos", []):
        name = r["name"]
        tag = f"{name} (archived)" if r.get("archived") else name
        if r.get("description"):                    # what the repository is, in one line
            title = f"The {tag} repository"
            text = (f"{title} (https://github.com/{org}/{name}): {r['description']}"
                    + (" It is archived: no longer worked on." if r.get("archived") else ""))
            c = Chunk(f"repo:{name}", title, "", text, f"https://github.com/{org}/{name}",
                      kind="repo", repo=tag)
            c.terms = _terms(f"{name} {name} {r['description']} {r['description']}")
            out.append(c)
        for path, text in r.get("files", {}).items():
            rel = f"{name}/{path}"
            out.extend(chunk_text(text, rel, file_url(org, name, path), repo=tag))
        for it in r.get("issues", []):
            what = "PR" if it["pr"] else "issue"
            bits = [it["state"]] + ([f"milestone {it['milestone']}"] if it["milestone"] else [])
            title = f"{tag} {what} #{it['number']} ({', '.join(bits)}): {it['title']}"
            head = title + (f"\nLabels: {', '.join(it['labels'])}" if it["labels"] else "")
            text = f"{head}\n\n{it['body']}".strip()
            c = Chunk(f"gh:{name}#{it['number']}", title, "", text, it["url"], kind="issue")
            c.terms = _terms(f"{it['title']} {it['title']} {' '.join(it['labels'])} {it['body']}")
            out.append(c)
    return out


def _terms(text: str):
    from collections import Counter
    return Counter(tokens(text))


def load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache))
    tmp.replace(path)
