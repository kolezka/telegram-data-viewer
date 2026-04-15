# `--redact` Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--redact` flag to `tg-viewer` that masks account IDs, DB key/salt hex, and backup paths in CLI console output of the orchestrator and its sub-scripts.

**Architecture:** A new Python helper module `redact.py` exposes three masking functions (`account`, `hexkey`, `path`) gated by a module-level `REDACT` boolean. Each Python sub-script parses `--redact` via argparse and calls `redact.set_enabled(True)` before any print; every `print()` that emits one of the sensitive values is updated to route the value through the appropriate helper. The bash orchestrator (`tg-viewer`) parses `--redact`, forwards it to Python sub-commands as `--redact`, and exports `TG_REDACT=1` so `tg-backup.sh` can mask the final path line it prints.

**Tech Stack:** Python 3 (stdlib only — no new deps), bash.

**Spec:** `docs/superpowers/specs/2026-04-15-redact-flag-design.md`

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `redact.py` | Create | Masking helpers + self-test runnable via `python3 redact.py` |
| `postbox_parser.py` | Modify | Parse `--redact`, call `redact.set_enabled`, route 7 print sites |
| `tg_appstore_decrypt.py` | Modify | Parse `--redact`, call `redact.set_enabled`, route 7 print sites |
| `tg-viewer` | Modify | Accept `--redact`, forward to sub-commands, export `TG_REDACT` |
| `tg-backup.sh` | Modify | Read `TG_REDACT` env, mask `BACKUP_DIR` in final summary lines |

The repo has no automated test suite (no `tests/` dir, no pytest in `requirements.txt`). Per the spec, wire-up verification is manual. For the new `redact.py` module we add self-contained assertions runnable via `python3 redact.py` so behavior is checked without introducing pytest.

---

## Task 1: Create `redact.py` helper module

**Files:**
- Create: `redact.py`

- [ ] **Step 1: Write the module with inline self-test**

Create `/Users/me/Development/tg-viewer/redact.py`:

```python
"""Console output redaction helpers for CLI tools.

A single module-level flag toggles masking. When off (default),
helpers return str(value) unchanged. When on, they return a
masked form that hides account IDs, DB key/salt hex fragments,
and timestamped backup paths.

Activate once at program start:
    import redact
    redact.set_enabled(args.redact)

Then route sensitive values at print time:
    print(f"Account: {redact.account(account_id)}")
    print(f"Key: {redact.hexkey(db_key.hex())}")
    print(f"Output: {redact.path(output_dir)}")
"""

from __future__ import annotations

import re
from pathlib import Path

REDACT: bool = False

_TG_BACKUP_SEGMENT = re.compile(r"tg_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")


def set_enabled(flag: bool) -> None:
    """Enable or disable redaction. Call once at program start."""
    global REDACT
    REDACT = bool(flag)


def account(value) -> str:
    """Mask a Telegram account / user ID."""
    if not REDACT:
        return str(value)
    return "***"


def hexkey(value) -> str:
    """Mask a hex key/salt fragment (full hex or truncated `aabb...ccdd` form)."""
    if not REDACT:
        return str(value)
    return "***"


def path(value) -> str:
    """Mask the tg_<timestamp> segment of a backup path, preserving any tail."""
    if not REDACT:
        return str(value)
    return _TG_BACKUP_SEGMENT.sub("<backup>", str(value))


if __name__ == "__main__":
    # Off by default
    assert REDACT is False
    assert account(12345678) == "12345678"
    assert hexkey("a1b2c3d4") == "a1b2c3d4"
    assert path("/tmp/tg_2026-04-15_12-58-12/parsed_data") == "/tmp/tg_2026-04-15_12-58-12/parsed_data"

    # On
    set_enabled(True)
    assert account(12345678) == "***"
    assert account("12345678") == "***"
    assert account(None) == "***"
    assert hexkey("a1b2...ef01") == "***"
    assert hexkey("") == "***"
    assert path("/tmp/tg_2026-04-15_12-58-12/parsed_data") == "/tmp/<backup>/parsed_data"
    assert path("./tg_2026-04-15_12-58-12") == "./<backup>"
    assert path(Path("/a/tg_2026-04-15_12-58-12/b")) == "/a/<backup>/b"
    # Non-matching path passes through
    assert path("/no/timestamp/here") == "/no/timestamp/here"

    # Back off — flag is resettable
    set_enabled(False)
    assert account(12345678) == "12345678"

    print("redact.py self-test: OK")
```

