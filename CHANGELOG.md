# Changelog

All notable changes to Corvid are documented here. This project follows
[semantic versioning](https://semver.org/), and the format is based on
[Keep a Changelog](https://keepachangelog.com/).

## [v0.1.0] - 2026-09-04

Initial release: a local coding agent built from scratch (Stage A).
Writeup: [docs/v0.1.0-building-a-coding-agent.md](docs/v0.1.0-building-a-coding-agent.md).

### Added
- Agent loop: an outer loop per user turn and an inner loop that runs until the model is done.
- Session as an append-only message log, re-sent as context on every model call.
- Tools: `read_file` (line-numbered, size-capped), `list_dir`, `write_file`, `run_shell` (timeout + output truncation).
- Tool-calling protocol from scratch (OpenAI-compatible schema, registry, dispatch).
- Approval gate on world-changing tools (`write_file`, `run_shell`), default-deny.
- Error handling: tool failures return as feedback instead of crashing; model call retries transient errors with backoff.
- Model-agnostic backend over an OpenAI-compatible API (built against Groq `openai/gpt-oss-120b`).
