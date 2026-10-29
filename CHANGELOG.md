# Changelog

All notable changes to unseenet-helpbot are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/) on the same principles as
[unseenet](https://github.com/unseenet/unseenet/blob/main/docs/development.md#versioning).

## [Unreleased]

## [0.3.2] - 2026-10-29

- **Only version tags are news** (#29): a release counts only with a tag like `v0.3.0` or
  `v0.6.3.post1`, so the entrance's `chiavdf-...` and `web-...` builds are never told about.

## [0.3.1] - 2026-10-29

- **News that actually gets written** (#29): the 0.6 releases were never posted, because
  all ten went to the model in one prompt and every try timed out. Now the model writes
  one short section per release, a few per look (`per_look` under `[news]`, default 4),
  kept until all are written; the bot puts them together into one post, each section
  tagged with its repository (`#unseenet-gui`) and linked to its release. If that post
  cannot be posted, each release gets its own post (`[unseenet-gui] What's new: ...`).
  Raw release notes are never posted - they are in `unseenet.announce`. The log says why
  a section failed.
- Names for the watchman, statistics, docs, MCP and demo repositories in the news.

## [0.3.0] - 2026-10-29

Needs unseenet 0.6 (`unseenet>=0.6,<0.7`): update the nodes first.

- **Ripening to the level you choose** (#27, unseenet#740): the bot's key ripens in the
  background to `ripen_to` under `[bot]`, else `UNSEENET_RIPEN_TO`, else level 3. Level 4
  takes two to three weeks of one core, then every answer costs about a quarter of the
  postage. The project's own bot runs at 4.
- **News** (#13, `[news]`, off by default): releases told in plain language in
  `unseenet.help.news` - stable ones only, those released together in one post
  ("What's new: Unseenet 0.6.0 and the graphical client 0.3.0"), written by the
  model from the release notes and CHANGELOG with the answers' rules, linking the
  official notes; nothing old ever, nothing when the model fails (tried 3 times).
  The comments under its posts are answered as in the help group. `news --dry-run`
  shows the post first.

- **Where issues ended** (#15): with a token, the comments on issues and PRs
  are sources too - the last two of each and every decision by a member - fetched
  since the last sync in one call per repository (a full fetch weekly), and put
  before the issue's text, so "why was X dropped?" is answered from the decision.
- **Answers from the clients, not the protocol** (#14): every source has a role
  (how-to, guide, spec, issue, docs); how-to pages count most and at most two
  UN-RFC pieces are used, unless the question is about the design; the model is
  told to give the graphical client's steps first, the terminal client in a
  sentence, the CLI only when asked, and to use the UN-RFCs only to explain why.

## [0.2.1] - 2026-10-25

### Changed

- The bot's profile links groups as `unseenet:<group-id>`, the form clients from unseenet 0.5 open (unseenet#386), instead of `unseenet:join?g=`.

## [0.2.0] - 2026-10-25

For unseenet 0.5 (`unseenet>=0.5,<0.6`); update the nodes first. The help bot learns from earlier answered threads.

### Added

- **Learning from earlier answered threads** (#5): a question in the help group
  that someone other than the asker answered - a person, never a bot - becomes
  a source, with a link to the thread, at most two in an answer. The prompt
  says to prefer the docs, as an earlier answer may be out of date.
  `learn_from_threads = false` turns it off.

## [0.1.0] - 2026-10-22

The first release. Works with unseenet 0.4 (`unseenet>=0.4.1,<0.5`).

### Added

- A help bot that answers questions in `unseenet.help` from the docs, with a
  local model behind an OpenAI-style API and a BM25 index of the documents.
- It knows every public repository of the organisation: their Markdown
  files, the UN-RFCs, issues and pull requests, and new repositories
  automatically; each repository gets a section from its description.
- Answering rules: citations only of excerpts it was given, a translated
  keyword step for questions in other languages, and stepping in on chat
  lines that ask something and have had no answer for 10 minutes.
- A bot mark in its profile; other bots are skipped by their profiles.
- An install script for Ubuntu servers (systemd, unbuffered output for the
  journal).
- It ripens its key on to level 3 while running, posting through the core's
  `Session` (#6).

[Unreleased]: https://github.com/unseenet/unseenet-helpbot/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/unseenet/unseenet-helpbot/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/unseenet/unseenet-helpbot/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/unseenet/unseenet-helpbot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/unseenet/unseenet-helpbot/releases/tag/v0.1.0
