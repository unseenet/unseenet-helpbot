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


# The help bot answered "How do I find the latest version?" from 0.3.1's CHANGELOG
# section ("releases/latest" on GitHub) instead of the page on updating.
UPDATING = chunk("updating.md", "# Updating\n\n## Portable (Linux, macOS, Windows) · Graphical\n\n"
                 "Press Update in the window: it fetches the newest version, checks its "
                 "signature and puts it in place. The version you run is in About Unseenet.",
                 repo="unseenet-portable")
LOG = "# Changelog\n\n## [Unreleased]\n\nNothing yet, nothing at all here.\n\n" + "".join(
    f"## [0.{n}.0] - 2026-10-{n + 10}\n\nRelease {n}: things that changed in version 0.{n}.0.\n\n"
    for n in range(7, 3, -1)) + (
    "## [0.3.1] - 2026-10-18\n\nA stable release is now GitHub's latest release, so "
    "releases/latest finds the latest version; before, the latest was a pre-release.\n")
CHANGELOG = chunk("CHANGELOG.md", LOG)


def test_a_changelog_keeps_only_its_newest_releases():
    headings = [c.heading for c in CHANGELOG]
    assert headings[0] == "[Unreleased]"
    assert [h for h in headings if h.startswith("[0")] == [
        "[0.7.0] - 2026-10-17", "[0.6.0] - 2026-10-16", "[0.5.0] - 2026-10-15"]
    assert not any("0.3.1" in c.text for c in CHANGELOG)
    assert all(c.role == "history" for c in CHANGELOG)


def test_latest_finds_the_newest():
    old = chunk_text("## [0.3.1]\n\n" + "the latest release, releases/latest, latest " * 3,
                     "notes.md", "https://example.org/notes.md")
    hits = [c for _, c in Index(UPDATING + old + CHANGELOG).search(
        "How do I find the latest version ?")]
    assert hits[0].path == "updating.md"


def test_upgrade_is_update():
    from unseenet_helpbot.docs import tokens
    assert tokens("how do I upgrade") == tokens("how do I update")
