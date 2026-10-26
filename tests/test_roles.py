"""#14: answer from the clients - how-to pages count most, the UN-RFCs explain why."""
from unseenet_helpbot.docs import Chunk, Index, chunk_text
from unseenet_helpbot.llm import SYSTEM, excerpts


def chunk(path, text, repo="unseenet", kind="docs"):
    out = chunk_text(text, path, "https://example.org/" + path, repo=repo)
    for c in out:
        c.kind = kind
    return out


RFC = chunk("spec/un-rfc-0028.md",
            "# UN-RFC 0028\n\n## Chat groups\n\n" + "A chat group takes chat lines; a chat line in a chat group. " * 6)
GUI = chunk("README.md", "# unseenet-gui\n\n## Chatting\n\nTo chat in a group, open it and type in the box at the bottom.",
            repo="unseenet-gui")
TUI = chunk("client.md", "# The terminal client\n\n## Chat\n\nIn a chat group, press Ctrl+P and choose Chat.")
MORE_RFC = [c for n in range(5) for c in chunk(f"spec/un-rfc-00{40 + n}.md", f"# UN-RFC 00{40 + n}\n\n## Chat\n\nchat group chat " * 3)]


def test_roles():
    assert RFC[0].role == "spec" and GUI[0].role == "howto" and TUI[0].role == "howto"
    assert Chunk("guide/start.md", "Start", "", "text", "u").role == "guide"
    assert Chunk("#140", "#140 broken", "", "broken", "u", kind="issue").role == "history"
    assert Chunk("t", "a thread", "", "x", "u", kind="thread").role == "howto"


def test_how_to_comes_before_the_protocol():
    index = Index(RFC + GUI + TUI + MORE_RFC)
    hits = [c for _, c in index.search("how do I chat in a chat group", k=5)]
    assert hits[0].role == "howto"
    assert sum(c.role == "spec" for c in hits) <= 2                 # at most two UN-RFC pieces


def test_a_question_about_the_design_lets_the_rfcs_count():
    index = Index(RFC + GUI)
    plain = dict((c.path, s) for s, c in index.search("chat group chat lines"))
    why = dict((c.path, s) for s, c in index.search("why does the protocol have chat group chat lines"))
    assert why["spec/un-rfc-0028.md"] > plain["spec/un-rfc-0028.md"]


def test_the_model_is_told():
    text = excerpts(GUI + RFC)
    assert "[1] (how-to)" in text and "[2] (spec)" in text
    assert "graphical client" in SYSTEM and "Ctrl+P" in SYSTEM and "spec" in SYSTEM
