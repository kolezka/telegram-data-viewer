# Phase 2a: Project Restructure (api/ + extract/) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the flat repo into three top-level subsystems — `api/` (FastAPI backend), `extract/` (Telegram backup/decrypt/parse pipeline), and `web/` (placeholder for the Phase 2b React frontend) — without changing any runtime behavior. The 33 pytest tests must still pass; the `tg-viewer` orchestrator must still work end-to-end.

**Architecture:** Pure refactor. Move files into subdirectories, update intra-package imports to be relative (`from . import redact`) or fully qualified (`from extract.postbox_parser import ...`), and update the bash orchestrator's path constants. The Python package name `webui` stays the same — only its directory location changes (from `webui/` to `api/webui/`). This keeps the import surface stable while achieving the directory split. Tests move from `tests/` to `api/tests/` because they all test the API.

**Tech Stack:** No new tech. Same Python, FastAPI, pytest setup as Phase 1.

**Out of scope (deferred to Phase 2b):** React frontend, Bun toolchain, OpenAPI codegen, deletion of `templates/index.html`, deletion of the transitional `pages` router.

---

## File Structure

**Before (flat layout, post-Phase-1):**

```
tg-viewer/
├── tg-viewer
├── tg-backup.sh
├── tg_appstore_decrypt.py
├── postbox_parser.py
├── redact.py
├── tg_decrypt.py            # legacy
├── extract-keys.sh          # legacy
├── main.py
├── webui/                   # FastAPI package
│   └── ...
├── templates/
│   └── index.html
├── tests/
│   ├── conftest.py
│   ├── fixtures/mini-parsed/
│   └── test_*.py
├── requirements.txt
├── README.md
├── CLAUDE.md
├── LICENSE
└── docs/
```

**After (three-subsystem monorepo):**

```
tg-viewer/
├── tg-viewer                # orchestrator (root) — paths updated
├── main.py                  # python orchestrator (root) — imports updated
├── extract/
│   ├── __init__.py          # NEW
│   ├── tg-backup.sh         # MOVED
│   ├── tg_appstore_decrypt.py  # MOVED, intra-imports relative
│   ├── postbox_parser.py    # MOVED, intra-imports relative
│   ├── redact.py            # MOVED
│   ├── tg_decrypt.py        # MOVED (legacy, untouched otherwise)
│   └── extract-keys.sh      # MOVED (legacy)
├── api/
│   ├── webui/               # MOVED from repo root; package name unchanged
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── app.py
│   │   ├── state.py
│   │   ├── models.py
│   │   ├── loader.py
│   │   ├── mime.py
│   │   ├── peer.py
│   │   ├── chats_logic.py
│   │   └── routers/
│   │       └── ...
│   ├── templates/           # MOVED from repo root
│   │   └── index.html
│   └── tests/               # MOVED from repo root
│       ├── __init__.py
│       ├── conftest.py      # path math updated (parent.parent.parent)
│       ├── fixtures/mini-parsed/
│       └── test_*.py
├── web/                     # NEW empty placeholder for Phase 2b
│   └── README.md            # NEW: explains Phase 2b lands here
├── pyproject.toml           # NEW: pytest config (testpaths)
├── requirements.txt         # unchanged
├── README.md                # paths updated
├── CLAUDE.md                # paths updated
├── LICENSE                  # unchanged
└── docs/                    # unchanged
```

---

## Conventions

- **All path moves use `git mv`** so git tracks them as renames (preserves blame/history).
- **Intra-package imports become relative** inside `extract/` (e.g. `import redact` → `from . import redact`).
- **Pytest discovery** is configured via a new root `pyproject.toml` with `[tool.pytest.ini_options] testpaths = ["api/tests"]`.
- **Tests stay green throughout.** Each task ends with `python3 -m pytest` returning 33 passed.
- **One commit per task.** No squashing.
- **No behavior changes.** If a test starts failing in a way that requires changing assertions, STOP and report — that means the move is wrong.

---

## Task 1: Create `extract/` package and move extraction modules