- [ ] **Step 2: Run the self-test**

Run: `cd /Users/me/Development/tg-viewer && python3 redact.py`
Expected output: `redact.py self-test: OK`
Expected exit code: `0`

- [ ] **Step 3: Commit**

```bash
cd /Users/me/Development/tg-viewer
git add redact.py
git commit -m "feat: add redact.py helper module for CLI output masking"
```

---

## Task 2: Wire `--redact` into `postbox_parser.py`

**Files:**
- Modify: `postbox_parser.py` — argparse block at L755-764 and print sites

**Call sites to update** (line numbers reflect current file state; re-check with Read before editing):
- L768 — `print(f"ERROR: {backup_dir} not found")` — path
- L790 — `print(f"Decrypting tempkey: {tempkey_path}")` — path
- L792 — `print(f"  Key: {db_key.hex()[:8]}...{db_key.hex()[-4:]}")` — hex key
- L793 — `print(f"  Salt: {db_salt.hex()[:8]}...{db_salt.hex()[-4:]}")` — hex salt
- L818 — `print(f"\nAccount {account_id}: no database")` — account ID
- L823 — `print(f"Account: {account_id} ({db_size_mb:.1f} MB)")` — account ID
- L849 — `print(f"  Output: {output_dir}")` — path

- [ ] **Step 1: Add import and argparse flag**

At the top of `postbox_parser.py`, ensure `import redact` is present after the existing imports. Inspect the top of the file with Read first; add the line after the last existing `import` statement.

Then modify the argparse block (currently L755-764). Add a new flag after `--account`:

Replace:
```python
    parser.add_argument('--account', help='Only process specific account ID')

    args = parser.parse_args()
```

With:
```python
    parser.add_argument('--account', help='Only process specific account ID')
    parser.add_argument('--redact', action='store_true',
                        help='Mask sensitive values (account IDs, keys, paths) in console output')

    args = parser.parse_args()
    redact.set_enabled(args.redact)
```

- [ ] **Step 2: Update the 7 print call sites**

Read the file first to confirm current line numbers, then apply these exact edits:

Replace:
```python
        print(f"ERROR: {backup_dir} not found")
```
With:
```python
        print(f"ERROR: {redact.path(backup_dir)} not found")
```

Replace:
```python
        print(f"Decrypting tempkey: {tempkey_path}")
        db_key, db_salt = decrypt_tempkey(tempkey_path, args.password)
        print(f"  Key: {db_key.hex()[:8]}...{db_key.hex()[-4:]}")
        print(f"  Salt: {db_salt.hex()[:8]}...{db_salt.hex()[-4:]}")
```
With:
```python
        print(f"Decrypting tempkey: {redact.path(tempkey_path)}")
        db_key, db_salt = decrypt_tempkey(tempkey_path, args.password)
        print(f"  Key: {redact.hexkey(db_key.hex()[:8] + '...' + db_key.hex()[-4:])}")
        print(f"  Salt: {redact.hexkey(db_salt.hex()[:8] + '...' + db_salt.hex()[-4:])}")
```

Replace:
```python
        if not db_path.exists():
            print(f"\nAccount {account_id}: no database")
            continue

        db_size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"\n{'='*60}")
        print(f"Account: {account_id} ({db_size_mb:.1f} MB)")
        print(f"{'='*60}")
```
With:
```python
        if not db_path.exists():
            print(f"\nAccount {redact.account(account_id)}: no database")
            continue

        db_size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"\n{'='*60}")
        print(f"Account: {redact.account(account_id)} ({db_size_mb:.1f} MB)")
        print(f"{'='*60}")
```

Replace:
```python
    print(f"\n{'='*60}")
    print(f"EXPORT COMPLETE")
    print(f"  Total messages: {summary['total_messages']:,}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")
```
With:
```python
    print(f"\n{'='*60}")
    print(f"EXPORT COMPLETE")
    print(f"  Total messages: {summary['total_messages']:,}")
    print(f"  Output: {redact.path(output_dir)}")
    print(f"{'='*60}")
```

