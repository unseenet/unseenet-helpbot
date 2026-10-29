"""#13: the help bot's news about releases, in plain language."""
import asyncio

from unseenet_helpbot import news

T0 = 1_761_480_000            # some time; releases at T0 and T0 + 30 min


def iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cache(*extra):
    rel = lambda tag, t, **kw: {"tag": tag, "name": tag, "body": f"Notes for {tag}: you can now export your data.",  # noqa: E731
                               "published": iso(t), "url": f"https://github.com/unseenet/x/releases/{tag}", **kw}
    return {"repos": [
        {"name": "unseenet", "files": {"CHANGELOG.md": "# Changelog\n\n## [0.6.0] - 2026\n\n- **Export** your data.\n\n## [0.5.0]\n\n- old\n"},
         "releases": [rel("v0.5.0", T0 - 86400 * 10), rel("v0.6.0", T0), rel("v0.6.1rc1", T0),
                      rel("dev", T0, prerelease=True), rel("v0.7.0", T0, draft=True), *extra]},
        {"name": "unseenet-gui", "files": {}, "releases": [rel("v0.3.0", T0 + 1800)]}]}


class Model:
    def __init__(self, text="With 0.6.0 you can **export your data** from the menu: Export my data."):
        self.text, self.asked = text, []

    async def complete(self, messages, *a, **kw):
        self.asked.append(messages)
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


class Session:
    def __init__(self):
        self.posts = []

    async def post(self, group, subject, body):
        self.posts.append((group, subject, body))
        return f"<n{len(self.posts)}@x>"


def test_only_stable_releases():
    tags = [r.tag for r in news.releases(cache())]
    assert tags == ["v0.5.0", "v0.6.0", "v0.3.0"]


def test_the_first_time_nothing_old_is_posted(tmp_path):
    st = news.NewsState.load(tmp_path / "news.json")
    assert news.due(cache(), st, now=T0 + 99999) == [] and "unseenet:v0.6.0" in st.seen
    assert news.NewsState.load(tmp_path / "news.json").seen == st.seen     # kept


def test_releases_together_are_one_post_after_the_window(tmp_path):
    st = news.NewsState(tmp_path / "news.json", seen={"unseenet:v0.5.0"}, fresh=False)
    assert news.due(cache(), st, now=T0 + 3600) == []                    # still gathering
    batch = news.due(cache(), st, now=T0 + 3 * 3600)
    assert [r.key for r in batch] == ["unseenet:v0.6.0", "unseenet-gui:v0.3.0"]
    assert news.subject(batch) == "What's new: Unseenet 0.6.0 and the graphical client 0.3.0"
    assert news.changelog_section(cache(), "unseenet", "0.6.0") == "- **Export** your data."


def test_one_section_per_release_put_together_in_one_post(tmp_path):
    st = news.NewsState(tmp_path / "news.json", seen={"unseenet:v0.5.0"}, fresh=False)
    s, m = Session(), Model()
    mid = asyncio.run(news.post_news(s, "unseenet.help.news@x", m, cache(), st, now=T0 + 3 * 3600))
    assert mid == "<n1@x>" and len(s.posts) == 1
    group, subj, body = s.posts[0]
    assert subj == "What's new: Unseenet 0.6.0 and the graphical client 0.3.0"
    assert len(m.asked) == 2                                              # one prompt each
    assert "Notes for v0.6.0" in m.asked[0][1]["content"] and "v0.3.0" not in m.asked[0][1]["content"]
    assert "Changelog:" in m.asked[0][1]["content"]                      # the notes were short
    assert "### Unseenet 0.6.0 · #unseenet" in body and "### The graphical client 0.3.0 · #unseenet-gui" in body
    assert "(https://github.com/unseenet/x/releases/v0.3.0)" in body and "unseenet.announce" in body
    assert st.written == {} and "unseenet-gui:v0.3.0" in st.seen
    assert asyncio.run(news.post_news(s, "g", m, cache(), st, now=T0 + 9 * 3600)) is None   # done


def test_a_few_sections_per_look_kept_until_all_are_written(tmp_path):
    st = news.NewsState(tmp_path / "news.json", seen={"unseenet:v0.5.0"}, fresh=False)
    s, m = Session(), Model()
    assert asyncio.run(news.post_news(s, "g", m, cache(), st, now=T0 + 3 * 3600, per_look=1)) is None
    assert list(news.NewsState.load(tmp_path / "news.json").written) == ["unseenet:v0.6.0"]
    assert asyncio.run(news.post_news(s, "g", m, cache(), st, now=T0 + 3 * 3600, per_look=1)) == "<n1@x>"
    assert len(m.asked) == 2 and len(s.posts) == 1


class Failing(Model):
    """Fails on the gui release, writes the others."""
    async def complete(self, messages, *a, **kw):
        self.asked.append(messages)
        if "graphical client" in messages[1]["content"]:
            raise TimeoutError("timed out")
        return self.text


def test_a_release_the_model_fails_on_is_left_out_never_raw_notes(tmp_path):
    st = news.NewsState(tmp_path / "news.json", seen={"unseenet:v0.5.0"}, fresh=False)
    s, logs = Session(), []
    for _ in range(3):
        asyncio.run(news.post_news(s, "g", Failing(), cache(), st, now=T0 + 3 * 3600, log=logs.append))
    assert len(s.posts) == 1
    _, subj, body = s.posts[0]
    assert subj == "What's new: Unseenet 0.6.0" and "graphical client" not in body
    assert "Notes for" not in body                                        # no raw notes
    assert any("TimeoutError" in x for x in logs) and any("gave up on unseenet-gui:v0.3.0" in x for x in logs)


def test_nothing_to_say_posts_nothing(tmp_path):
    st = news.NewsState(tmp_path / "news.json", seen={"unseenet:v0.5.0"}, fresh=False)
    s = Session()
    assert asyncio.run(news.post_news(s, "g", Model("DONT_KNOW"), cache(), st, now=T0 + 3 * 3600)) is None
    assert s.posts == [] and "unseenet:v0.6.0" in st.seen


class Refusing(Session):
    async def post(self, group, subject, body):
        if subject.startswith("What's new"):
            raise ValueError("too big")
        return await super().post(group, subject, body)


def test_if_the_gathered_post_fails_each_release_gets_its_own(tmp_path):
    st = news.NewsState(tmp_path / "news.json", seen={"unseenet:v0.5.0"}, fresh=False)
    s = Refusing()
    asyncio.run(news.post_news(s, "g", Model(), cache(), st, now=T0 + 3 * 3600))
    assert [p[1] for p in s.posts] == ["[unseenet] What's new: Unseenet 0.6.0",
                                       "[unseenet-gui] What's new: the graphical client 0.3.0"]
    assert "#unseenet-gui" in s.posts[1][2] and "Notes for" not in s.posts[1][2]


def test_many_releases_make_a_short_subject():
    rels = [news.Release(n, "v1.0.0", "", "", "", "") for n in
            ("unseenet-gui", "unseenet-tui", "unseenet", "unseenet-gateway", "unseenet-watchman")]
    assert news.subject(rels) == "What's new: Unseenet 1.0.0, the graphical client 1.0.0 and 3 more"