**Files:**
- Create: `extract/__init__.py`
- Move (`git mv`): `tg-backup.sh` → `extract/tg-backup.sh`
- Move: `tg_appstore_decrypt.py` → `extract/tg_appstore_decrypt.py`
- Move: `postbox_parser.py` → `extract/postbox_parser.py`
- Move: `redact.py` → `extract/redact.py`
- Move: `tg_decrypt.py` → `extract/tg_decrypt.py`
- Move: `extract-keys.sh` → `extract/extract-keys.sh`

- [ ] **Step 1: Create the package marker**

```bash
mkdir extract
```

Write `extract/__init__.py`:

```python
"""Telegram backup, decrypt, and parse pipeline."""
```

- [ ] **Step 2: Move the bash scripts**

```bash
git mv tg-backup.sh extract/tg-backup.sh
git mv extract-keys.sh extract/extract-keys.sh
```

- [ ] **Step 3: Move the Python modules**

```bash
git mv tg_appstore_decrypt.py extract/tg_appstore_decrypt.py
git mv postbox_parser.py extract/postbox_parser.py
git mv redact.py extract/redact.py
git mv tg_decrypt.py extract/tg_decrypt.py
```

- [ ] **Step 4: Update intra-package imports inside `extract/`**

These three Python files import each other via flat-path imports that no longer work:

`extract/tg_appstore_decrypt.py:26`:
```python
import redact
```
→
```python
from . import redact
```

`extract/postbox_parser.py:26`:
```python
import redact
```
→
```python
from . import redact
```

`extract/postbox_parser.py:886` (a lazy import inside a function body):
```python
        from tg_appstore_decrypt import decrypt_tempkey
```
→
```python
        from .tg_appstore_decrypt import decrypt_tempkey
```

(The line number may have shifted; locate the lazy import via `grep -n "from tg_appstore_decrypt" extract/postbox_parser.py`.)

- [ ] **Step 5: Verify syntactic validity**

```bash
python3 -c "from extract import redact; from extract import tg_appstore_decrypt; from extract import postbox_parser; print('extract package imports OK')"
```

Expected: prints `extract package imports OK`.

If you get `ImportError: attempted relative import with no known parent package`, double-check that `extract/__init__.py` exists.

- [ ] **Step 6: Commit**

```bash
git add extract/
git commit -m "refactor: move extraction pipeline into extract/ package"
```

---

## Task 2: Update `main.py` imports

`main.py` currently imports the extraction modules from the repo root. Re-point those imports to `extract/`.

**Files:**
- Modify: `main.py:88` and `main.py:149`

- [ ] **Step 1: Find and update the imports**

Run `grep -n "from tg_appstore\|from postbox_parser" main.py` to confirm the line numbers (Phase 1 has them at 88 and 149 respectively).

`main.py:88`:
```python
    from tg_appstore_decrypt import decrypt_tempkey
```
→
```python
    from extract.tg_appstore_decrypt import decrypt_tempkey
```

`main.py:149`:
```python
    from postbox_parser import (
        parse_peer_from_t2,
        parse_messages_from_t7,
        parse_messages_from_fts,
        export_account,
    )
```
→
```python
    from extract.postbox_parser import (
        parse_peer_from_t2,
        parse_messages_from_t7,
        parse_messages_from_fts,
        export_account,
    )
```

- [ ] **Step 2: Smoke-check the import**

```bash
python3 -c "import main; print('main module imports OK')"
```

