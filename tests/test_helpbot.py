from datetime import datetime, timedelta, timezone

import pytest

import unseenet.client.session as sess
from unseenet.client.session import Message, Session
from unseenet.core import crypto
from unseenet.core.groups import KIND_CHAT, KIND_POST
from unseenet.core.store import Store
from unseenet.core.vault import Vault
from unseenet.node.server import Node, NodeConfig

from unseenet_helpbot import bot, llm, runner
from unseenet_helpbot.docs import Index, chunk_file, tokens, url_for

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
BOT, ALICE, BOB = "bot-key", "alice-key", "bob-key"
KDF = {"ops": 1, "mem": 8192 * 1024}


def write_docs(tmp_path):
    d = tmp_path / "docs"
    (d / "spec").mkdir(parents=True)
    (d / "spec" / "un-rfc-0019.md").write_text(
        "```\nUnseenet Working Group\nUN-RFC: 0019\n\n      Unseenet: Names for Identities\n```\n\n"
        "# Abstract\n\nAn identity may hold a registered name like @lorensen, issued by a registrar.\n\n"
        "# 4. Registered Names\n\nClaim a registered name in the client with the command palette: "
        "Claim a name. The registrar issues a signed name certificate.\n")
    (d / "node").mkdir()
    (d / "node" / "install.md").write_text(
        "# Installing a node\n\nA node runs on Debian or a Raspberry Pi with one install command. "
        "It is an onion service, so no port forwarding is needed.\n")
    return d


def test_chunks_titles_and_urls(tmp_path):
    d = write_docs(tmp_path)
    chunks = chunk_file(d / "spec" / "un-rfc-0019.md", "spec/un-rfc-0019.md")
    assert chunks[0].title == "Names for Identities"
    assert [c.label for c in chunks][-1] == "UN-RFC 0019, 4. Registered Names"
    assert url_for("spec/un-rfc-0019.md") == "https://unseenet.org/spec/un-rfc-0019/"
    assert url_for("index.md") == "https://unseenet.org/"
    assert url_for("node/index.md") == "https://unseenet.org/node/"
    assert "0019" in tokens("see un-rfc-0019")


def test_search_finds_the_right_section(tmp_path):
    ix = Index.from_folders([write_docs(tmp_path)])
    assert ix.search("how do I claim a name")[0][1].heading == "4. Registered Names"
    assert ix.search("raspberry pi port forwarding")[0][1].path == "node/install.md"
    assert ix.search("zzz qqq") == []


class FakeModel:
    def __init__(self, reply="Use the command palette: Claim a name [2]."):
        self.reply, self.calls = reply, []

    async def complete(self, messages, max_tokens=500):
        self.calls.append(messages)
        if max_tokens == 40:
            return "claim registered name"
        return self.reply


async def test_answer_cites_and_renumbers(tmp_path):
    ix = Index.from_folders([write_docs(tmp_path)])
    ans = await llm.answer(FakeModel(), ix, "Hvordan får jeg et navn?")
    assert ans.text.endswith("[1].") and len(ans.sources) == 1
    assert ans.sources[0].heading == "Abstract"      # [2] became [1]


async def test_dont_know(tmp_path):
    ix = Index.from_folders([write_docs(tmp_path)])
    assert (await llm.answer(FakeModel("DONT_KNOW"), ix, "claim a name")).text == ""
    assert (await llm.answer(FakeModel("[1] [2]"), ix, "claim a name")).text == ""   # only citations


def test_key_notation(tmp_path):
    f = tmp_path / "k.md"
    f.write_text("# Keys\n\nPress ++ctrl+p++ or ++enter++ to open the command palette here.\n")
    assert "Press Ctrl+P or Enter" in chunk_file(f, "k.md")[0].text


def msg(mid, author, *, refs=(), subject="Question", body="How do I claim a name?\n",
        minutes_ago=60, name="Alice", kind=KIND_POST):
    return Message(0, mid, "g", subject=subject, from_name=name, author_key=author,
                   date=NOW - timedelta(minutes=minutes_ago), body=body,
                   references=list(refs), kind=kind)


def state():
    return bot.State(None, [], [])


def pick(msgs, rules=None, st=None, mine=()):
    st = st or state()
    return [(t.msg.message_id, t.why) for t in
            bot.select(msgs, me={BOT}, mine=set(mine), rules=rules or bot.Rules(), state=st, now=NOW)]


def test_humans_first_then_unanswered():
    assert pick([msg("<a>", ALICE, minutes_ago=5)]) == []                  # wait for people
    assert pick([msg("<a>", ALICE)]) == [("<a>", "unanswered")]
    answered = [msg("<a>", ALICE), msg("<b>", BOB, refs=["<a>"], subject="Re: Question")]
    assert pick(answered) == []
    off = bot.Rules(unanswered_after=None)
    assert pick([msg("<a>", ALICE)], off) == []


