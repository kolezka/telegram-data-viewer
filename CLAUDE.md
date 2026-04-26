# CLAUDE.md

## Project Overview

Telegram data extraction, decryption, and visualization toolkit for macOS. Extracts deleted messages, secret chats, and creates offline archives.

## Architecture

```
extract/tg-backup.sh → extract/tg_appstore_decrypt.py → extract/postbox_parser.py → python -m webui (in api/)
```

`tg-viewer` orchestrates this pipeline. It decrypts `.tempkeyEncrypted` (AES-CBC with SHA-512 of password), opens SQLCipher with `PRAGMA cipher_default_plaintext_header_size = 32`, and parses Postbox binary format from tables t2 (peers) and t7 (messages).

Legacy pipeline (`extract/extract-keys.sh` + `extract/tg_decrypt.py`) still exists but is not used by `tg-viewer`.

## Key files

| File | Purpose |
|------|---------|
| `tg-viewer` | CLI orchestrator (bash) — `full`, `backup`, `decrypt`, `parse`, `webui`, `clean` |
| `extract/tg-backup.sh` | Backup Telegram data from macOS (supports `--batch` for non-interactive use) |
| `extract/tg_appstore_decrypt.py` | Decrypt .tempkeyEncrypted + open SQLCipher databases |
| `extract/postbox_parser.py` | Parse Postbox binary format, extract messages/peers/conversations |
| `extract/redact.py` | Console output redaction helpers |
| `api/webui/` | FastAPI backend package — `python -m webui` (with `cwd=api/`) |
| `api/templates/index.html` | Transitional inline-JS frontend (deleted in Phase 2b) |
| `web/` | Phase 2b React + Bun frontend (placeholder for now) |
| `extract/extract-keys.sh` | Extract keys from Keychain (legacy) |
| `extract/tg_decrypt.py` | Legacy decryptor (tries multiple key formats) |

## Development commands

```bash
# Full workflow (backup + decrypt + parse + web UI)
./tg-viewer full

# Individual steps
./tg-viewer backup ./data
./tg-viewer decrypt ./data/tg_*/
./tg-viewer parse ./data/tg_*/
./tg-viewer webui ./data/tg_*/parsed_data

# Cleanup generated data
./tg-viewer clean
```

## Technical notes

- SQLCipher config: `cipher_default_plaintext_header_size = 32`, raw key mode (key + salt = 48 bytes hex)
- Default password: `"no-matter-key"` (when no local passcode set)
- Key verification: MurmurHash3 x86_32 with seed `0xF7CA7FD2`
- Postbox peer tags: `02fn04` (first_name), `02ln04` (last_name), `02un04` (username), `01t04` (title)
- t7 message key: peer_id(8b BE) + padding(4b) + timestamp(4b BE) + namespace(4b BE)
- Secret chat remote peer: field `r` (`01 72 01` + user_id as LE int32/int64)
- Backup directories (`tg_*`, `test-data/`) are gitignored
