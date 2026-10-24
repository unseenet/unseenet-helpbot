"""Earlier answered threads of the help group, as excerpts the bot answers from
(unseenet-helpbot#5).

A thread counts when it starts with a question and someone other than the asker
answered it - a person, never a bot: the bot must not learn from its own answers
or another bot's, or a mistake would come back as a source. Each becomes one
excerpt, ``kind="thread"``, with the question, the answers and a link to the
thread, so an answer can point people to where it was asked before. The docs
still come first: the model is told that an earlier answer can be out of date.
"""

from __future__ import annotations

from collections import Counter

from .bot import is_bot, is_question, own_text
from .docs import Chunk, tokens

MAX_TEXT = 2400
MAX_ANSWERS = 3


def post_address(group: str, message_id: str) -> str:
    """The thread's ``unseenet:`` address, in the form the core writes (0.5), else the
    group's older form, which every client opens."""
    try:
        from unseenet.core.addresses import post_address as address
    except ImportError:
        return f"unseenet:join?g={group}"
    return address(group, message_id)


def thread_chunks(msgs: list, group: str, *, not_people: set[str]) -> list[Chunk]:
    """One excerpt per answered question in ``msgs`` (the group's posts). Answers by
    keys in ``not_people`` (the bot's own, other bots') or by the asker never count."""
    by_id = {m.message_id: m for m in msgs}
    replies: dict[str, list] = {}
    for m in msgs:
        root = m.references[0] if m.references else None
        if root in by_id and m.readable:
            replies.setdefault(root, []).append(m)
    out = []
    for root_id, answers in replies.items():
        q = by_id[root_id]
        if q.references or not q.readable or q.author_key in not_people or is_bot(q):
            continue
        asked = f"{q.subject}\n{own_text(q)}"
        if not is_question(asked):
            continue
        people = [a for a in sorted(answers, key=lambda a: a.number)
                  if a.author_key and a.author_key != q.author_key
                  and a.author_key not in not_people and not is_bot(a) and own_text(a)]
        if not people:
            continue
        subject = (q.subject or own_text(q).split("\n", 1)[0])[:120]
        text = f"Question: {subject}\n{own_text(q)}"
        for a in people[:MAX_ANSWERS]:
            text += f"\n\nAnswer by {a.from_name or 'someone'}:\n{own_text(a)}"
        text = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " ..."
        c = Chunk(f"thread:{root_id}", f"Earlier answer in the help group: {subject}", "",
                  text, post_address(group, root_id), kind="thread")
        c.terms = Counter(tokens(f"{subject} {subject} {text}"))
        out.append(c)
    return out