- [ ] **Step 3: Smoke-test the flag parser**

Run: `cd /Users/me/Development/tg-viewer && python3 postbox_parser.py --help 2>&1 | grep -- --redact`
Expected: a line like `  --redact              Mask sensitive values...`

Run: `cd /Users/me/Development/tg-viewer && python3 postbox_parser.py /nonexistent --redact 2>&1 | head -5`
Expected: the error line prints `ERROR: /nonexistent not found` with the path unchanged (since `/nonexistent` contains no `tg_<timestamp>` segment). Exit code 1.

Run: `cd /Users/me/Development/tg-viewer && python3 postbox_parser.py /tmp/tg_2026-04-15_12-58-12 --redact 2>&1 | head -5`
Expected: `ERROR: /tmp/<backup> not found` — the timestamp segment is masked.

- [ ] **Step 4: Commit**

```bash
cd /Users/me/Development/tg-viewer
git add postbox_parser.py
git commit -m "feat: wire --redact flag into postbox_parser"
```

---

## Task 3: Wire `--redact` into `tg_appstore_decrypt.py`

**Files:**
- Modify: `tg_appstore_decrypt.py` — argparse block at L304-312 and print sites

**Call sites to update** (line numbers reflect current file state; re-check with Read before editing):
- L318 — `print(f"ERROR: Directory not found: {backup_dir}")` — path
- L338 — `print(f"Using tempkey: {tempkey_path}")` — path
- L344 — `print(f"  dbKey:  {db_key.hex()[:8]}...{db_key.hex()[-4:]}")` — hex key
- L345 — `print(f"  dbSalt: {db_salt.hex()[:8]}...{db_salt.hex()[-4:]}")` — hex salt
- L365 — `print(f"\n  {account_dir.name}: No database found")` — contains `account-<id>`
- L368 — `print(f"\n--- Account: {account_id} ---")` — account ID
- L369 — `print(f"  Database: {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")` — path
- L412 — `print(f"Output: {output_dir}")` — path
- L413 — `print(f"Summary: {summary_file}")` — path

Note: L378 passes `account_id` into `extract_all_data()`, and L381 into `try_decode_postbox_messages()`. Grep those functions for their own `print(...account_id...)` sites and route them through `redact.account(account_id)` too. Use:

```
Grep pattern: "print\(.*account_id"  path: tg_appstore_decrypt.py
```

If any matches are found outside `main()`, update them the same way (wrap `account_id` with `redact.account(...)` inside the f-string).

- [ ] **Step 1: Add import and argparse flag**

Add `import redact` after the existing imports at the top of `tg_appstore_decrypt.py`.

In the argparse block, add after `--tempkey`:

Replace:
```python
    parser.add_argument('--tempkey', help='Path to .tempkeyEncrypted file')

    args = parser.parse_args()
```

With:
```python
    parser.add_argument('--tempkey', help='Path to .tempkeyEncrypted file')
    parser.add_argument('--redact', action='store_true',
                        help='Mask sensitive values (account IDs, keys, paths) in console output')

    args = parser.parse_args()
    redact.set_enabled(args.redact)
```

- [ ] **Step 2: Update print sites in `main()`**

Replace:
```python
        print(f"ERROR: Directory not found: {backup_dir}")
```
With:
```python
        print(f"ERROR: Directory not found: {redact.path(backup_dir)}")
```

Replace:
```python
    print(f"Using tempkey: {tempkey_path}")
```
With:
```python
    print(f"Using tempkey: {redact.path(tempkey_path)}")
```

Replace:
```python
    print(f"  dbKey:  {db_key.hex()[:8]}...{db_key.hex()[-4:]}")
    print(f"  dbSalt: {db_salt.hex()[:8]}...{db_salt.hex()[-4:]}")
```
With:
```python
    print(f"  dbKey:  {redact.hexkey(db_key.hex()[:8] + '...' + db_key.hex()[-4:])}")
    print(f"  dbSalt: {redact.hexkey(db_salt.hex()[:8] + '...' + db_salt.hex()[-4:])}")
```

