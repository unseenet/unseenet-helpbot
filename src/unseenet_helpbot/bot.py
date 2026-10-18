"""Which posts the bot answers, and how the answer looks.

The rules are plain functions over `Message`s so they can be tested without a
network: humans first, answer when asked, a question nobody answered after a
while, never itself or other bots, a limit per hour and per thread.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unseenet.client.session import Message, split_signature
from unseenet.core.groups import KIND_CHAT, KIND_POST

from .llm import Answer

SIGNATURE = ("I'm a bot that answers from the Unseenet documentation, and I can be wrong. "
             "A person may well answer too.")
NOT_FOUND = ("I couldn't find this in the documentation. Hopefully someone here knows - "
             "and if it's missing from the docs, that's worth an issue: "
             "https://github.com/unseenet/unseenet/issues")
KEEP = 2000                      # handled Message-IDs remembered


@dataclass
class Rules:
    triggers: list[str] = field(default_factory=lambda: ["@helpbot"])
    unanswered_after: timedelta | None = timedelta(minutes=30)   # None: only when asked
    chat_unanswered_after: timedelta | None = timedelta(minutes=10)   # chat moves faster
    max_per_hour: int = 10
    max_per_thread: int = 3
    ignore_keys: set[str] = field(default_factory=set)


@dataclass
class State:
    path: Path | None = None
    handled: list[str] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    fresh: bool = False          # first run: what is already there was asked before the bot came

    @classmethod
    def load(cls, path: str | Path) -> "State":
        path = Path(path).expanduser()
        try:
            d = json.loads(path.read_text())
        except (OSError, ValueError):
            d = {}
        return cls(path, d.get("handled", []), d.get("times", []), fresh=not d)

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handled = self.handled[-KEEP:]
        self.path.write_text(json.dumps({"handled": self.handled, "times": self.times[-200:]},
                                        indent=1))

    def done(self, msgid: str) -> None:
        if msgid not in self.handled:
            self.handled.append(msgid)

    def answered(self, now: datetime) -> None:
        self.times.append(now.isoformat())

    def in_last_hour(self, now: datetime) -> int:
        since = now - timedelta(hours=1)
        return sum(1 for t in self.times if datetime.fromisoformat(t) > since)


def own_text(msg: Message) -> str:
    """What the author wrote: no signature, no quoted lines."""
    body = split_signature(msg.body)[0]
    return "\n".join(ln for ln in body.split("\n") if not ln.lstrip().startswith(">")).strip()


_QWORDS = ("how ", "what ", "why ", "where ", "when ", "which ", "who ", "can ", "could ",
           "is ", "are ", "do ", "does ", "should ", "hvordan ", "hvad ", "hvorfor ", "hvor ",
           "hvornår ", "hvilken ", "hvilke ", "hvem ", "kan ", "skal ", "er ", "har ", "virker ")


def is_question(text: str) -> bool:
    """A chat line the bot may step in on: it asks something."""
    t = text.strip().lower()
    return "?" in t or t.startswith(_QWORDS) or "help" in t or "hjælp" in t


def is_bot(msg: Message) -> bool:
    # until profiles carry a bot flag in clients (unseenet/unseenet#163)
    return bool(re.search(r"\(bot\)\s*$|\bbot$", msg.from_name or "", re.IGNORECASE))


def asked(msg: Message, rules: Rules, mine: set[str]) -> bool:
    if any(r in mine for r in msg.references[-1:]):      # a reply to the bot: a follow-up
        return True
    text = f"{msg.subject}\n{own_text(msg)}".lower()
    return any(t.lower() in text for t in rules.triggers)


@dataclass
class Todo:
    msg: Message
    why: str                     # "asked" or "unanswered"


def select(msgs: list[Message], *, me: set[str], mine: set[str], rules: Rules, state: State,
           now: datetime | None = None) -> list[Todo]:
    """What to answer now, oldest first. ``me``: the bot's keys; ``mine``: the
    Message-IDs of its posts. Posts that will never be answered are marked
    handled in ``state``; posts held back by the hourly limit are not."""
    now = now or datetime.now(timezone.utc)
    handled = set(state.handled)
    replied_to: dict[str, set[str]] = {}        # msgid -> keys that replied to it
    bot_posts: dict[str, int] = {}              # thread root -> answers by the bot
    for m in msgs:
        for r in m.references[-1:]:
            replied_to.setdefault(r, set()).add(m.author_key)
        if m.author_key in me:
            bot_posts[m.thread_root] = bot_posts.get(m.thread_root, 0) + 1
    chat = [m for m in msgs if m.kind != KIND_POST and not m.references]
    later_chat: dict[str, set[str]] = {}       # chat line -> authors who wrote after it
    for i, m in enumerate(chat):
        later_chat[m.message_id] = {c.author_key for c in chat[i + 1:]}
    todo = []
    for m in msgs:
        if m.message_id in handled or not m.readable or m.author_key in me:
            continue
        if m.author_key in rules.ignore_keys or is_bot(m) or not own_text(m):
            state.done(m.message_id)
            continue
        if bot_posts.get(m.thread_root, 0) >= rules.max_per_thread:
            state.done(m.message_id)
            continue
        if any(k in me for k in replied_to.get(m.message_id, ())):
            state.done(m.message_id)           # answered already (state lost?)
            continue
        if asked(m, rules, mine):
            todo.append(Todo(m, "asked"))
            continue
        if m.kind != KIND_POST and not m.references:     # a chat line
            after = later_chat.get(m.message_id, set())
            if after & me or after - {m.author_key} or rules.chat_unanswered_after is None:
                state.done(m.message_id)     # someone (or the bot) wrote after it, or off
                continue
            if m.author_key in after:        # the same person goes on: answer the last line
                state.done(m.message_id)
                continue
            if not is_question(own_text(m)):  # "thanks", "hi", an answer to someone
                state.done(m.message_id)
                continue
            if m.date and now - m.date >= rules.chat_unanswered_after:
                todo.append(Todo(m, "unanswered"))
            continue
        others = replied_to.get(m.message_id, set()) - {m.author_key}
        if m.references or others or rules.unanswered_after is None:
            state.done(m.message_id)     # a reply in a thread, answered by a person, or off
            continue
        if m.date and now - m.date >= rules.unanswered_after:
            todo.append(Todo(m, "unanswered"))
        # else: wait and look again
    room = max(rules.max_per_hour - state.in_last_hour(now), 0)
    return todo[:room]


def thread_of(msg: Message, msgs: list[Message]) -> list[str]:
    """The earlier posts of the thread, oldest first, as plain text. For a chat
    line: the chat just before it (people often ask over several lines)."""
    if msg.kind != KIND_POST and not msg.references:
        before = [m for m in msgs if m.kind != KIND_POST and not m.references and m.readable]
        i = next((n for n, m in enumerate(before) if m.message_id == msg.message_id), 0)
        return [f"{m.from_name}: {split_signature(m.body)[0].strip()}" for m in before[max(0, i - 6):i]]
    out = []
    for m in msgs:
        if m.message_id == msg.message_id:
            break
        if m.thread_root == msg.thread_root and m.readable:
            out.append(f"{m.from_name}: {split_signature(m.body)[0].strip()}")
    return out


def question_of(msg: Message, rules: Rules) -> str:
    text = own_text(msg)
    for t in rules.triggers:
        text = re.sub(re.escape(t), "", text, flags=re.IGNORECASE)
    subject = msg.subject.strip()
    if subject and not subject.lower().startswith("re:"):
        text = f"{subject}\n{text}"
    return text.strip()


@dataclass
class Reply:
    subject: str
    body: str
    references: list[str]
    kind: str


def reply(msg: Message, ans: Answer | None, kinds: tuple[str, ...]) -> Reply:
    """The answer as a post in the thread (or a chat line in a chat group).
    ``ans`` None: not found in the docs."""
    kind = KIND_POST if msg.kind == KIND_POST and KIND_POST in kinds else KIND_CHAT
    if kind not in kinds:
        kind = kinds[0]
    if ans is None:
        text = NOT_FOUND
    else:
        text = ans.text.strip()
        if ans.sources:
            text += "\n\nSources:\n" + "\n".join(
                f"{i}. [{c.label}]({c.url})" for i, c in enumerate(ans.sources, 1))
    if kind == KIND_POST:
        quoted = "\n".join(f"> {ln}" for ln in own_text(msg).split("\n")[:6])
        name = msg.from_name or "You"
        text = f"{name} wrote:\n{quoted}\n\n{text}"
        subject = msg.subject if msg.subject.lower().startswith("re:") else f"Re: {msg.subject}"
    else:
        subject = ""
    return Reply(subject, f"{text}\n\n-- \n{SIGNATURE}\n", [*msg.references, msg.message_id], kind)
