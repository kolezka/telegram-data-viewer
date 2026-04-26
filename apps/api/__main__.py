"""CLI entry: `python -m api <data_dir> --host --port`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the tg-viewer web UI")
    parser.add_argument("data_dir", help="Directory containing decrypted parsed_data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if not Path(args.data_dir).exists():
        print(f"ERROR: Data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    print("\n🚀 Starting Telegram Data Web UI (FastAPI)")
    print(f"📂 Data directory: {args.data_dir}")
    print(f"🌐 URL: http://{args.host}:{args.port}")
    print(f"📖 OpenAPI docs: http://{args.host}:{args.port}/docs")
    print("\nPress Ctrl+C to stop\n")

    app = create_app(args.data_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