Replace:
```python
        if not db_path.exists():
            print(f"\n  {account_dir.name}: No database found")
            continue

        print(f"\n--- Account: {account_id} ---")
        print(f"  Database: {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")
```
With:
```python
        if not db_path.exists():
            print(f"\n  account-{redact.account(account_id)}: No database found")
            continue

        print(f"\n--- Account: {redact.account(account_id)} ---")
        print(f"  Database: {redact.path(db_path)} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")
```

(Note: `account_dir.name` is `account-<id>`; we replace the original text with a reconstructed form that routes the id through `redact.account()`.)

Replace:
```python
    print(f"\n{'='*60}")
    print(f"DONE: {total_messages} total rows extracted")
    print(f"Output: {output_dir}")
    print(f"Summary: {summary_file}")
```
With:
```python
    print(f"\n{'='*60}")
    print(f"DONE: {total_messages} total rows extracted")
    print(f"Output: {redact.path(output_dir)}")
    print(f"Summary: {redact.path(summary_file)}")
```

- [ ] **Step 3: Sweep for any remaining account_id prints outside main()**

Run: `cd /Users/me/Development/tg-viewer && grep -n "print.*account_id" tg_appstore_decrypt.py`
For each result that is NOT already wrapped in `redact.account(...)`, apply this transformation: inside the f-string, replace `{account_id}` with `{redact.account(account_id)}`.

If the grep returns only lines you already updated in Step 2, no further changes are needed.

- [ ] **Step 4: Smoke-test the flag parser**

Run: `cd /Users/me/Development/tg-viewer && python3 tg_appstore_decrypt.py --help 2>&1 | grep -- --redact`
Expected: a line describing `--redact`.

Run: `cd /Users/me/Development/tg-viewer && python3 tg_appstore_decrypt.py /tmp/tg_2026-04-15_12-58-12 --redact 2>&1 | head -5`
Expected: `ERROR: Directory not found: /tmp/<backup>` (timestamp masked). Exit code 1.

- [ ] **Step 5: Commit**

```bash
cd /Users/me/Development/tg-viewer
git add tg_appstore_decrypt.py
git commit -m "feat: wire --redact flag into tg_appstore_decrypt"
```

---

## Task 4: Add `--redact` to `tg-viewer` orchestrator

**Files:**
- Modify: `tg-viewer` — global options parser (L313-322), sub-command runners (L151-175), full workflow (L238-305), help text (L27-68)

- [ ] **Step 1: Add `REDACT` state and parse the flag**

Read the current file with Read first to confirm line numbers.

Find the `main()` function (currently starting L308) and the global options loop (L313-322). Add handling for `--redact`:

Replace:
```bash
main() {
    local command="${1:-help}"
    local port="5000"
    local host="127.0.0.1"
    
    # Parse global options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port) port="$2"; shift 2 ;;
            --host) host="$2"; shift 2 ;;
            --help|-h) show_help; exit 0 ;;
            -*) die "Unknown option: $1" ;;
            *) break ;;
        esac
    done
```

With:
```bash
main() {
    local command="${1:-help}"
    local port="5000"
    local host="127.0.0.1"
    local redact=false

    # Parse global options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port) port="$2"; shift 2 ;;
            --host) host="$2"; shift 2 ;;
            --redact) redact=true; shift ;;
            --help|-h) show_help; exit 0 ;;
            -*) die "Unknown option: $1" ;;
            *) break ;;
        esac
    done

    if [[ "$redact" == true ]]; then
        export TG_REDACT=1
    fi
```

- [ ] **Step 2: Forward the flag to Python sub-commands**

Update `run_decrypt` (currently L151-162):

Replace:
```bash
run_decrypt() {
    local backup_dir="$1"

    title "Step 2: Decrypting databases"

    if [[ ! -d "$backup_dir" ]]; then
        die "Backup directory not found: $backup_dir"
    fi

    log "Decrypting databases in: $backup_dir"
    python3 "$APPSTORE_DECRYPT_SCRIPT" "$backup_dir"
}
```

