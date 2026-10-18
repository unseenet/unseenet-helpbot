# unseenet-helpbot

A bot that follows the help group on [Unseenet](https://unseenet.org)
and answers questions from the project's documentation and specs, using a
small language model that runs locally.

**Status:** early. It reads the group, answers with sources, and is tested
against a local node and a local model. It does not run on the network yet.

## How it works

- **One key, its own vault.** The bot is an ordinary Unseenet client built
  on `unseenet.client.session.Session` from
  [unseenet/unseenet](https://github.com/unseenet/unseenet), with its own
  vault and the name *Unseenet help (bot)*.
- **Knowledge.** At start (and hourly) it cuts the docs and the UN-RFC
  series into sections and searches them with BM25: no model, no extra
  package, milliseconds for the whole docs folder.
- **Answering.** The model first turns the question into English search
  keywords (so a Danish question finds the English docs), then answers
  from the five best sections only, citing them. The reply quotes the
  question, lists its sources with links and ends with a signature saying
  it is a bot and can be wrong.
- **The model runs locally** through any OpenAI-style server (Ollama or
  llama.cpp's `llama-server`), so questions do not leave Tor for a third
  party. A remote API can be configured, but is not the default.

## Rules it follows

- **Humans first.** It answers when a post names it (`@helpbot`), when
  someone replies to one of its answers, or when a question (a new thread)
  has had no reply for 30 minutes. Chat lines only when it is named.
- **A source, or no answer:** "I couldn't find this in the docs" when it
  was named, silence otherwise.
- **No security advice of its own.** The prompt tells it to point to the
  docs and say that Unseenet is pre-alpha and not reviewed.
- **Limits:** 10 answers an hour and 3 per thread. It never answers
  itself or other bots, nor anything posted before its first look at the
  group.
- **The question is data, not instructions.** The prompt says so, but a
  small model can be talked into things; the limits keep the damage small.

## Running it

```sh
pip install git+https://github.com/unseenet/unseenet-helpbot.git
ollama pull qwen2.5:7b
git clone https://github.com/unseenet/unseenet ~/src/unseenet   # the docs
cp helpbot.example.toml helpbot.toml        # fill in the group
export UNSEENET_VAULT_PASSPHRASE=...
unseenet-helpbot -c helpbot.toml ask "How do I run a node?"   # try it, no network
unseenet-helpbot -c helpbot.toml init       # the bot's vault and key
unseenet-helpbot -c helpbot.toml run --once --dry-run   # what would it answer?
unseenet-helpbot -c helpbot.toml run        # follow the group
```

Keep the docs fresh with `git pull` (e.g. a daily timer); the index is
rebuilt every hour.

On a server, `contrib/install-ubuntu.sh` does all of this - Tor, Ollama,
the model, a `helpbot` user, a vault with a random passphrase, the bot as a
systemd service and a daily update of the docs:

```sh
sudo GROUP="unseenet.help@<fp>" bash contrib/install-ubuntu.sh
```

The bot publishes a profile with the bot mark (UN-RFC 0022) on its first
run, and does not answer keys whose profile carries the mark.

## Choosing a model

Tried on an 8-core laptop CPU without a GPU, with the same three questions:

| Model | RAM | Time per answer | Result |
|---|---|---|---|
| `qwen2.5:7b` | ~6 GB | 15-30 s | right each time, close to the docs' own words |
| `qwen2.5:3b` | ~3 GB | 10-45 s | once added a step the docs don't say, once answered with only citations |

`qwen2.5:7b` is the default. An Oracle Always Free ARM VM (4 cores,
24 GB) can run it; expect it to be slower than the table.

## Licence

Apache-2.0, like the rest of Unseenet.
