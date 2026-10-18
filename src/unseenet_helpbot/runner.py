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
import os
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unseenet.client.session import Session, SessionError
from unseenet.core.vault import Vault

from . import bot, llm
from .docs import Index

PASS_ENV = "UNSEENET_VAULT_PASSPHRASE"


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


def load_config(path: str | Path) -> Config:
    path = Path(path).expanduser()
    d = tomllib.loads(path.read_text())
    b, m = d.get("bot", {}), d.get("model", {})
    after = b.get("answer_unanswered_after_minutes", 30)
    try:
        return Config(
            vault=Path(b["vault"]).expanduser(), group=b["group"],
            docs=[str(Path(p).expanduser()) for p in b["docs"]],
            state_file=Path(b.get("state_file", "~/.local/state/unseenet-helpbot/state.json")).expanduser(),
            name=b.get("name", "Unseenet help (bot)"), nodes=b.get("nodes", []),
            poll=float(b.get("poll_seconds", 120)), rewrite=bool(m.get("rewrite_query", True)),
            rules=bot.Rules(triggers=b.get("triggers", ["@helpbot"]),
                            unanswered_after=timedelta(minutes=after) if after else None,
                            max_per_hour=int(b.get("max_per_hour", 10)),
                            max_per_thread=int(b.get("max_per_thread", 3)),
                            ignore_keys=set(b.get("ignore_keys", []))),
            model=llm.Model(base_url=m.get("base_url", llm.Model.base_url),
                            model=m.get("model", llm.Model.model),
                            api_key=os.environ.get(m.get("api_key_env", ""), "") if m.get("api_key_env") else "",
                            timeout=float(m.get("timeout", 300))))
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


async def cmd_ask(cfg: Config, question: str) -> None:
    index = Index.from_folders(cfg.docs)
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
    todo = bot.select(msgs, me=me, mine=s.my_message_ids(), rules=cfg.rules, state=state)
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
    index, built = Index.from_folders(cfg.docs), datetime.now(timezone.utc)
    print(f"{len(index.chunks)} sections of docs; following {cfg.group}")
    try:
        while True:
            if datetime.now(timezone.utc) - built > timedelta(hours=1):   # docs may have changed
                index, built = Index.from_folders(cfg.docs), datetime.now(timezone.utc)
            try:
                await look_once(s, cfg, index, state, dry_run)
            except (SessionError, OSError, ConnectionError) as exc:
                print(f"could not read the group: {exc}")
            if once:
                break
            await asyncio.sleep(cfg.poll)
    finally:
        await s.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="unseenet-helpbot", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--config", default="helpbot.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="make the bot's vault and key, and follow the group")
    a = sub.add_parser("ask", help="answer one question from the docs, without the network")
    a.add_argument("question")
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
        else:
            asyncio.run(cmd_run(cfg, args.once, args.dry_run))
    except KeyboardInterrupt:
        sys.exit(130)