Expected: prints `main module imports OK` (importing `main` doesn't run `main()`, so no Telegram interaction occurs).

If this fails, the imports are still broken. Inspect the traceback.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "refactor: update main.py imports for extract/ package"
```

---

## Task 3: Update `tg-viewer` script paths to point at `extract/`

`tg-viewer` has five script-path constants near the top of the file. Four of them refer to extraction scripts, which now live under `extract/`.

**Files:**
- Modify: `tg-viewer:9-13`

- [ ] **Step 1: Update the path constants**

Change lines 9–12 of `tg-viewer`:

```bash
BACKUP_SCRIPT="$SCRIPT_DIR/tg-backup.sh"
EXTRACT_SCRIPT="$SCRIPT_DIR/extract-keys.sh"
APPSTORE_DECRYPT_SCRIPT="$SCRIPT_DIR/tg_appstore_decrypt.py"
POSTBOX_PARSER_SCRIPT="$SCRIPT_DIR/postbox_parser.py"
```

to:

```bash
BACKUP_SCRIPT="$SCRIPT_DIR/extract/tg-backup.sh"
EXTRACT_SCRIPT="$SCRIPT_DIR/extract/extract-keys.sh"
APPSTORE_DECRYPT_SCRIPT="$SCRIPT_DIR/extract/tg_appstore_decrypt.py"
POSTBOX_PARSER_SCRIPT="$SCRIPT_DIR/extract/postbox_parser.py"
```

(Leave line 13 — `WEBUI_SCRIPT_DIR` — alone for now. Task 5 updates it to `$SCRIPT_DIR/api/webui`.)

`run_postbox_parser` invokes the parser with `python3 "$POSTBOX_PARSER_SCRIPT" ...` (line ~191). The parser is now `extract/postbox_parser.py`, which has been converted to use relative imports inside `extract/`. Running it with `python3 extract/postbox_parser.py` will FAIL because Python can't process relative imports in a top-level script. Update the invocation:

`tg-viewer:191`:
```bash
    python3 "$POSTBOX_PARSER_SCRIPT" "$backup_dir" "${redact_arg[@]+"${redact_arg[@]}"}"
```
→
```bash
    (cd "$SCRIPT_DIR" && python3 -m extract.postbox_parser "$backup_dir" "${redact_arg[@]+"${redact_arg[@]}"}")
```

If `postbox_parser.py` had a `if __name__ == "__main__":` block at the bottom, `python3 -m extract.postbox_parser` will execute it. If it did NOT, the new invocation will silently no-op. Verify with `grep -n '__name__' extract/postbox_parser.py` — if there's no `if __name__ == "__main__":` block, you'll need to add one (or run `extract/postbox_parser.py` differently). The Phase 1 codebase had this script as a CLI; the bottom-of-file block should still be there.

If `tg_appstore_decrypt.py` and `extract-keys.sh` are also invoked by tg-viewer, apply the same `python3 -m extract.X` pattern for the Python ones; bash scripts can be invoked by absolute path unchanged.

- [ ] **Step 2: Verify the path constants are right**

```bash
grep -E '_SCRIPT(_DIR)?=' tg-viewer
```

Expected: 5 lines, four pointing into `extract/`, one (`WEBUI_SCRIPT_DIR`) still at `$SCRIPT_DIR/webui` (will change in Task 5).

- [ ] **Step 3: Smoke-test the parser invocation**

If a `tg_*` backup directory exists, run `./tg-viewer parse <DIR>` against it. If no real backup is available, just verify that the script doesn't error before reaching the parser:

```bash
./tg-viewer parse /tmp/this-does-not-exist 2>&1 | head -5
```

Expected: error about the missing directory, NOT a "command not found" or "ModuleNotFoundError".

- [ ] **Step 4: Commit**

```bash
git add tg-viewer
git commit -m "refactor: update tg-viewer paths for extract/ package"
```

---

## Task 4: Move `webui/` → `api/webui/` and `templates/` → `api/templates/`

**Files:**
- `mkdir api`
- Move (`git mv`): `webui/` → `api/webui/`
- Move: `templates/` → `api/templates/`

The Python package name (`webui`) is unchanged — only the location changes. The `templates/` move requires no code changes because `api/webui/routers/pages.py:14` resolves the templates path as `parent.parent.parent / "templates"`, which after the move resolves to `api/templates/` (still works correctly).

- [ ] **Step 1: Create `api/`**

```bash
mkdir api
```

- [ ] **Step 2: Move the package and templates**

```bash
git mv webui api/webui
git mv templates api/templates
```

- [ ] **Step 3: Verify the templates path resolution**

```bash
python3 -c "
from pathlib import Path
# Simulate what api/webui/routers/pages.py does
p = Path('api/webui/routers/pages.py').resolve().parent.parent.parent / 'templates'
print('Resolved templates dir:', p)
print('Exists:', p.is_dir())
print('index.html exists:', (p / 'index.html').is_file())
"
```

Expected: `Exists: True` and `index.html exists: True`.

- [ ] **Step 4: Commit**

```bash
git add api/
git commit -m "refactor: move FastAPI package and templates into api/"
```

---

## Task 5: Move `tests/` → `api/tests/` and update conftest

**Files:**
- Move: `tests/` → `api/tests/`
- Modify: `api/tests/conftest.py` (path math)

The conftest.py currently does:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
```

After the move, conftest.py is at `api/tests/conftest.py`, so `parent.parent` resolves to `api/`. We need it to resolve to the **repo root** (parent of `api/`) so `from webui.X import Y` works (the package `webui` is now at `api/webui/`, so the parent of `webui` — i.e., `api/` — must be on `sys.path`).

Wait — that means `parent.parent` (which equals `api/`) is exactly what we want on `sys.path`. Let me re-read.

The `webui` package lives at `api/webui/`. For `from webui.X import Y` to work, sys.path must contain `api/` (so that `webui` is at the top of a path entry). conftest.py's `parent.parent` is `api/`. So `sys.path.insert(0, str(api/))` is correct. **No change to the math is needed** as long as `parent.parent` evaluates to `api/`.

But we also want `import extract` to work in tests (in case any test ever imports from the extraction pipeline — none do today, but it should work). For that, `sys.path` needs to contain the repo root (parent of `api/`). Add a second sys.path insertion.

- [ ] **Step 1: Move the tests**

```bash
git mv tests api/tests
```

- [ ] **Step 2: Update `api/tests/conftest.py` path math and rename variables for clarity**

Current `api/tests/conftest.py`:

```python
"""Pytest fixtures shared across tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "mini-parsed"

# Ensure the repo root is on sys.path so `import webui` and `import webui as old`
# both resolve regardless of pytest's rootdir.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def mini_data_dir() -> Path:
    """Path to the tiny parsed_data fixture used by all parity tests."""
    return FIXTURE_DIR


@pytest.fixture
def fastapi_client(mini_data_dir: Path):
    ...
```

Replace it with:

```python
"""Pytest fixtures shared across tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


# api/tests/conftest.py → parents: api/tests/, api/, <repo root>
API_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = API_DIR.parent
FIXTURE_DIR = API_DIR / "tests" / "fixtures" / "mini-parsed"

# Make `webui` importable from api/, and `extract` importable from repo root.
for path in (str(API_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture
def mini_data_dir() -> Path:
    """Path to the tiny parsed_data fixture used by all parity tests."""
    return FIXTURE_DIR


@pytest.fixture
def fastapi_client(mini_data_dir: Path):
    """FastAPI TestClient with the mini-parsed fixture loaded."""
    from fastapi.testclient import TestClient

    from webui.app import create_app

    app = create_app(str(mini_data_dir))
    with TestClient(app) as client:
        # Same Task 1 follow-up applies here: summary.json's relative backup_dir
        # would point outside the fixture; pin it absolute so /api/media works
        # regardless of pytest's CWD. The lifespan has already run by the time
        # we enter the `with` block.
        client.app.state.app_state.backup_dir = mini_data_dir
        yield client
```

- [ ] **Step 3: Run the tests**

```bash
python3 -m pytest api/tests/ -v
```

Expected: 33 passed.

If you get `ModuleNotFoundError: No module named 'webui'`, the sys.path insert isn't hitting. Print the resolved paths inside conftest as a debug aid.

- [ ] **Step 4: Commit**

```bash
git add api/tests/
git commit -m "refactor: move tests into api/tests and adjust conftest path math"
```

---

## Task 6: Add root `pyproject.toml` so plain `pytest` finds `api/tests/`

**Files:**
- Create: `pyproject.toml`

Without configuration, running `pytest` from the repo root won't find `api/tests/` (pytest's default `testpaths` is the rootdir). Adding a tiny `pyproject.toml` solves this.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["api/tests"]
```

- [ ] **Step 2: Verify plain pytest works**

```bash
python3 -m pytest -v
```

Expected: 33 passed (same as `pytest api/tests`).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pyproject.toml with pytest testpaths"
```

