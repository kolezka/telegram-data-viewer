#!/usr/bin/env python3
"""
main.py — Full Telegram extraction pipeline.

Usage:
    python3 main.py                     # auto-detect Telegram, backup + decrypt + parse
    python3 main.py --skip-backup DIR   # use existing backup, just decrypt + parse
    python3 main.py --webui DIR         # start web UI on parsed data
    python3 main.py --password SECRET   # use custom local passcode
"""

import subprocess
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Telegram App Store data location
TG_APPSTORE = Path.home() / "Library/Group Containers/6N38VWS5BX.ru.keepcoder.Telegram"

BANNER = """
  ████████╗ ██████╗       ██████╗  █████╗  ██████╗██╗  ██╗███████╗
  ╚══██╔══╝██╔════╝      ██╔════╝ ██╔══██╗██╔════╝██║  ██║██╔════╝
     ██║   ██║  ███╗     ██║      ███████║██║     ███████║█████╗
     ██║   ██║   ██║     ██║      ██╔══██║██║     ██╔══██║██╔══╝
     ██║   ╚██████╔╝     ╚██████╗ ██║  ██║╚██████╗██║  ██║███████╗
     ╚═╝    ╚═════╝       ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝
"""


def check_dependencies():
    """Verify all required packages are installed."""
    missing = []
    for pkg, import_name in [
        ("sqlcipher3", "sqlcipher3"),
        ("cryptography", "cryptography"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print(f"Install with: pip install {' '.join(missing)}")
        sys.exit(1)


def step_backup(dest: Path) -> Path:
    """Run tg-backup.sh and return the backup directory path."""
    print("\n=== Step 1: Backup Telegram data ===")

    if not TG_APPSTORE.exists():
        print(f"ERROR: Telegram App Store data not found at {TG_APPSTORE}")
        sys.exit(1)

    script = Path(__file__).parent / "tg-backup.sh"
    if not script.exists():
        print(f"ERROR: {script} not found")
        sys.exit(1)

    result = subprocess.run(
        ["bash", str(script), str(dest)],
        capture_output=False,
    )
    if result.returncode != 0:
        print("ERROR: Backup failed")
        sys.exit(1)

    # Find the newest tg_* directory in dest
    backups = sorted(dest.glob("tg_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("ERROR: No backup directory created")
        sys.exit(1)

    backup_dir = backups[0]
    print(f"Backup: {backup_dir}")
    return backup_dir


def step_decrypt(backup_dir: Path, password: str) -> tuple:
    """Decrypt .tempkeyEncrypted and return (db_key, db_salt)."""
    print("\n=== Step 2: Decrypt encryption key ===")

    from tg_appstore_decrypt import decrypt_tempkey

    tempkey_path = None
    for candidate in [
        backup_dir / ".tempkeyEncrypted",
        backup_dir / "appstore" / ".tempkeyEncrypted",
    ]:
        if candidate.exists():
            tempkey_path = candidate
            break

    if not tempkey_path:
        print("ERROR: .tempkeyEncrypted not found in backup")
        print("  This file is required for App Store Telegram decryption.")
        sys.exit(1)

    db_key, db_salt = decrypt_tempkey(str(tempkey_path), password)
    print(f"  Key verified (MurmurHash3 OK)")
    return db_key, db_salt


def step_open_databases(backup_dir: Path, db_key: bytes, db_salt: bytes) -> list:
    """Open all account databases and return list of (account_id, connection)."""
    print("\n=== Step 3: Open databases ===")

    import sqlcipher3

    hex_key = (db_key + db_salt).hex()
    opened = []

    account_dirs = sorted(backup_dir.glob("account-*"))
    if not account_dirs:
        print("  No account-* directories found")
        return opened

    for account_dir in account_dirs:
        db_path = account_dir / "postbox" / "db" / "db_sqlite"
        if not db_path.exists():
            continue

        account_id = account_dir.name.replace("account-", "")
        size_mb = db_path.stat().st_size / 1024 / 1024

        try:
            conn = sqlcipher3.connect(str(db_path))
            conn.execute("PRAGMA cipher_default_plaintext_header_size = 32")
            conn.execute(f'PRAGMA key = "x\'{hex_key}\'"')
            table_count = conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
            print(f"  account-{account_id}: {size_mb:.0f} MB, {table_count} tables")
            opened.append((account_id, conn))
        except Exception as e:
            print(f"  account-{account_id}: FAILED ({e})")

    print(f"  Opened {len(opened)}/{len(account_dirs)} databases")
    return opened


def step_parse(backup_dir: Path, databases: list, output_dir: Path) -> dict:
    """Parse messages from all databases."""
    print("\n=== Step 4: Parse messages ===")

    from postbox_parser import (
        parse_peer_from_t2,
        parse_messages_from_t7,
        parse_messages_from_fts,
        export_account,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    total_messages = 0

    for account_id, conn in databases:
        print(f"\n  --- Account {account_id} ---")
        result = export_account(conn, account_id, output_dir)
        results[account_id] = result
        total_messages += result.get("total_messages", 0)
        conn.close()

    summary = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "backup_dir": str(backup_dir),
        "accounts": results,
        "total_messages": total_messages,
    }
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def step_webui(data_dir: Path, port: int):
    """Start the FastAPI web UI."""
    print(f"\n=== Web UI ===")
    print(f"  Data: {data_dir}")
    print(f"  URL:  http://127.0.0.1:{port}")
    print(f"  Press Ctrl+C to stop\n")

    subprocess.run(
        [sys.executable, "-m", "webui", str(data_dir), "--port", str(port)],
        cwd=Path(__file__).parent,
    )


def print_summary(summary: dict, output_dir: Path):
    """Print a concise summary of results."""
    total = summary.get("total_messages", 0)
    accounts = summary.get("accounts", {})

    print(f"\n{'='*60}")
    print(f"  EXTRACTION COMPLETE")
    print(f"{'='*60}")

    for acc_id, info in accounts.items():
        peers = info.get("peers", 0)
        msgs = info.get("total_messages", 0)
        convos = info.get("conversations", 0)
        status = "OK" if msgs > 0 else "EMPTY"
        print(f"  account-{acc_id}: {msgs:>10,} msgs, {peers:>6,} peers, {convos:>4} convos  [{status}]")

    print(f"  {'':>48}{'─'*12}")
    print(f"  {'Total:':>48}{total:>10,}")
    print(f"\n  Output: {output_dir}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Telegram data extraction pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python3 main.py                        # full pipeline\n"
               "  python3 main.py --skip-backup ./data   # reuse existing backup\n"
               "  python3 main.py --webui ./data/parsed_data\n",
    )
    parser.add_argument("--skip-backup", metavar="DIR",
                        help="Skip backup, use existing directory")
    parser.add_argument("--webui", metavar="DIR",
                        help="Just start web UI on parsed data directory")
    parser.add_argument("--output", metavar="DIR",
                        help="Output directory for parsed data (default: backup_dir/parsed_data)")
    parser.add_argument("--password", default="no-matter-key",
                        help="Local passcode (default: no passcode)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Web UI port (default: 5000)")
    parser.add_argument("--no-webui", action="store_true",
                        help="Skip starting web UI after extraction")
    parser.add_argument("--dest", metavar="DIR", default=".",
                        help="Backup destination directory (default: current dir)")

    args = parser.parse_args()

    print(BANNER)

    # Web UI only mode
    if args.webui:
        data_dir = Path(args.webui)
        if not data_dir.exists():
            print(f"ERROR: {data_dir} not found")
            sys.exit(1)
        check_dependencies()
        step_webui(data_dir, args.port)
        return

    check_dependencies()

    # Step 1: Backup (or skip)
    if args.skip_backup:
        backup_dir = Path(args.skip_backup)
        if not backup_dir.exists():
            print(f"ERROR: {backup_dir} not found")
            sys.exit(1)
        print(f"Using existing backup: {backup_dir}")
    else:
        backup_dir = step_backup(Path(args.dest))

    # Step 2: Decrypt key
    db_key, db_salt = step_decrypt(backup_dir, args.password)

    # Step 3: Open databases
    databases = step_open_databases(backup_dir, db_key, db_salt)
    if not databases:
        print("ERROR: No databases could be opened")
        sys.exit(1)

    # Step 4: Parse messages
    output_dir = Path(args.output) if args.output else backup_dir / "parsed_data"
    summary = step_parse(backup_dir, databases, output_dir)

    # Summary
    print_summary(summary, output_dir)

    # Step 5: Web UI
    if not args.no_webui:
        step_webui(output_dir, args.port)


if __name__ == "__main__":
    main()