def test_asked_by_name_or_follow_up():
    assert pick([msg("<a>", ALICE, body="@helpbot how?\n", minutes_ago=1)]) == [("<a>", "asked")]
    quoted = msg("<a>", ALICE, body="> @helpbot said\nthanks\n", minutes_ago=1, refs=["<x>"])
    assert pick([quoted]) == []
    follow = [msg("<a>", ALICE), msg("<b>", BOT, refs=["<a>"], name="Unseenet help (bot)"),
              msg("<c>", ALICE, refs=["<a>", "<b>"], body="And then?\n", minutes_ago=1)]
    assert pick(follow, mine={"<b>"}) == [("<c>", "asked")]


def test_never_itself_bots_backlog_or_chat_lines():
    assert pick([msg("<a>", BOT)]) == []
    assert pick([msg("<a>", BOB, name="News (bot)", body="@helpbot\n")]) == []
    assert pick([msg("<a>", ALICE, kind=KIND_CHAT, subject="")]) == []
    assert pick([msg("<a>", ALICE, kind=KIND_CHAT, subject="", body="@helpbot hi?\n")]) \
        == [("<a>", "asked")]


def test_limits():
    many = [msg(f"<{i}>", ALICE, subject=f"Q{i}") for i in range(5)]
    assert len(pick(many, bot.Rules(max_per_hour=2))) == 2
    st = state()
    st.times = [(NOW - timedelta(minutes=10)).isoformat()] * 2
    assert pick(many, bot.Rules(max_per_hour=2), st) == []
    thread = [msg("<a>", ALICE)] + [msg(f"<b{i}>", BOT, refs=["<a>"]) for i in range(3)] + \
             [msg("<c>", ALICE, refs=["<a>"], body="@helpbot more?\n", minutes_ago=1)]
    assert pick(thread) == []


def test_reply_quotes_and_lists_sources(tmp_path):
    ix = Index.from_folders([write_docs(tmp_path)])
    ans = llm.Answer("Claim it [1].", [ix.chunks[-1]])
    r = bot.reply(msg("<a>", ALICE), ans, (KIND_CHAT, KIND_POST))
    assert r.subject == "Re: Question" and r.references == ["<a>"] and r.kind == KIND_POST
    assert "> How do I claim a name?" in r.body
    assert "1. [UN-RFC 0019" in r.body and "\n-- \n" in r.body
    chat = bot.reply(msg("<a>", ALICE, kind=KIND_CHAT), None, (KIND_CHAT,))
    assert chat.kind == KIND_CHAT and chat.subject == "" and bot.NOT_FOUND in chat.body


async def test_end_to_end_on_a_node(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "DEFAULT_POW", 10)
    node = Node(Store(), NodeConfig(min_pow=8, forward_delay=(0, 0)))
    server = await node.serve("127.0.0.1", 0)
    addr = f"127.0.0.1:{server.sockets[0].getsockname()[1]}"

    owner = Session(Vault.open(tmp_path / "owner.vault", "pw", **KDF), status=lambda *_: None)
    owner.new_identity("owner", "Owner")
    owner.add_node(addr)
    group = await owner.create_group("unseenet.help", "open", title="Help")

    monkeypatch.setenv(runner.PASS_ENV, "pw")
    monkeypatch.setattr(runner, "Vault", type("V", (), {"open": staticmethod(
        lambda p, pw: Vault.open(p, pw, **KDF))}))
    cfg = runner.Config(vault=tmp_path / "bot.vault", group=group, docs=[str(write_docs(tmp_path))],
                        state_file=tmp_path / "state.json", nodes=[addr])
    runner.cmd_init(cfg)
    st = bot.State.load(cfg.state_file)
    s = runner.open_session(cfg)
    cfg.model = FakeModel()
    index = Index.from_folders(cfg.docs)
    quiet = lambda *_: None
    await owner.post(group, "Old", "@helpbot asked before the bot came\n")
    assert await runner.look_once(s, cfg, index, st, log=quiet) == 0     # first look

    q = await owner.post(group, "Names", "@helpbot how do I claim a name?\n")
    assert await runner.look_once(s, cfg, index, st, log=quiet) == 1
    assert await runner.look_once(s, cfg, index, st, log=quiet) == 0     # once only

    msgs = await owner.fetch_group(group)
    answer = [m for m in msgs if m.references == [q]]
    assert len(answer) == 1 and answer[0].subject == "Re: Names"
    assert "Claim a name [1]" in answer[0].body and "un-rfc-0019" in answer[0].body
    await s.close(); await owner.close()
    server.close()