---

## Task 7: Update `tg-viewer` and `main.py` `webui` invocations to use `cd api`

After Task 4, the `webui` package lives at `api/webui/`. For `python -m webui` to work, Python needs `api/` on its module search path. The cleanest way: cd into `api/` before invoking.

**Files:**
- Modify: `tg-viewer:13` and `tg-viewer:217` (or wherever the `python3 -m webui` invocation is)
- Modify: `main.py:185-188` (the subprocess that launches the webui)

- [ ] **Step 1: Update `tg-viewer` `WEBUI_SCRIPT_DIR`**

Line 13:

```bash
WEBUI_SCRIPT_DIR="$SCRIPT_DIR/webui"
```
→
```bash
WEBUI_SCRIPT_DIR="$SCRIPT_DIR/api/webui"
```

- [ ] **Step 2: Update the `python3 -m webui` invocation**

Find the line that invokes `python3 -m webui` (Phase 1 has it at line 217, inside `run_webui()`). It currently looks like:

```bash
    (cd "$SCRIPT_DIR" && python3 -m webui "$abs_data_dir" --host "$host" --port "$port")
```

Change to:

```bash
    (cd "$SCRIPT_DIR/api" && python3 -m webui "$abs_data_dir" --host "$host" --port "$port")
```

(The `cd api` puts `webui` at the top of the search path so `python -m webui` resolves.)

