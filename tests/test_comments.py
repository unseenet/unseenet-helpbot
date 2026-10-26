"""#15: the comments on issues and PRs - where they ended - with a token, since the last sync."""
import json

from test_github import API, RAW

from unseenet_helpbot import github

C = "https://api.github.com/repos/unseenet/{}/issues/comments?sort=updated&direction=asc"


def comment(i, number, user, body, assoc="NONE", bot=False, date="2026-10-01"):
    return {"id": i, "issue_url": f"https://api.github.com/repos/unseenet/unseenet/issues/{number}",
            "user": {"login": user, "type": "Bot" if bot else "User"}, "author_association": assoc,
            "created_at": date + "T10:00:00Z", "body": body}


FIRST = [comment(1, 140, "sonia", "Would love this for Tails."),
         comment(2, 140, "andlo", "Decided: going with the SOCKS port of the running Tor.", "OWNER"),
         comment(3, 140, "x", "me too", date="2026-10-02"),
         comment(4, 140, "github-actions[bot]", "CI passed", bot=True, date="2026-10-03"),
         comment(5, 140, "y", "any news?", date="2026-10-04")]


def fake(token="t", extra=None):
    calls, api = [], dict(API)
    for repo in ("unseenet", "unseenet-web", "old"):
        api[C.format(repo) + "&per_page=100&page=1"] = FIRST if repo == "unseenet" else []
    api.update(extra or {})

    def fetch(url):
        calls.append(url)
        return RAW[url].encode() if url in RAW else json.dumps(api[url]).encode()
    return github.GitHub(org="unseenet", exclude={"skipme"}, token=token, fetch=fetch), calls


def test_comments_with_a_token_where_it_ended_first():
    gh, calls = fake()
    cache = gh.sync(log=lambda *_: None)
    assert sum("/comments" in u for u in calls) == 3                # one call per repository
    kept = cache["repos"][0]["comments"]["140"]
    assert [c["id"] for c in kept] == [2, 3, 5]                     # the decision, the last two; no bot
    issue = next(c for c in github.chunks(cache) if c.path == "gh:unseenet#140")
    assert issue.text.index("Decision (andlo") < issue.text.index("Tails already runs Tor")
    assert "going" in issue.terms and "CI passed" not in issue.text


def test_the_next_sync_asks_only_since_the_last():
    gh, _ = fake()
    first = gh.sync(log=lambda *_: None)
    since = first["repos"][0]["comments_synced"]
    newer = [comment(6, 186, "andlo", "Not planned: closing, it is a duplicate.", "MEMBER", date="2026-10-20")]
    gh, calls = fake(extra={C.format("unseenet") + f"&since={since}&per_page=100&page=1": newer,
                            C.format("unseenet-web") + f"&since={first['repos'][1]['comments_synced']}&per_page=100&page=1": [],
                            C.format("old") + f"&since={first['repos'][2]['comments_synced']}&per_page=100&page=1": []})
    second = gh.sync(log=lambda *_: None, previous=first)
    assert all("since=" in u for u in calls if "/comments" in u)
    kept = second["repos"][0]["comments"]
    assert [c["id"] for c in kept["140"]] == [2, 3, 5] and kept["186"][0]["decision"]


def test_without_a_token_no_comments_but_what_was_had_is_kept():
    gh, _ = fake()
    first = gh.sync(log=lambda *_: None)
    said = []
    gh, calls = fake(token="")
    second = gh.sync(log=said.append, previous=first)
    assert not any("/comments" in u for u in calls) and any("no token" in s for s in said)
    assert second["repos"][0]["comments"] == first["repos"][0]["comments"]
