# `--redact` flag for CLI output

## Problem

CLI output from `tg-viewer` and its sub-scripts prints values that are sensitive when shared in logs, bug reports, or screen recordings: the Telegram account ID, raw database key/salt hex fragments, and backup directory paths that embed a timestamp of when the backup was taken. A `--redact` flag should mask these in console output without changing any on-disk artifacts or web UI behavior.

## Scope

**In scope:** CLI stdout/stderr from `tg-viewer`, `postbox_parser.py`, `tg_appstore_decrypt.py`, and `tg-backup.sh`.

**Out of scope:**
- Web UI (`webui.py`) — still displays raw values.
- On-disk artifacts: parsed JSON, media, decrypted DB — still contain raw values.
- Message/peer content — never printed to console today; no change.
- Legacy scripts (`tg_decrypt.py`, `extract-keys.sh`, `main.py`) — not used by `tg-viewer` orchestrator; no change.

## User interface

```
tg-viewer --redact full
tg-viewer --redact parse ./data/tg_2026-04-15_12-58-12/
```

`--redact` is a top-level boolean flag on `tg-viewer`. When present, it is forwarded to each Python sub-command as `--redact`, and exported to the environment as `TG_REDACT=1` so `tg-backup.sh` can observe it.

Flag is off by default. No config file, no env-only mode — the flag is the single source of truth.

## Redaction rules

| Source value | Masked form |
|---|---|
| Account ID (numeric Telegram user ID) | `***` |
| DB key hex (full or truncated fragments like `a1b2...ef01`) | `***` |
| DB salt hex | `***` |
| Backup directory path `tg_<timestamp>/...` | `<backup>/...` (the `tg_<timestamp>` segment is replaced with `<backup>`; any tail inside is preserved) |

Counts (message count, peer count, file count, byte size) are **not** redacted — they are useful for support and don't identify a user.

## Architecture

One new module: `redact.py`.

```
redact.py
  REDACT: bool  (module-level, set once at startup)
  set_enabled(flag: bool) -> None
  account(id) -> str
  hexkey(s: str) -> str
  path(p: str | Path) -> str
```

Each helper returns `str(input)` unchanged when `REDACT` is false, and the masked form when true. No dependency on argparse — the calling script parses its flag and calls `set_enabled()` once before any print.

Every `print(...)` call that currently emits one of the four sensitive values routes its value through the corresponding helper. Call sites are identified by reviewing `print` statements in the three Python files; the current set (as of this spec) is:

- `postbox_parser.py`: account ID banner, key/salt preview lines, backup path lines in ERROR/EXPORT blocks.
- `tg_appstore_decrypt.py`: key/salt previews, backup path lines.
- `tg-viewer`: echo lines that print resolved paths and account IDs.
- `tg-backup.sh`: the "Backup saved to …" final line and any intermediate path echoes.

Bash scripts implement a tiny `_redact_path` shell function gated on `$TG_REDACT`; they do not import the Python helper.

## Data flow

```
user -> tg-viewer --redact <cmd>
         |
         +-- export TG_REDACT=1
         +-- pass --redact to python sub-command
         |
         v
      sub-script argparse -> redact.set_enabled(True)
         |
         v
      print(..., redact.account(id), redact.hexkey(k), redact.path(p))
```

## Error handling

- Unknown values passed to helpers (e.g. `None`, non-string) are coerced with `str()` before masking; masked output is still `***`.
- If `set_enabled()` is never called, `REDACT` defaults to `False` → behavior unchanged. This preserves backwards compatibility for any direct invocation of the sub-scripts.
- No new failure modes: helpers never raise.

## Testing

Manual verification — no automated test suite exists in this repo today, so this feature follows the same convention:

1. Run `./tg-viewer --redact full` against a test backup.
2. Capture full stdout+stderr.
3. `grep -E '<account_id>|<first-8-hex-of-key>|<tg_YYYY-MM-DD_HH-MM-SS>'` — must return zero matches.
4. Run without `--redact` against the same backup — the three values must appear as before (no accidental permanent redaction).
5. Spot-check that counts, progress lines, and error messages still render clearly.

## Non-goals / YAGNI

- No partial/hashed redaction modes — a single fully-masked form only.
- No per-value granularity (e.g. "redact only keys") — one flag covers all four categories.
- No web UI toggle — out of scope per design decision.
- No redaction of on-disk JSON — out of scope per design decision.
