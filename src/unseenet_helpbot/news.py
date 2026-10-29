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
- The model writes one short section per release, so each prompt fits a small model on
  a CPU (asking for ten releases at once timed out, unseenet-helpbot#29). Sections are kept
  in the state as they are written, a few per look, and the post goes out when all are
  there. The bot puts them together itself, each under its own heading tagged with the
  repository (``#unseenet-gui``).
- If that post cannot be posted, each release gets its own post instead, tagged the same way.
- Raw release notes are never posted: they are in ``unseenet.announce``. A release the
  model fails on ``max_tries`` times is left out (and logged); one it has nothing to say
  about (DONT_KNOW) is left out too.

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
         "unseenet-import": "the importer", "unseenet-helpbot": "the help bot",
         "unseenet-watchman": "the watchman", "unseenet-stats": "the statistics site",
         "unseenet-docs": "the docs", "unseenet-mcp": "the MCP server",
         "unseenet-demo": "the demo"}
_TEST = re.compile(r"(a|b|rc|dev|alpha|beta)\d*$", re.I)
_VERSION_TAG = re.compile(r"^v\d+(\.\d+)*(\.post\d+)?$")   # not chiavdf-..., web-..., dev

WRITE = """You write one section of the Unseenet help bot's news feed: a few sentences \
that tell ordinary people what is new in ONE release of one part of Unseenet, a \
discussion network over Tor. Several such sections are put together into one post.

Rules:
- Use ONLY the release notes below. Do not add anything they do not say: no features, \
no dates, no plans, no advice about anonymity or security.
- Say what is new for an ordinary user, the way you do it in the graphical client \
(menus, the palette); the terminal client in a sentence if useful.
- If the notes say node operators must do something (update the nodes first, for \
example), say so in one sentence.
- English, Markdown, no heading and no links (they are added). At most about 80 words: \
two or three sentences, or a short list of at most four points.
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
    return (bool(_VERSION_TAG.match(tag)) and not r.get("draft") and not r.get("prerelease")
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
    written: dict[str, str] = field(default_factory=dict)   # key -> section; "" = nothing to say

    @classmethod
    def load(cls, path) -> "NewsState":
        path = Path(path)
        try:
            d = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls(path)
        return cls(path, set(d.get("seen", [])), dict(d.get("tries", {})), list(d.get("posted", [])),
                   fresh=False, written=dict(d.get("written", {})))

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen": sorted(self.seen), "tries": self.tries,
                                   "posted": self.posted[-200:], "written": self.written}))
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
    batch = sorted(batch, key=lambda r: r.repo != "unseenet")     # the core first
    names = [f"{NAMES.get(r.repo, r.repo)} {r.version}" for r in batch]
    names[0] = names[0][0].upper() + names[0][1:]
    if len(names) > 3:                                # 'Unseenet 0.6.2, ... and 8 more'
        names = names[:2] + [f"{len(names) - 2} more"]
    said = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"What's new: {said}"[:200]


def changelog_section(cache: dict, repo: str, version: str) -> str:
    """The CHANGELOG's section for ``version`` in ``repo``, as the cache has the file."""
    r = next((x for x in cache.get("repos", []) if x["name"] == repo), {})
    text = r.get("files", {}).get("CHANGELOG.md", "")
    m = re.search(rf"^## \[?v?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def source(r: Release, cache: dict, limit: int = 2500) -> str:
    """What the model writes one release's section from: the release notes, or the
    CHANGELOG section when the notes say little. Kept short for a small model on a CPU."""
    text = r.body.strip()
    if len(text) < 400:
        log = changelog_section(cache, r.repo, r.version)
        if log:
            text = (text + "\n\nChangelog:\n" + log).strip()
    if len(text) > limit:
        text = text[:limit].rsplit("\n", 1)[0] + "\n..."
    return f"Release: {NAMES.get(r.repo, r.repo)} {r.version}\n\nRelease notes:\n{text}"


async def write_section(model, r: Release, cache: dict) -> str | None:
    """One release's section; "" when the model has nothing to say, None when it fails."""
    try:
        text = (await model.complete([{"role": "system", "content": WRITE},
                                      {"role": "user", "content": source(r, cache)}],
                                     max_tokens=250)).strip()
    except Exception as exc:                          # timeouts, connection, bad answers
        return _fail(exc)
    if "DONT_KNOW" in text.upper()[:40].replace(" ", "_"):
        return ""
    text = re.sub(r"^#+ .*\n+", "", text).strip()     # no heading of its own
    return text if len(text) >= 40 else None


_last_error = [""]                                    # why the last section failed, for the log


def _fail(exc: BaseException) -> None:
    _last_error[0] = f"{type(exc).__name__}: {exc}"
    return None


def tag(repo: str) -> str:
    return "#" + repo


def heading(r: Release) -> str:
    name = NAMES.get(r.repo, r.repo)
    return f"{name[0].upper()}{name[1:]} {r.version} · {tag(r.repo)}"


def section(r: Release, text: str) -> str:
    return f"### {heading(r)}\n\n{text}\n\n[Release notes and downloads]({r.url})"


def body(ready: list[tuple[Release, str]]) -> str:
    """The whole post, put together by the bot: one section per release."""
    intro = ("" if len(ready) == 1 else
             f"{len(ready)} parts of Unseenet were released together. Here is what is new, "
             "in plain words.\n\n")
    return intro + "\n\n".join(section(r, t) for r, t in ready) + (
        "\n\nThe official release notes are in the group unseenet.announce. "
        "Ask here in the comments if something is unclear.\n")


def single_subject(r: Release) -> str:
    return f"[{r.repo}] What's new: {NAMES.get(r.repo, r.repo)} {r.version}"[:200]


async def post_news(session, group: str, model, cache: dict, state: NewsState, *,
                    gather_hours: float = 2.0, max_tries: int = 3, dry_run: bool = False,
                    log=print, now: float | None = None, per_look: int = 4) -> str | None:
    """Write what is due, ``per_look`` sections at a time, and post when all are written.
    Returns the Message-ID of the (first) post, or the text in a dry run."""
    batch = due(cache, state, now, gather_hours, max_tries)
    if not batch:
        return None
    todo = [r for r in batch if r.key not in state.written]
    for r in todo[:per_look]:
        text = await write_section(model, r, cache)
        if text is None:
            state.tries[r.key] = state.tries.get(r.key, 0) + 1
            log(f"news: could not write {r.key} (try {state.tries[r.key]} of {max_tries}): "
                f"{_last_error[0] or 'empty or too short answer'}")
            _last_error[0] = ""
        else:
            state.written[r.key] = text
    pending = [r for r in batch
               if r.key not in state.written and state.tries.get(r.key, 0) < max_tries]
    if pending:
        state.save()
        log(f"news: {len(batch) - len(pending)} of {len(batch)} written; "
            f"the rest next time ({', '.join(r.key for r in pending)})")
        return None
    given_up = [r.key for r in batch if r.key not in state.written]
    if given_up:
        log(f"news: gave up on {', '.join(given_up)} - left out of the post")
    ready = [(r, state.written[r.key]) for r in batch if state.written.get(r.key)]
    if not ready:
        _done(state, batch, None)
        log("news: nothing to tell about " + ", ".join(r.key for r in batch))
        return None
    text = body(ready)
    if dry_run:
        log(f"news: would post {subject([r for r, _ in ready])!r}:\n{text}")
        return text
    try:
        msgid = await session.post(group, subject([r for r, _ in ready]), text)
        log(f"news: posted {msgid}: {subject([r for r, _ in ready])}")
    except Exception as exc:                          # too big, refused: one post each
        log(f"news: the gathered post failed ({exc}); posting each release on its own")
        msgid = None
        for r, t in ready:
            one = (f"{t}\n\n[Release notes and downloads]({r.url}) · {tag(r.repo)}\n")
            mid = await session.post(group, single_subject(r), one)
            msgid = msgid or mid
            log(f"news: posted {mid}: {single_subject(r)}")
    _done(state, batch, msgid)
    return msgid


def _done(state: NewsState, batch: list[Release], msgid: str | None) -> None:
    state.seen |= {r.key for r in batch}
    for r in batch:
        state.written.pop(r.key, None)
    if msgid:
        state.posted.append({"id": msgid, "releases": [r.key for r in batch]})
    state.save()
