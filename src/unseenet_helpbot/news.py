"""The help bot's news (#13): releases told in plain language in its own feed,
``unseenet.help.news`` (created in unseenet, unseenet-helpbot#21).

``unseenet.announce`` stays the official word: the release notes, posted by CI. Here the
bot retells them for ordinary people - what changed for you, what node operators must
do, where to get it - from the release notes and the CHANGELOG, with the same rules as
its answers (only what the sources say, no dates, no security advice).

- Only stable releases: no drafts, prereleases, ``a``/``b``/``rc`` or ``dev`` tags.
- The first time, every release there is counts as seen: nothing old is ever posted.
- Releases within ``gather_hours`` of the first new one are one post (0.6.0 releases the
  core, the clients and the services together).
- If the model fails or does not know, nothing is posted; it tries again at the next
  look, ``max_tries`` times.

The comments under its posts are answered by the bot's own answering (``look_once`` on
the news group).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

NAMES = {"unseenet": "Unseenet", "unseenet-gui": "the graphical client",
         "unseenet-tui": "the terminal client", "unseenet-gateway": "the gateway",
         "unseenet-entrance": "the web entrance", "unseenet-bots": "the bots",
         "unseenet-portable": "the portable builds", "unseenet-bootable": "the bootable images",
         "unseenet-import": "the importer", "unseenet-helpbot": "the help bot"}
_TEST = re.compile(r"(a|b|rc|dev|alpha|beta)\d*$", re.I)

WRITE = """You write the Unseenet help bot's news feed: a short post that tells ordinary \
people what is new in a release of Unseenet, a discussion network over Tor.

Rules:
- Use ONLY the release notes and changelog below. Do not add anything they do not say: \
no features, no dates, no plans, no advice about anonymity or security.
- Say what is new for an ordinary user, the way you do it in the graphical client \
(menus, the palette); the terminal client in a sentence if useful.
- If the notes say node operators must do something (update the nodes first, for \
example), say so in a separate short paragraph.
- End with where to get it: the links given below.
- English, Markdown: no heading (the subject is the headline), a few short paragraphs \
or a short list. At most about 200 words.
- If the notes say nothing an ordinary person would care about, reply with exactly \
DONT_KNOW."""


@dataclass
class Release:
    repo: str
    tag: str
    name: str
    body: str
    published: str
    url: str

    @property
    def key(self) -> str:
        return f"{self.repo}:{self.tag}"

    @property
    def version(self) -> str:
        return self.tag.lstrip("v")

    @property
    def when(self) -> float:
        try:
            return datetime.fromisoformat(self.published.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0


def stable(r: dict) -> bool:
    """A release people should hear about: not a draft, prerelease or test version."""
    tag = str(r.get("tag", ""))
    return (bool(tag) and not r.get("draft") and not r.get("prerelease") and tag != "dev"
            and not _TEST.search(tag.split("+")[0]))


def releases(cache: dict) -> list[Release]:
    out = []
    for repo in cache.get("repos", []):
        for r in repo.get("releases", []):
            if stable(r):
                out.append(Release(repo["name"], r["tag"], r.get("name") or r["tag"],
                                   r.get("body") or "", r.get("published") or "", r.get("url") or ""))
    return sorted(out, key=lambda r: r.when)


@dataclass
class NewsState:
    path: Path | None
    seen: set[str] = field(default_factory=set)
    tries: dict[str, int] = field(default_factory=dict)
    posted: list[dict] = field(default_factory=list)
    fresh: bool = True

    @classmethod
    def load(cls, path) -> "NewsState":
        path = Path(path)
        try:
            d = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls(path)
        return cls(path, set(d.get("seen", [])), dict(d.get("tries", {})), list(d.get("posted", [])),
                   fresh=False)

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen": sorted(self.seen), "tries": self.tries,
                                   "posted": self.posted[-200:]}))
        tmp.replace(self.path)


def due(cache: dict, state: NewsState, now: float | None = None, gather_hours: float = 2.0,
        max_tries: int = 3) -> list[Release]:
    """The releases to post now, together; [] when there are none or the window is open.
    The first time, everything there is is marked seen."""
    now = time.time() if now is None else now
    every = releases(cache)
    if state.fresh:
        state.seen |= {r.key for r in every}
        state.fresh = False
        state.save()
        return []
    new = [r for r in every if r.key not in state.seen and state.tries.get(r.key, 0) < max_tries]
    if not new:
        return []
    first = min(r.when for r in new)
    if now - first < gather_hours * 3600:
        return []                                     # more may come in the same round
    return [r for r in new if r.when <= first + gather_hours * 3600]


def subject(batch: list[Release]) -> str:
    """'What's new: Unseenet 0.6.0, the graphical client 0.3.0 and the gateway 0.2.0'."""
    names = [f"{NAMES.get(r.repo, r.repo)} {r.version}" for r in batch]
    names[0] = names[0][0].upper() + names[0][1:]
    said = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"What's new: {said}"[:200]


def changelog_section(cache: dict, repo: str, version: str) -> str:
    """The CHANGELOG's section for ``version`` in ``repo``, as the cache has the file."""
    r = next((x for x in cache.get("repos", []) if x["name"] == repo), {})
    text = r.get("files", {}).get("CHANGELOG.md", "")
    m = re.search(rf"^## \[?v?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def sources(batch: list[Release], cache: dict, limit: int = 3500) -> str:
    out = []
    for r in batch:
        log = changelog_section(cache, r.repo, r.version)
        part = (f"## {NAMES.get(r.repo, r.repo)} {r.version}\nRelease notes:\n{r.body.strip()[:limit]}"
                + (f"\n\nChangelog:\n{log[:limit]}" if log else "") + f"\n\nWhere to get it: {r.url}")
        out.append(part)
    return "\n\n".join(out)


async def write(model, batch: list[Release], cache: dict, announce: str = "") -> str | None:
    """The post's body, or None when the model fails or has nothing to say."""
    prompt = sources(batch, cache)
    try:
        text = (await model.complete([{"role": "system", "content": WRITE},
                                      {"role": "user", "content": prompt}])).strip()
    except (OSError, ValueError, KeyError):
        return None
    if not text or "DONT_KNOW" in text.upper()[:40].replace(" ", "_") or len(text) < 40:
        return None
    head = ("The official release notes: " + announce + "\n\n") if announce else ""
    return head + text + "\n"


async def post_news(session, group: str, model, cache: dict, state: NewsState, *,
                    gather_hours: float = 2.0, max_tries: int = 3, dry_run: bool = False,
                    log=print, now: float | None = None) -> str | None:
    """Post what is due, if anything; returns the Message-ID (or the text, dry run)."""
    batch = due(cache, state, now, gather_hours, max_tries)
    if not batch:
        return None
    announce = next((r.url for r in batch if r.repo == "unseenet"), batch[0].url)
    body = await write(model, batch, cache, announce)
    if body is None:
        for r in batch:
            state.tries[r.key] = state.tries.get(r.key, 0) + 1
        state.save()
        log(f"news: nothing written for {', '.join(r.key for r in batch)}; again next time")
        return None
    subj = subject(batch)
    if dry_run:
        log(f"news: would post {subj!r}:\n{body}")
        return body
    msgid = await session.post(group, subj, body)
    state.seen |= {r.key for r in batch}
    state.posted.append({"id": msgid, "releases": [r.key for r in batch]})
    state.save()
    log(f"news: posted {msgid}: {subj}")
    return msgid
