<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/unseenet/unseenet/main/assets/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/unseenet/unseenet/main/assets/logo-light.svg" alt="Unseenet" width="360">
  </picture>
</p>

<h1 align="center">unseenet-helpbot</h1>

<p align="center"><b>The bot that answers questions in unseenet.help.</b><br>
From the project's docs, specs, issues and earlier answers, with a small language model that runs locally.</p>

<p align="center">
  <a href="https://github.com/unseenet/unseenet-helpbot/releases"><img src="https://img.shields.io/github/v/release/unseenet/unseenet-helpbot?include_prereleases&label=release" alt="Release"></a>
  <a href="https://github.com/unseenet/unseenet-helpbot/actions/workflows/tests.yml"><img src="https://github.com/unseenet/unseenet-helpbot/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0"></a>
</p>

> **Pre-alpha.** Nothing is stable yet, and Unseenet has not had a security
> review. Do not rely on it to protect anyone yet.

## What it is

A bot that follows the help group on [Unseenet](https://unseenet.org)
and answers questions from the project's documentation and specs, using a
small language model that runs locally.

**Status:** early. It reads `unseenet.help`, answers with sources, and runs
for the project on its own small cloud VM with a local model.

### Rules it follows

- **Humans first.** It answers when a post names it (`@helpbot`), when
  someone replies to one of its answers, when a new thread has had no
  reply for 30 minutes, or when a chat line that asks something has had no
  answer for 10 minutes. Dates in Unseenet are rounded to 10 minutes, so
  the wait can be up to 10 minutes longer.
- **It learns from people's answers.** A question in the group that someone
  other than the asker answered - a person, never a bot - becomes one more
  source, with a link to the thread, so it can say "as answered earlier in
  the group". The docs come first: an earlier answer may be out of date.
  Turn it off with `learn_from_threads = false`.
- **A source, or no answer:** "I couldn't find this in the docs" when it
  was named, silence otherwise.
- **No security advice of its own.** The prompt tells it to point to the
  docs and say that Unseenet is pre-alpha and not reviewed.
- **Limits:** 10 answers an hour and 3 per thread. It never answers
  itself or other bots, nor anything posted before its first look at the
  group.
- **The question is data, not instructions.** The prompt says so, but a
  small model can be talked into things; the limits keep the damage small.

## Run it

```sh
pip install "unseenet-helpbot @ git+https://github.com/unseenet/unseenet-helpbot.git@v0.1.0"
ollama pull qwen2.5:7b
cp helpbot.example.toml helpbot.toml        # fill in the group
export UNSEENET_VAULT_PASSPHRASE=...
unseenet-helpbot -c helpbot.toml sync       # fetch the repositories, issues and PRs
                                            # (and their comments, with a token: #15)
unseenet-helpbot -c helpbot.toml ask "How do I run a node?"   # try it, no network
unseenet-helpbot -c helpbot.toml init       # the bot's vault and key
unseenet-helpbot -c helpbot.toml run --once --dry-run   # what would it answer?
unseenet-helpbot -c helpbot.toml run        # follow the group
```

On a server, `contrib/install-ubuntu.sh` does all of this - Tor, Ollama,
the model, a `helpbot` user, a vault with a random passphrase and the bot
as a systemd service:

```sh
sudo GROUP="unseenet.help@<fp>" bash contrib/install-ubuntu.sh
```

The bot publishes a profile with the bot mark (UN-RFC 0022) on its first
run, and does not answer keys whose profile carries the mark.

### Choosing a model

Tried on an 8-core laptop CPU without a GPU, with the same three questions:

| Model | RAM | Time per answer | Result |
|---|---|---|---|
| `qwen2.5:7b` | ~6 GB | 15-30 s | right each time, close to the docs' own words |
| `qwen2.5:3b` | ~3 GB | 10-45 s | once added a step the docs don't say, once answered with only citations |

`qwen2.5:7b` is the default. An Oracle Always Free ARM VM (4 cores,
24 GB) can run it; expect it to be slower than the table.

## How it works

- **One key, its own vault.** The bot is an ordinary Unseenet client built
  on `unseenet.client.session.Session` from
  [unseenet/unseenet](https://github.com/unseenet/unseenet), with its own
  vault and the name *Unseenet help (bot)*.
- **Knowledge.** Every public repository of the organisation on GitHub:
  its Markdown files (README, docs, the UN-RFCs, the changelog), and its
  issues and pull requests with their state, labels and milestone, so it
  can say "a known problem, open in #140" or "planned for 0.4.0". The list
  of repositories is read at every sync (every 6 hours), so new ones come
  by themselves; private ones never. Local folders can be added too. All
  of it is cut into sections and searched with BM25 - no model, no extra
  package, milliseconds.
- **Answering.** The model first turns the question into English search
  keywords (so a Danish question finds the English docs), then answers
  from the five best sections only, citing them. The reply quotes the
  question, lists its sources with links and ends with a signature saying
  it is a bot and can be wrong.
- **The model runs locally** through any OpenAI-style server (Ollama or
  llama.cpp's `llama-server`), so questions do not leave Tor for a third
  party. A remote API can be configured, but is not the default.

## Versions and releases

Versions follow [semantic versioning](https://semver.org/) on the same
principles as [unseenet](https://github.com/unseenet/unseenet/blob/main/docs/development.md#versioning):
tags `vX.Y.Z` on `main`, the changes in [CHANGELOG.md](CHANGELOG.md), and a
GitHub release for each tag. This is one of the project's own services, so it
is not on PyPI. Each release names the minor version of unseenet it works with
(`unseenet>=0.5,<0.6`).

To release: move the entries under `## [Unreleased]` in `CHANGELOG.md` to a
new `## [X.Y.Z] - YYYY-MM-DD` section, set `__version__` in
`src/unseenet_helpbot/__init__.py`, commit, then
`git tag -a vX.Y.Z -m "unseenet-helpbot X.Y.Z" && git push origin vX.Y.Z`.

## Part of Unseenet

| Repository | What it is |
|---|---|
| [unseenet](https://github.com/unseenet/unseenet) | The protocol (UN-RFCs), the core library, the node and the command-line client |
| [unseenet-tui](https://github.com/unseenet/unseenet-tui) | The terminal client |
| [unseenet-gui](https://github.com/unseenet/unseenet-gui) | The graphical client - in a window, booted, or in a browser |
| [unseenet-portable](https://github.com/unseenet/unseenet-portable) | Builds the portable clients, Terminal and Graphical, with Tor inside |
| [unseenet-bootable](https://github.com/unseenet/unseenet-bootable) | Builds the bootable images, Terminal and Graphical |
| [unseenet-docs](https://github.com/unseenet/unseenet-docs) | The site [unseenet.org](https://unseenet.org) |
| [unseenet-entrance](https://github.com/unseenet/unseenet-entrance) | Web entrances: the graphical client in an ordinary browser |
| [unseenet-gateway](https://github.com/unseenet/unseenet-gateway) | Gateways to other networks: Usenet, Nostr, Matrix |
| [unseenet-bots](https://github.com/unseenet/unseenet-bots) | Bots that keep channels filled with current content |
| [unseenet-helpbot](https://github.com/unseenet/unseenet-helpbot) | The bot that answers questions in `unseenet.help` |
| [unseenet-stats](https://github.com/unseenet/unseenet-stats) | Statistics for the network |
| [unseenet-mcp](https://github.com/unseenet/unseenet-mcp) | An MCP server, so a language model can read and post as you (planning) |
| [unseenet-demo](https://github.com/unseenet/unseenet-demo) | Demo people, feeds and sites, made with the command-line client |

## License

[Apache License 2.0](LICENSE). The Unseenet logo: CC BY 4.0.
