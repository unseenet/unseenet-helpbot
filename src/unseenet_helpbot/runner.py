"""Run the help bot.

    unseenet-helpbot -c helpbot.toml init              # a vault with the bot's key
    unseenet-helpbot -c helpbot.toml ask "How do I run a node?"   # no network
    unseenet-helpbot -c helpbot.toml run --once        # look once, answer, stop
    unseenet-helpbot -c helpbot.toml run               # keep following the group

The vault's passphrase is read from UNSEENET_VAULT_PASSPHRASE.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import os
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unseenet.client.runtime import SERVICE_RIPEN_TO, ClientRuntime
from unseenet.client.session import Session, SessionError
from unseenet.core.vault import Vault

from . import bot, github, llm
from .docs import Index
from .threads import thread_chunks

_BOTS: set[str] = set()        # keys whose profile carries the bot mark, as found so far
_SEEN: set[str] = set()        # keys already looked up

PASS_ENV = "UNSEENET_VAULT_PASSPHRASE"
ABOUT = """\
# Unseenet help :robot:

Ask me anything about **[Unseenet](https://unseenet.org)** in
[unseenet.help](unseenet:join?g=unseenet.help@ph5fc5hop5232qsz) -
getting started, keys and ripening, nodes, groups, following and posting.

## How I work

- I answer from the [guide](https://unseenet.org/guide/), the
  [UN-RFCs](https://unseenet.org/spec/) and the project's
  [issues on GitHub](https://github.com/unseenet)
- I am a bot and can be wrong - people in the group may correct me
- Write in English or Danish - *jeg svarer også på dansk*

## Not me you need?

The project talks in [unseenet](unseenet:join?g=unseenet@ph5fc5hop5232qsz),
news are in [unseenet.announce](unseenet:join?g=unseenet.announce@ph5fc5hop5232qsz),
and the project is run by [Andreas](unseenet:b4xkhrco5yii4dw7).
"""   # the public profile, Markdown (UN-RFC 0022 section 4.1)
PROFILE_LINKS = [{"kind": "web", "value": "https://unseenet.org/guide/"},
                 {"kind": "github", "value": "https://github.com/unseenet/unseenet-helpbot"}]
PICTURE = "helpbot-profile.webp"  # 128 px, ready to publish; source assets/helpbot.svg
PICTURE_ALT = "A robot head whose face is the Unseenet eye"


@dataclass
class Config:
    vault: Path
    group: str
    docs: list[str]
    state_file: Path
    name: str = "Unseenet help (bot)"
    nodes: list[str] = field(default_factory=list)
    poll: float = 120.0
    rewrite: bool = True
    rules: bot.Rules = field(default_factory=bot.Rules)
    model: llm.Model = field(default_factory=llm.Model)
    github: github.GitHub | None = None
    github_cache: Path = Path("~/.local/state/unseenet-helpbot/github.json").expanduser()
    github_hours: float = 6.0
    learn: bool = True          # answer from earlier answered threads of the group too (#5)


def load_config(path: str | Path) -> Config:
    path = Path(path).expanduser()
    d = tomllib.loads(path.read_text())
    b, m, g = d.get("bot", {}), d.get("model", {}), d.get("github", {})
    after = b.get("answer_unanswered_after_minutes", 30)
    chat_after = b.get("answer_unanswered_chat_after_minutes", 10)
    try:
        return Config(
            vault=Path(b["vault"]).expanduser(), group=b["group"],
            docs=[str(Path(p).expanduser()) for p in b.get("docs", [])],
            state_file=Path(b.get("state_file", "~/.local/state/unseenet-helpbot/state.json")).expanduser(),
            name=b.get("name", "Unseenet help (bot)"), nodes=b.get("nodes", []),
            poll=float(b.get("poll_seconds", 120)), rewrite=bool(m.get("rewrite_query", True)),
            rules=bot.Rules(triggers=b.get("triggers", ["@helpbot"]),
                            unanswered_after=timedelta(minutes=after) if after else None,
                            chat_unanswered_after=timedelta(minutes=chat_after) if chat_after else None,
                            max_per_hour=int(b.get("max_per_hour", 10)),
                            max_per_thread=int(b.get("max_per_thread", 3)),
                            ignore_keys=set(b.get("ignore_keys", []))),
            model=llm.Model(base_url=m.get("base_url", llm.Model.base_url),
                            model=m.get("model", llm.Model.model),
                            api_key=os.environ.get(m.get("api_key_env", ""), "") if m.get("api_key_env") else "",
                            timeout=float(m.get("timeout", 300))),
            github=github.GitHub(org=g.get("org", "unseenet"), issues=bool(g.get("issues", True)),
                                 exclude=set(g.get("exclude", [])),
                                 token=os.environ.get(g.get("token_env", ""), "") if g.get("token_env") else "")
                   if g.get("enabled", True) and g else None,
            github_cache=Path(g.get("cache_file", "~/.local/state/unseenet-helpbot/github.json")).expanduser(),
            github_hours=float(g.get("refresh_hours", 6)),
            learn=bool(b.get("learn_from_threads", True)))
    except KeyError as exc:
        raise SystemExit(f"{path}: missing {exc}") from exc


def open_session(cfg: Config, log=print) -> Session:
    pw = os.environ.get(PASS_ENV)
    if not pw:
        raise SystemExit(f"set {PASS_ENV} to the bot vault's passphrase")
    return Session(Vault.open(cfg.vault, pw), status=log)


def cmd_init(cfg: Config) -> None:
    s = open_session(cfg)
    if not s.has_identity():
        s.new_identity("helpbot", cfg.name)
    nodes = cfg.nodes
    if not nodes:
        from unseenet.core.poster import known_node_addresses
        nodes = known_node_addresses()
    for n in nodes:
        s.add_node(n)
    s.subscribe(cfg.group)
    s.save()
    print(f"vault:   {cfg.vault}")
    print(f"key:     {s.identity().key_text}")
    print(f"name:    {s.display_name()}")
    print(f"follows: {cfg.group} on {', '.join(s.nodes)}")


def build_index(cfg: Config) -> Index:
    """The local folders and, if configured, what was last fetched from GitHub."""
    chunks = Index.from_folders(cfg.docs).chunks if cfg.docs else []
    if cfg.github is not None:
        chunks += github.chunks(github.load_cache(cfg.github_cache), cfg.github.org)
    return Index(chunks)


async def sync_github(cfg: Config, force: bool = False, log=print) -> bool:
    """Fetch from GitHub if the cache is older than refresh_hours; True if it did."""
    if cfg.github is None:
        return False
    cache = github.load_cache(cfg.github_cache)
    if not force and datetime.now(timezone.utc).timestamp() - cache.get("synced", 0) < cfg.github_hours * 3600:
        return False
    try:
        fresh = await asyncio.get_running_loop().run_in_executor(None, cfg.github.sync, log)
    except (OSError, ValueError, KeyError) as exc:
        log(f"github: could not sync: {exc}")
        return False
    if fresh["repos"]:
        github.save_cache(cfg.github_cache, fresh)
    return True


async def cmd_ask(cfg: Config, question: str) -> None:
    index = build_index(cfg)
    ans = await llm.answer(cfg.model, index, question, rewrite=cfg.rewrite)
    if not ans.text:
        print("(not found in the docs)")
        for c in ans.sources:
            print("  looked at:", c.label)
        return
    print(ans.text)
    print("\nSources:")
    for i, c in enumerate(ans.sources, 1):
        print(f"{i}. {c.label} - {c.url}")


async def bot_keys(s: Session, keys: set[str]) -> set[str]:
    """The keys among ``keys`` whose profile carries the bot mark (UN-RFC 0022), read
    in one batch so the node does not learn whose profile is looked at (UN-RFC 0041)."""
    try:
        await s.prefetch_profiles(keys)
    except (SessionError, OSError, ConnectionError):
        pass                                    # what is cached still counts
    return {k for k in keys if s.is_bot(k)}


def profile() -> dict:
    """The public profile: the bot mark, Markdown About text, links and languages."""
    from unseenet.core.profiles import make_profile
    return make_profile(about=ABOUT, links=PROFILE_LINKS, lang=["en", "da"],
                        bot=True, markdown=True)


def _mark(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()[:16]


def profile_mark() -> str:
    """A short hash of the profile, kept in the vault: a changed text is published again."""
    import json
    return _mark(json.dumps(profile(), sort_keys=True).encode())


async def publish_profile(s: Session, log=print) -> None:
    """At start: publish the profile and the picture when they are new or have changed,
    so clients show the bot mark and the current text."""
    from importlib.resources import files

    from unseenet.core.profiles import make_picture
    if s.data.get("helpbot_profile") != profile_mark():
        try:
            await s.publish_profile(profile())
        except (SessionError, OSError, ConnectionError) as exc:
            log(f"could not publish the profile yet: {exc}")
            return
        s.data["helpbot_profile"] = profile_mark()
        s.save()
        log("published the profile with the bot mark")
    data = files("unseenet_helpbot").joinpath(PICTURE).read_bytes()
    mark = _mark(data)
    if s.data.get("helpbot_picture") != mark:
        try:              # already the middle square, 128 px WebP without metadata (8.1)
            await s.publish_picture(make_picture(data, "image/webp", 128, alt=PICTURE_ALT))
        except (SessionError, OSError, ConnectionError, ValueError) as exc:
            log(f"could not publish the picture yet: {exc}")
            return
        s.data["helpbot_picture"] = mark
        s.save()
        log("published the profile picture")


async def look_once(s: Session, cfg: Config, index: Index, state: bot.State,
                    dry_run: bool = False, log=print) -> int:
    """Fetch the group, answer what is due; returns how many answers were posted."""
    msgs = s.visible(await s.fetch_group(cfg.group))
    if state.fresh:                    # the first look: answer only what comes after it
        for m in msgs:
            state.done(m.message_id)
        state.fresh = False
        state.save()
        log(f"first look: {len(msgs)} earlier posts left alone")
        return 0
    me = {s.identity(n).key_text for n in s.data["identities"]}
    rules = cfg.rules
    bots = await bot_keys(s, {m.author_key for m in msgs
                              if m.message_id not in state.handled and m.author_key not in me})
    _BOTS.update(bots)
    if bots:
        rules = dataclasses.replace(rules, ignore_keys=rules.ignore_keys | bots)
    if cfg.learn:                       # earlier answered threads, as excerpts (#5)
        authors = {m.author_key for m in msgs if m.author_key} - me - _SEEN
        if authors:
            _BOTS.update(await bot_keys(s, authors))
            _SEEN.update(authors)
        learned = thread_chunks(msgs, cfg.group,
                                not_people=me | _BOTS | cfg.rules.ignore_keys)
        if index.replace("thread", learned):
            log(f"{len(learned)} answered threads of the group to answer from")
    todo = bot.select(msgs, me=me, mine=s.my_message_ids(), rules=rules, state=state)
    posted = 0
    for t in todo:
        q = bot.question_of(t.msg, cfg.rules)
        log(f"{t.why}: {t.msg.message_id} {q[:60]!r}")
        try:
            ans = await llm.answer(cfg.model, index, q, bot.thread_of(t.msg, msgs), rewrite=cfg.rewrite)
        except (OSError, ValueError, KeyError) as exc:
            log(f"  the model did not answer: {exc}")
            break                                  # try again next time
        if not ans.text and t.why == "unanswered":
            log("  not in the docs; staying quiet")
            state.done(t.msg.message_id)
            continue
        r = bot.reply(t.msg, ans if ans.text else None, s.group_kinds(cfg.group))
        if dry_run:
            log(f"  would post ({r.kind}) {r.subject!r}:\n{r.body}")
        else:
            try:
                msgid = await s.post(cfg.group, r.subject, r.body, references=r.references, kind=r.kind)
            except (SessionError, OSError, ConnectionError) as exc:
                log(f"  could not post: {exc}")
                break
            log(f"  posted {msgid}")
            state.answered(datetime.now(timezone.utc))
            posted += 1
        state.done(t.msg.message_id)
    state.save()
    return posted


async def cmd_run(cfg: Config, once: bool, dry_run: bool) -> None:
    s = open_session(cfg)
    if not s.has_identity():
        raise SystemExit("no key in the vault yet: run init first")
    if cfg.group not in s.data["subscribed"]:
        s.subscribe(cfg.group)
    state = bot.State.load(cfg.state_file)
    if dry_run:
        state.path = None                          # look, but remember nothing
    await sync_github(cfg)
    index, built = build_index(cfg), datetime.now(timezone.utc)
    print(f"{len(index.chunks)} sections of docs, issues and PRs; following {cfg.group}")
    ripening = None
    try:
        if not dry_run:
            await publish_profile(s)
            if not once:            # on to level 3, no surcharge; low priority (UN-RFC 0025)
                ripening = asyncio.create_task(ClientRuntime(s, ripen_to=SERVICE_RIPEN_TO).ripen())
        while True:
            if datetime.now(timezone.utc) - built > timedelta(hours=1):   # docs may have changed
                await sync_github(cfg)
                index, built = build_index(cfg), datetime.now(timezone.utc)
            try:
                await look_once(s, cfg, index, state, dry_run)
            except (SessionError, OSError, ConnectionError) as exc:
                print(f"could not read the group: {exc}")
            if once:
                break
            await asyncio.sleep(cfg.poll)
    finally:
        if ripening is not None:
            ripening.cancel()
        await s.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="unseenet-helpbot", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--config", default="helpbot.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="make the bot's vault and key, and follow the group")
    a = sub.add_parser("ask", help="answer one question from the docs, without the network")
    a.add_argument("question")
    sub.add_parser("sync", help="fetch the repositories, issues and PRs from GitHub now")
    r = sub.add_parser("run", help="follow the group and answer")
    r.add_argument("--once", action="store_true", help="look once, then stop")
    r.add_argument("--dry-run", action="store_true", help="show answers instead of posting")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    try:
        if args.cmd == "init":
            cmd_init(cfg)
        elif args.cmd == "ask":
            asyncio.run(cmd_ask(cfg, args.question))
        elif args.cmd == "sync":
            asyncio.run(sync_github(cfg, force=True))
            print(f"{len(build_index(cfg).chunks)} sections in all")
        else:
            asyncio.run(cmd_run(cfg, args.once, args.dry_run))
    except KeyboardInterrupt:
        sys.exit(130)