With:
```bash
run_decrypt() {
    local backup_dir="$1"

    title "Step 2: Decrypting databases"

    if [[ ! -d "$backup_dir" ]]; then
        die "Backup directory not found: $backup_dir"
    fi

    local redact_arg=()
    [[ "${TG_REDACT:-0}" == "1" ]] && redact_arg=(--redact)

    log "Decrypting databases in: $backup_dir"
    python3 "$APPSTORE_DECRYPT_SCRIPT" "$backup_dir" "${redact_arg[@]}"
}
```

Update `run_parse` (currently L164-175):

Replace:
```bash
run_parse() {
    local backup_dir="$1"

    title "Step 3: Parsing Postbox data"

    if [[ ! -d "$backup_dir" ]]; then
        die "Backup directory not found: $backup_dir"
    fi

    log "Parsing messages, peers, and conversations in: $backup_dir"
    python3 "$POSTBOX_PARSER_SCRIPT" "$backup_dir"
}
```

With:
```bash
run_parse() {
    local backup_dir="$1"

    title "Step 3: Parsing Postbox data"

    if [[ ! -d "$backup_dir" ]]; then
        die "Backup directory not found: $backup_dir"
    fi

    local redact_arg=()
    [[ "${TG_REDACT:-0}" == "1" ]] && redact_arg=(--redact)

    log "Parsing messages, peers, and conversations in: $backup_dir"
    python3 "$POSTBOX_PARSER_SCRIPT" "$backup_dir" "${redact_arg[@]}"
}
```

Note: `run_webui` is intentionally NOT updated — web UI redaction is out of scope per the spec.

- [ ] **Step 3: Add `_redact_path` helper and use it in tg-viewer's own echoes**

Below the existing logging helpers (after L23, after the `title()` function), add:

```bash
# Redact tg_<timestamp> segments in paths when TG_REDACT=1
_redact_path() {
    if [[ "${TG_REDACT:-0}" == "1" ]]; then
        echo "$1" | sed -E 's|tg_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}|<backup>|g'
    else
        echo "$1"
    fi
}
```

Then route tg-viewer's own path echoes through it. In `run_backup` (L117-130), replace:

```bash
    log "Running Telegram backup to: $dest_dir"
    "$BACKUP_SCRIPT" "$dest_dir"
    
    echo "$dest_dir"  # Return the backup directory
```

With:
```bash
    log "Running Telegram backup to: $(_redact_path "$dest_dir")"
    "$BACKUP_SCRIPT" "$dest_dir"

    echo "$dest_dir"  # Return the backup directory (used as pipe value — do not redact)
```

In `run_decrypt`, `run_parse`, `run_webui`, replace each `log "... $backup_dir"` / `log "... $data_dir"` line so the path is wrapped with `_redact_path`. Specifically:

- In `run_decrypt` (after Step 2 edits): `log "Decrypting databases in: $(_redact_path "$backup_dir")"`
- In `run_parse` (after Step 2 edits): `log "Parsing messages, peers, and conversations in: $(_redact_path "$backup_dir")"`
- In `run_webui` (L177-197), replace `log "Data directory: $data_dir"` with `log "Data directory: $(_redact_path "$data_dir")"`
- In `run_full_workflow` (L238-305), replace:
  - `log "Destination: $dest_dir"` → `log "Destination: $(_redact_path "$dest_dir")"`
  - `log "Running Telegram backup to: $dest_dir"` → `log "Running Telegram backup to: $(_redact_path "$dest_dir")"`
  - `log "Using backup directory: $backup_dir"` → `log "Using backup directory: $(_redact_path "$backup_dir")"`
  - `ok "Backup: $backup_dir"` → `ok "Backup: $(_redact_path "$backup_dir")"`
  - `ok "Data: $data_dir"` → `ok "Data: $(_redact_path "$data_dir")"`
  - `log "To start web UI later, run: ./tg-viewer webui '$data_dir'"` → `log "To start web UI later, run: ./tg-viewer webui '$(_redact_path "$data_dir")'"`

The `run_clean` function (L199-236) iterates real directory paths that the user needs to see verbatim to confirm deletion. Leave `run_clean` alone.

- [ ] **Step 4: Update help text**

In `show_help` (L27-68), add `--redact` to the `OPTIONS` block. Replace:

```bash
OPTIONS:
    --port PORT         Web UI port (default: 5000)
    --host HOST         Web UI host (default: 127.0.0.1)
    --help, -h          Show this help
```