- [ ] **Step 3: Update `main.py`'s subprocess invocation**

`main.py:185-188`:

```python
    subprocess.run(
        [sys.executable, "-m", "webui", str(data_dir), "--port", str(port)],
        cwd=Path(__file__).parent,
    )
```

Change `cwd` to point at `api/`:

```python
    subprocess.run(
        [sys.executable, "-m", "webui", str(data_dir), "--port", str(port)],
        cwd=Path(__file__).parent / "api",
    )
```

- [ ] **Step 4: End-to-end smoke test**

```bash
./tg-viewer webui api/tests/fixtures/mini-parsed &
TG_PID=$!
sleep 2
curl -s -o /dev/null -w "/: %{http_code}\n" http://127.0.0.1:5000/
curl -s -o /dev/null -w "/api/stats: %{http_code}\n" http://127.0.0.1:5000/api/stats
curl -s -o /dev/null -w "/docs: %{http_code}\n" http://127.0.0.1:5000/docs
curl -s -o /dev/null -w "/api/media/test.jpg: %{http_code}\n" http://127.0.0.1:5000/api/media/account-1000000001/test.jpg
kill $TG_PID
wait $TG_PID 2>/dev/null
```

Expected: all four endpoints return `200`. If any returns 500, inspect uvicorn's stdout for the error.

- [ ] **Step 5: Commit**

```bash
git add tg-viewer main.py
git commit -m "refactor: invoke 'python -m webui' with cwd=api/ after restructure"
```

---

## Task 8: Create empty `web/` placeholder

The `web/` directory is the future home of Phase 2b's React+Bun frontend. Create it now (as a no-op) so the three-subsystem layout is visible from the file tree.

**Files:**
- Create: `web/README.md`

- [ ] **Step 1: Write `web/README.md`**

```markdown
# web/

Placeholder for the Phase 2b React + Bun frontend.

When Phase 2b lands, this directory will contain:

- `package.json` — Bun workspace manifest
- `tsconfig.json` — TypeScript compiler config
- `index.html` — Bun.serve() HTML entry
- `src/` — React components, generated OpenAPI types, fetch client
- `dist/` — production build output (served by FastAPI via StaticFiles in prod)

See `docs/superpowers/plans/2026-04-26-phase-2b-react-bun-frontend.md`.
```

- [ ] **Step 2: Commit**

```bash
mkdir -p web
git add web/README.md
git commit -m "chore: add web/ placeholder for Phase 2b frontend"
```

---

## Task 9: Update `README.md` and `CLAUDE.md` for the new layout

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Survey the docs for stale path references**

```bash
grep -n 'webui\|tg-backup\|postbox_parser\|tg_appstore\|extract-keys\|tg_decrypt\|templates/' README.md CLAUDE.md
```

For each match, check whether the path is now under `extract/`, `api/`, or root. Update accordingly. Examples of likely changes:

