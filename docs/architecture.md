# Architecture

How `tg-viewer` is laid out internally — subsystems, scripts, decryption flow, key derivation, and the Postbox database schema.

## Subsystems

The codebase is organised into three subsystems:

- `extract/` — backup + decryption + Postbox parsing (Python + bash)
- `api/` — FastAPI backend package and transitional templates
- `web/` — Phase 2b React + Bun frontend (placeholder)

## Scripts

| File | Purpose |
|------|---------|
| `tg-viewer` | CLI orchestrator — runs the full pipeline or individual steps |
| `extract/tg-backup.sh` | Copies Telegram data from App Store / Desktop / Standalone |
| `extract/tg_appstore_decrypt.py` | Decrypts `.tempkeyEncrypted` and opens SQLCipher databases |
| `extract/postbox_parser.py` | Parses Postbox binary format — extracts messages, peers, conversations from t2/t7/ft41 |
| `api/webui/` | FastAPI web UI package for browsing messages (entrypoint: `python -m webui`, run with `cwd=api/`) |
| `web/` | React + Bun frontend — built to `web/dist/` and served by FastAPI's StaticFiles |
| `extract/extract-keys.sh` | Extracts encryption keys from macOS Keychain (legacy) |
| `extract/tg_decrypt.py` | Legacy decryptor — tries multiple key formats via sqlcipher3 |

## Decryption flow

```mermaid
flowchart TD
    subgraph backup ["1. Backup"]
        TG["Telegram App Data<br/><code>~/Library/Group Containers/…</code>"]
        TG -->|rsync| BK["Backup directory<br/><code>tg_2025-01-01_12-00-00/</code>"]
    end

    subgraph decrypt ["2. Decrypt"]
        BK --> TK[".tempkeyEncrypted<br/><i>64 bytes, AES-256-CBC</i>"]
        TK -->|"SHA-512(password)"| DK["dbKey (32 B) + dbSalt (16 B)"]
        DK -->|"MurmurHash3 verify"| DB["SQLCipher database<br/><code>PRAGMA cipher_default_plaintext_header_size = 32</code>"]
    end

    subgraph parse ["3. Parse"]
        DB --> T2["<b>t2</b> — Peers<br/><i>users, channels, groups</i>"]
        DB --> T7["<b>t7</b> — Messages<br/><i>binary serialized</i>"]
        DB --> FT["<b>ft41</b> — Full-text index"]
        T2 & T7 & FT --> OUT["parsed_data/<br/>messages + peers + conversations"]
    end

    subgraph view ["4. View"]
        OUT --> WEB["FastAPI Web UI<br/><code>http://127.0.0.1:5000</code>"]
    end

    style backup fill:#e8f4fd,stroke:#4a9eff
    style decrypt fill:#fde8e8,stroke:#ff6b6b
    style parse fill:#fef3e2,stroke:#ffa94d
    style view fill:#e8fde8,stroke:#51cf66
```

## Key derivation

```mermaid
flowchart LR
    PW["Password<br/><code>'no-matter-key'</code>"] -->|SHA-512| H["64-byte digest"]
    H --> K["Bytes 0–31 → AES key"]
    H --> IV["Bytes 48–63 → IV"]
    K & IV -->|"AES-256-CBC"| DE["Decrypt .tempkeyEncrypted"]
    DE --> DBK["dbKey<br/><i>32 bytes</i>"]
    DE --> DBS["dbSalt<br/><i>16 bytes</i>"]
    DE --> MH["MurmurHash3<br/><i>4 bytes, verify</i>"]
    DBK & DBS -->|"hex(key+salt)"| SC["SQLCipher<br/>raw key mode"]

    style PW fill:#f3e8ff,stroke:#9775fa
    style SC fill:#e8fde8,stroke:#51cf66
```

## Postbox database schema

Telegram stores data in numbered tables with binary-serialized values:

```mermaid
erDiagram
    t2 ||--o{ t7 : "peer_id"
    t7 ||--o{ ft41_content : "message_id"
    t7 ||--o{ t12 : "message_tags"
    t7 ||--o{ t62 : "global_index"

    t2 {
        int key "PeerId"
        blob value "first_name, last_name, username, title"
    }
    t7 {
        blob key "peer_id(8) + pad(4) + timestamp(4) + namespace(4)"
        blob value "serialized message"
    }
    ft41_content {
        int docid "message reference"
        text content "searchable text"
    }
    t12 {
        blob key "message tag key"
        blob value "tag data"
    }
    t62 {
        blob key "global message index"
        blob value "index data"
    }
```

Peer data uses tagged binary fields: `02` + tag(2b) + `04` + length(uint32 LE) + UTF-8 string.
Channel titles use: `01` + `t` + `04` + length(uint32 LE) + string.
Secret chat remote peer is in field `r`: `01` + `72` + `01` + user_id(LE int32/int64).
