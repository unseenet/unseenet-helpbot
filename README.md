# unseenet-helpbot

A bot that follows the help group on [Unseenet](https://unseenet.org)
and answers questions from the project's documentation and specs, using a
small language model that runs locally.

**Status:** planning. Nothing works yet; see the issues.

## Idea

- One bot is one key, with `bot: true` in its profile (UN-RFC 0030), like
  the bots in [unseenet-bots](https://github.com/unseenet/unseenet-bots).
- Built only on the public core library of
  [unseenet/unseenet](https://github.com/unseenet/unseenet).
- Answers from an index of the docs, the UN-RFC series and the FAQ
  (retrieval-augmented generation), and later from earlier answered
  threads in the help group.
- The model runs locally (llama.cpp or Ollama, a model in the 3-8B
  class), so questions never leave Tor for a third party. A remote API
  can be configured, but is not the default.

## Rules it follows

- **Humans first.** Answers when mentioned, or when a question has been
  unanswered for a while - not to everything.
- **Always a source.** Every answer names the document and section it
  is based on, e.g. "UN-RFC 0019 section 3".
- **Says "I don't know"** rather than guessing.
- **No security advice of its own.** Questions about threat model or
  protecting someone are pointed to the docs and to people.
- Rate limited, and ignores other bots.

## Licence

Apache-2.0, like the rest of Unseenet.