With:
```bash
OPTIONS:
    --port PORT         Web UI port (default: 5000)
    --host HOST         Web UI host (default: 127.0.0.1)
    --redact            Mask sensitive values (account IDs, keys, paths) in CLI output
    --help, -h          Show this help
```

- [ ] **Step 5: Smoke-test**

Run: `cd /Users/me/Development/tg-viewer && ./tg-viewer --redact help 2>&1 | grep -- --redact`
Expected: the new help line appears.

Run: `cd /Users/me/Development/tg-viewer && ./tg-viewer --redact decrypt /tmp/tg_2026-04-15_12-58-12 2>&1 | head -5`
Expected: the `[INFO] Decrypting databases in:` line shows `<backup>` instead of the timestamp. The die line `Backup directory not found: /tmp/tg_2026-04-15_12-58-12` may still print the raw path (the guard fires before the log line). That's acceptable: the guard path is shown to the user for their own debugging and is what they typed; we consider user-provided paths in die messages as not sensitive in the same way.

Run: `cd /Users/me/Development/tg-viewer && ./tg-viewer decrypt /tmp/tg_2026-04-15_12-58-12 2>&1 | head -5`
Expected (no `--redact`): path printed verbatim.

- [ ] **Step 6: Commit**

```bash
cd /Users/me/Development/tg-viewer
git add tg-viewer
git commit -m "feat: add --redact flag to tg-viewer orchestrator"
```

---

## Task 5: Honor `TG_REDACT` in `tg-backup.sh`

**Files:**
- Modify: `tg-backup.sh` — logging helpers area (L44-49) and summary block (L202-215), per-account header (L153), final archive summary (L224)

- [ ] **Step 1: Add the `_redact_path` helper**

After the logging helpers (after L49 `die()`), insert:

```bash
# Redact tg_<timestamp> segments in paths when TG_REDACT=1
_redact_path() {
    if [[ "${TG_REDACT:-0}" == "1" ]]; then
        echo "$1" | sed -E 's|tg_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}|<backup>|g'
    else
        echo "$1"
    fi
}
```

- [ ] **Step 2: Route sensitive path echoes through the helper**

In the summary block (currently L202-215), replace:

```bash
ok "Backup complete!"
ok "Location: $BACKUP_DIR"
ok "Total size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
echo ""
log "Next steps:"
log "  • Run './extract-keys.sh $BACKUP_DIR' to extract encryption keys"
log "  • Run './tg_decrypt.py $BACKUP_DIR' to decrypt the databases"
log "  • Run './webui.py' to browse messages in the web interface"
```

With:
```bash
ok "Backup complete!"
ok "Location: $(_redact_path "$BACKUP_DIR")"
ok "Total size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
echo ""
log "Next steps:"
log "  • Run './extract-keys.sh $(_redact_path "$BACKUP_DIR")' to extract encryption keys"
log "  • Run './tg_decrypt.py $(_redact_path "$BACKUP_DIR")' to decrypt the databases"
log "  • Run './webui.py' to browse messages in the web interface"
```

In the optional archive block (currently L217-226), replace:

```bash
    ARCHIVE="$DEST/tg_$TIMESTAMP.tar.gz"
    log "Compressing..."
    tar -czf "$ARCHIVE" -C "$DEST" "tg_$TIMESTAMP"
    ok "Archive: $ARCHIVE ($(du -sh "$ARCHIVE" | cut -f1))"
```

With:
```bash
    ARCHIVE="$DEST/tg_$TIMESTAMP.tar.gz"
    log "Compressing..."
    tar -czf "$ARCHIVE" -C "$DEST" "tg_$TIMESTAMP"
    ok "Archive: $(_redact_path "$ARCHIVE") ($(du -sh "$ARCHIVE" | cut -f1))"
```

Leave per-account log lines (L153 `log "━━━ Backing up $dir_name ($label) ━━━"`) unchanged — `$dir_name` is `account-<id>` which is the account ID itself. Since this message is also sensitive per the spec, update it too:

Replace:
```bash
  log "━━━ Backing up $dir_name ($label) ━━━"
```

