# Changelog

All notable changes to unseenet-helpbot are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/) on the same principles as
[unseenet](https://github.com/unseenet/unseenet/blob/main/docs/development.md#versioning).

## [Unreleased]

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

[Unreleased]: https://github.com/unseenet/unseenet-helpbot/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/unseenet/unseenet-helpbot/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/unseenet/unseenet-helpbot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/unseenet/unseenet-helpbot/releases/tag/v0.1.0
