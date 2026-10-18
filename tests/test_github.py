import json

from unseenet_helpbot import github
from unseenet_helpbot.docs import Index

API = {
    "https://api.github.com/orgs/unseenet/repos?type=public&per_page=100&page=1": [
        {"name": "unseenet", "default_branch": "main", "private": False},
        {"name": "unseenet-web", "default_branch": "main", "private": False,
         "description": "A local web client for Unseenet: groups and chat in a window"},
        {"name": "old", "default_branch": "main", "private": False, "archived": True},
        {"name": "secret", "default_branch": "main", "private": True},
        {"name": "skipme", "default_branch": "main", "private": False}],
    "https://api.github.com/repos/unseenet/unseenet/git/trees/main?recursive=1": {"tree": [
        {"path": "docs/project/people.md", "type": "blob", "size": 10},
        {"path": "rfc/un-rfc-0005.md", "type": "blob", "size": 10},
        {"path": "LICENSE.md", "type": "blob", "size": 10},
        {"path": "tests/data/x.md", "type": "blob", "size": 10}]},
    "https://api.github.com/repos/unseenet/unseenet-web/git/trees/main?recursive=1": {"tree": [
        {"path": "README.md", "type": "blob", "size": 10}]},
    "https://api.github.com/repos/unseenet/old/git/trees/main?recursive=1": {"tree": []},
    "https://api.github.com/repos/unseenet/unseenet/issues?state=all&per_page=100&page=1": [
        {"number": 140, "title": "Client: use an existing Tor, so Unseenet runs in Tails",
         "state": "open", "labels": [{"name": "enhancement"}], "milestone": {"title": "0.4.0"},
         "html_url": "https://github.com/unseenet/unseenet/issues/140",
         "body": "Tails already runs Tor; the client should use its SOCKS port."},
        {"number": 191, "title": "Add the help group", "state": "closed",
         "pull_request": {"merged_at": "2026-10-18"}, "labels": [], "milestone": None,
         "html_url": "https://github.com/unseenet/unseenet/pull/191", "body": ""},
        {"number": 186, "title": "Core: a reading API", "state": "closed",
         "state_reason": "not_planned", "labels": [], "milestone": None,
         "html_url": "https://github.com/unseenet/unseenet/issues/186", "body": "duplicate"}],
    "https://api.github.com/repos/unseenet/unseenet-web/issues?state=all&per_page=100&page=1": [],
    "https://api.github.com/repos/unseenet/old/issues?state=all&per_page=100&page=1": [],
}
RAW = {
    "https://raw.githubusercontent.com/unseenet/unseenet/main/docs/project/people.md":
        "# People\n\n## Not people\n\nClaude is an AI assistant made by Anthropic, not a person.\n",
    "https://raw.githubusercontent.com/unseenet/unseenet/main/rfc/un-rfc-0005.md":
        "# Abstract\n\nONNTP is the transport of articles between nodes over onion services.\n",
    "https://raw.githubusercontent.com/unseenet/unseenet-web/main/README.md":
        "# unseenet-web\n\nA local web client for Unseenet in a browser window, with kiosk mode.\n",
}


def fake():
    calls = []

    def fetch(url):
        calls.append(url)
        return RAW[url].encode() if url in RAW else json.dumps(API[url]).encode()
    return github.GitHub(org="unseenet", exclude={"skipme"}, fetch=fetch), calls


def test_sync_reads_public_repos_only():
    gh, calls = fake()
    cache = gh.sync(log=lambda *_: None)
    assert [r["name"] for r in cache["repos"]] == ["unseenet", "unseenet-web", "old"]
    assert cache["repos"][2]["archived"]
    assert not any(w in u for u in calls for w in ("secret", "skipme", "LICENSE", "tests/"))
    states = {i["number"]: i["state"] for i in cache["repos"][0]["issues"]}
    assert states == {140: "open", 191: "merged", 186: "not planned"}


def test_chunks_label_and_link():
    gh, _ = fake()
    ix = Index(github.chunks(gh.sync(log=lambda *_: None)))
    top = ix.search("tails existing tor")[0][1]
    assert top.kind == "issue"
    assert top.label.startswith("unseenet issue #140 (open, milestone 0.4.0)")
    assert ix.search("help group")[0][1].label.startswith("unseenet PR #191 (merged)")
    web = ix.search("web client kiosk")[0][1]
    assert web.label.startswith("unseenet-web: ")
    assert web.url == "https://github.com/unseenet/unseenet-web/blob/HEAD/README.md"
    rfc = ix.search("ONNTP onion transport")[0][1]
    assert rfc.label.startswith("UN-RFC 0005")
    assert rfc.url == "https://unseenet.org/spec/un-rfc-0005/"
    assert ix.search("who is claude")[0][1].url == "https://unseenet.org/project/people/"
    repo = ix.search("Is there a web client?")[0][1]
    assert repo.label == "The unseenet-web repository"
    assert repo.url == "https://github.com/unseenet/unseenet-web"


def test_duplicates_dropped_and_issues_capped():
    gh, _ = fake()
    chunks = github.chunks(gh.sync(log=lambda *_: None))
    ix = Index(chunks + chunks)
    assert len(ix.chunks) == len(chunks)
    assert all(c.kind != "issue" for _, c in ix.search("tails tor help group", max_issues=0))