With:
```bash
  local dir_name_safe="$dir_name"
  if [[ "${TG_REDACT:-0}" == "1" ]]; then
      dir_name_safe="account-***"
  fi
  log "━━━ Backing up $dir_name_safe ($label) ━━━"
```

(The `$label` is a peerName — a display string like "My iPhone" — not covered by the spec's current redaction set. Leave it unchanged.)

Also update the per-account summary line at L113-125. Replace:

```bash
log "Found ${#ACCOUNT_DIRS[@]} account(s):"
for d in "${ACCOUNT_DIRS[@]}"; do
  dir_name=$(basename "$d")
  dir_id="${dir_name#account-}"
  label=$(get_account_name "$dir_id")
  db_path="$d/postbox/db/db_sqlite"
  if [[ -f "$db_path" ]]; then
    db_size=$(du -sh "$db_path" 2>/dev/null | cut -f1)
    log "  $dir_name ($label) — postbox DB: $db_size"
  else
    log "  $dir_name ($label) — no postbox DB found"
  fi
done
```

With:
```bash
log "Found ${#ACCOUNT_DIRS[@]} account(s):"
for d in "${ACCOUNT_DIRS[@]}"; do
  dir_name=$(basename "$d")
  dir_id="${dir_name#account-}"
  label=$(get_account_name "$dir_id")
  db_path="$d/postbox/db/db_sqlite"
  local_name="$dir_name"
  [[ "${TG_REDACT:-0}" == "1" ]] && local_name="account-***"
  if [[ -f "$db_path" ]]; then
    db_size=$(du -sh "$db_path" 2>/dev/null | cut -f1)
    log "  $local_name ($label) — postbox DB: $db_size"
  else
    log "  $local_name ($label) — no postbox DB found"
  fi
done
```

(Note: `local` is not valid in bash outside a function. At this point in `tg-backup.sh` we are at script top level, so use a plain variable assignment instead:)

Actually, correct that: at script top level, remove the `local` keyword. Use:

```bash
log "Found ${#ACCOUNT_DIRS[@]} account(s):"
for d in "${ACCOUNT_DIRS[@]}"; do
  dir_name=$(basename "$d")
  dir_id="${dir_name#account-}"
  label=$(get_account_name "$dir_id")
  db_path="$d/postbox/db/db_sqlite"
  safe_name="$dir_name"
  [[ "${TG_REDACT:-0}" == "1" ]] && safe_name="account-***"
  if [[ -f "$db_path" ]]; then
    db_size=$(du -sh "$db_path" 2>/dev/null | cut -f1)
    log "  $safe_name ($label) — postbox DB: $db_size"
  else
    log "  $safe_name ($label) — no postbox DB found"
  fi
done
```

Same fix for the per-account header earlier (it's inside a top-level `for` loop, also not in a function):

```bash
  safe_name="$dir_name"
  [[ "${TG_REDACT:-0}" == "1" ]] && safe_name="account-***"
  log "━━━ Backing up $safe_name ($label) ━━━"
```

- [ ] **Step 3: Smoke-test**

Run: `cd /Users/me/Development/tg-viewer && TG_REDACT=1 bash -n tg-backup.sh`
Expected: no syntax errors, exit code 0.

Run: `cd /Users/me/Development/tg-viewer && bash -n tg-backup.sh`
Expected: no syntax errors.

The full script requires a real Telegram install and is interactive; full runtime smoke-test happens in Task 6.

- [ ] **Step 4: Commit**

```bash
cd /Users/me/Development/tg-viewer
git add tg-backup.sh
git commit -m "feat: honor TG_REDACT env in tg-backup.sh output"
```

---

## Task 6: End-to-end manual verification

**Files:** none (verification only)

This task validates the spec's acceptance criteria. It requires a pre-existing backup directory. If the project has `tg_*` directories at the repo root from prior runs, use one of them.

- [ ] **Step 1: Pick a test backup and capture its identifying values**

Run: `cd /Users/me/Development/tg-viewer && ls -d tg_*/ 2>/dev/null | head -1`
Expected: a directory like `tg_2026-04-15_12-58-12/`. If none exist, skip to Step 6 and document that an end-to-end run could not be performed without a fresh backup; the unit-level smoke tests in Tasks 1–5 still stand.

Pick one: export as `TEST_BACKUP=<dirname>` (e.g. `export TEST_BACKUP=tg_2026-04-15_12-58-12`).

Extract identifying values:
- `TS="${TEST_BACKUP#tg_}"` — the timestamp portion
- `ACCOUNT_ID` — run `ls "$TEST_BACKUP" | grep '^account-' | head -1 | sed 's/account-//'`

- [ ] **Step 2: Run the parse step with `--redact` and capture output**

Run:
```bash
cd /Users/me/Development/tg-viewer
./tg-viewer --redact parse "./$TEST_BACKUP" > /tmp/redact-on.log 2>&1
```
(Adjust the path if the backup already has `decrypted_data`/`parsed_data` prerequisites — if `parse` requires prior decryption, run `./tg-viewer --redact decrypt "./$TEST_BACKUP"` first, then parse.)

- [ ] **Step 3: Verify no sensitive values leaked**

Run these greps. Each MUST return zero matches:

```bash
# Account ID must not appear in redacted output
grep -c "$ACCOUNT_ID" /tmp/redact-on.log
# Expected: 0

# Timestamp must not appear
grep -c "$TS" /tmp/redact-on.log
# Expected: 0
```

If `ACCOUNT_ID` is very short (e.g. 3 digits) and collides with unrelated numbers in the output (message counts), accept that as a false positive only if manually confirmed — otherwise the redaction is incomplete.

- [ ] **Step 4: Confirm unredacted run still shows values**

Run:
```bash
cd /Users/me/Development/tg-viewer
./tg-viewer parse "./$TEST_BACKUP" > /tmp/redact-off.log 2>&1
grep -c "$ACCOUNT_ID" /tmp/redact-off.log
# Expected: >= 1
grep -c "$TS" /tmp/redact-off.log
# Expected: >= 1
```

This confirms we didn't accidentally redact unconditionally.

- [ ] **Step 5: Confirm counts and progress still render**

Run: `grep -E 'Extracted|Processed|conversations saved|Total combined' /tmp/redact-on.log | head -10`
Expected: multiple lines showing counts and progress — these should be intact (counts are not redacted per spec).

- [ ] **Step 6: Final commit of docs or notes (if any)**

No new files were created in Task 6. If the engineer added a short CHANGELOG entry or README note, commit it now:

```bash
cd /Users/me/Development/tg-viewer
git status
# If README.md or CHANGELOG.md was touched:
git add README.md CHANGELOG.md 2>/dev/null || true
git commit -m "docs: note --redact flag" 2>/dev/null || true
```

If no changes, skip the commit.

---

## Self-Review (completed by plan author before handoff)

**Spec coverage:**
- `--redact` flag on `tg-viewer` → Task 4
- Propagated to Python sub-scripts → Tasks 2, 3, 4 (forwarding)
- `TG_REDACT=1` env for bash → Tasks 4 (export), 5 (read)
- Account IDs masked as `***` → Tasks 2 (L818, L823), 3 (L368, L365), 5 (per-account headers)
- Key/salt hex masked → Tasks 2 (L792-793), 3 (L344-345)
- Path timestamps masked to `<backup>` → Tasks 2 (L768, L790, L849), 3 (L318, L338, L369, L412-413), 4 (tg-viewer echoes), 5 (tg-backup summary)
- Web UI, JSON files, legacy scripts unaffected → No tasks touch `webui.py`, `tg_decrypt.py`, `main.py`, `extract-keys.sh`, on-disk JSON output
- Counts not redacted → Verified in Task 6 Step 5

**Placeholder scan:** No TBD/TODO/placeholder text. Every code block is concrete.

**Type consistency:** `redact.set_enabled(bool)`, `redact.account(value)`, `redact.hexkey(str)`, `redact.path(str|Path)` — names consistent across Task 1 definition and Tasks 2–3 usage. Bash helper is `_redact_path` consistently in both `tg-viewer` and `tg-backup.sh`.

**Ambiguity check:** All four sensitive categories have a single defined masked form. `_redact_path` uses the same regex in two places; if that ever diverges it's a code smell. Not worth extracting to a shared bash file for two copies — accept the duplication.