- "`./webui.py`" or "`webui.py`" → "`python -m webui` (run via `tg-viewer` or `cd api && python -m webui ...`)"
- "`tg-backup.sh`" → "`extract/tg-backup.sh`"
- "`postbox_parser.py`" → "`extract/postbox_parser.py`"
- "`templates/index.html`" → "`api/templates/index.html`"
- The architecture diagram should show the three-subsystem layout

In `CLAUDE.md`, the architecture line was:

```
tg-backup.sh -> tg_appstore_decrypt.py -> postbox_parser.py -> python -m webui
```

Update to:

```
extract/tg-backup.sh -> extract/tg_appstore_decrypt.py -> extract/postbox_parser.py -> python -m webui (in api/)
```

The Key files table should reflect:

| File | Purpose |
|------|---------|
| `tg-viewer` | CLI orchestrator (bash) |
| `extract/tg-backup.sh` | Backup Telegram data from macOS |
| `extract/tg_appstore_decrypt.py` | Decrypt .tempkeyEncrypted + open SQLCipher databases |
| `extract/postbox_parser.py` | Parse Postbox binary format |
| `extract/redact.py` | Console output redaction helpers |
| `api/webui/` | FastAPI backend package — `python -m webui` |
| `api/templates/index.html` | Transitional inline-JS frontend (deleted in Phase 2b) |
| `web/` | Phase 2b React + Bun frontend (placeholder) |

- [ ] **Step 2: Apply the edits**

Use the Edit tool to update `README.md` and `CLAUDE.md` per Step 1's mapping. Do not change feature descriptions or anything other than file paths and the layout description.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: update README and CLAUDE.md for api/ + extract/ layout"
```

---

## Task 10: Final verification

- [ ] **Step 1: Run full test suite from repo root**

```bash
python3 -m pytest -v
```

Expected: 33 passed.

- [ ] **Step 2: End-to-end smoke test**

```bash
./tg-viewer webui api/tests/fixtures/mini-parsed &
TG_PID=$!
sleep 2
curl -s http://127.0.0.1:5000/api/stats | python3 -m json.tool
curl -s -o /dev/null -w "/docs: %{http_code}\n" http://127.0.0.1:5000/docs
kill $TG_PID
wait $TG_PID 2>/dev/null
```

Expected: `/api/stats` returns the same JSON as before the restructure (`total_databases: 1`, `total_messages: 3`); `/docs` returns `200`.

- [ ] **Step 3: Sanity-check no stale paths remain**

```bash
git ls-files | xargs grep -l 'tg-backup.sh\|postbox_parser.py\|tg_appstore_decrypt.py' 2>/dev/null | grep -v '^docs/' | grep -v '^extract/'
```

Expected output: only `tg-viewer`, `main.py`, `README.md`, `CLAUDE.md`, and possibly `extract/tg-backup.sh` itself (which references its own filename in usage text). Anything else means a path reference was missed.

- [ ] **Step 4: Verify git history was preserved on moves**

```bash
git log --follow --oneline api/webui/app.py | head -5
git log --follow --oneline extract/postbox_parser.py | head -5
```

Expected: both show commits from before the move (Phase 1 history).

- [ ] **Step 5: No commit needed for verification**

This is the final task — no new commit. The branch is now ready to merge or hand off to Phase 2b.

---

## Self-Review Checklist

**1. Spec coverage:**

| Spec requirement | Implemented in |
|---|---|
| Three top-level subsystems (api/, extract/, web/) | Tasks 1, 4, 8 |
| `webui` package moved to `api/webui/` | Task 4 |
| `templates/` moved alongside the API | Task 4 |
| Extraction modules in `extract/` | Task 1 |
| Tests live with the API | Task 5 |
| `pyproject.toml` configures pytest | Task 6 |
| `tg-viewer` paths updated | Tasks 3, 7 |
| `main.py` imports + subprocess updated | Tasks 2, 7 |
| Docs updated | Task 9 |
| 33 tests pass throughout | Task 5 + Task 10 |

**2. Placeholder scan:** none — every step has runnable code or commands.

**3. Type consistency:** the `webui` package name is preserved through the move; all import statements stay `from webui.X` and `from extract.X`. No type renames.
