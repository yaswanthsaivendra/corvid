# Changelog

Notable changes per release, based on [Keep a Changelog](https://keepachangelog.com/).

## [v0.1.0] - 2026-09-04

Initial release: a local coding agent built from scratch. Full writeup:
[docs/v0.1.0-building-a-coding-agent.md](docs/v0.1.0-building-a-coding-agent.md).

### Added
- Agent loop with a session (message history) passed as context on each call.
- Tools: `read_file`, `list_dir`, `write_file`, `run_shell`.
- Approval gate on file writes and shell commands.
- Error handling and transient API retries.
- Model-agnostic OpenAI-compatible backend.
