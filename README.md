# Telegram Data Viewer

macOS toolkit for extracting, decrypting, and browsing Telegram messages — including deleted messages and secret chats.

> All processing is local and offline. No network connections, no API calls.

## How it works

```mermaid
flowchart LR
    A["<b>tg-backup.sh</b><br/>Copy app data"] --> B["<b>tg_appstore_decrypt.py</b><br/>Decrypt SQLCipher"]
    B --> C["<b>postbox_parser.py</b><br/>Parse messages"]
    C --> D["<b>webui.py</b><br/>Browse in browser"]

    style A fill:#4a9eff,color:#fff,stroke:none
    style B fill:#ff6b6b,color:#fff,stroke:none
    style C fill:#ffa94d,color:#fff,stroke:none
    style D fill:#51cf66,color:#fff,stroke:none
```

`./tg-viewer full` runs the entire pipeline in one command.

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Full automated workflow (backup + decrypt + parse + web UI)
./tg-viewer full

# 3. Clean up when done
./tg-viewer clean
```

> Quit Telegram before running backup to avoid database locks.

## Step-by-step usage

```bash
./tg-viewer backup ./data           # Copy Telegram data
./tg-viewer decrypt ./data/tg_*/    # Decrypt databases
./tg-viewer parse ./data/tg_*/      # Parse messages into conversations
./tg-viewer webui ./data/tg_*/parsed_data   # Browse in web UI
```

Or call the scripts directly:

```bash
./tg-backup.sh ./data
python3 tg_appstore_decrypt.py ./data/tg_*/
python3 postbox_parser.py ./data/tg_*/
python3 webui.py ./data/tg_*/parsed_data
```

### Extraction results

From a real run on 3 accounts:

| Metric | Result |
|--------|--------|
| Databases decrypted | 3/3 (100%) |
| Messages extracted | 1,105,979 |
| Peers identified | 69,596 |
| Conversations | 374 |
| Secret chats decoded | 24 (13 peer names resolved) |
| Metadata noise | 0% |

## Commands

| Command | Description |
|---------|-------------|
| `./tg-viewer full [DIR]` | Run complete workflow: backup, decrypt, parse, web UI |
| `./tg-viewer backup [DIR]` | Create backup of Telegram data |
| `./tg-viewer decrypt DIR` | Decrypt databases (App Store `.tempkeyEncrypted`) |
| `./tg-viewer parse DIR` | Parse Postbox binary format into messages/peers/conversations |
| `./tg-viewer webui DIR` | Start web UI to browse parsed data |
| `./tg-viewer clean` | Remove all backup, decrypted, and parsed data |
| `./tg-viewer setup` | Install Python dependencies |

## Architecture

### Decryption flow

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
        OUT --> WEB["Flask Web UI<br/><code>http://127.0.0.1:5000</code>"]
    end

    style backup fill:#e8f4fd,stroke:#4a9eff
    style decrypt fill:#fde8e8,stroke:#ff6b6b
    style parse fill:#fef3e2,stroke:#ffa94d
    style view fill:#e8fde8,stroke:#51cf66
```

### Key derivation

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

### Scripts

| File | Purpose |
|------|---------|
| `tg-viewer` | CLI orchestrator — runs the full pipeline or individual steps |
| `tg-backup.sh` | Copies Telegram data from App Store / Desktop / Standalone |
| `tg_appstore_decrypt.py` | Decrypts `.tempkeyEncrypted` and opens SQLCipher databases |
| `postbox_parser.py` | Parses Postbox binary format — extracts messages, peers, conversations from t2/t7/ft41 |
| `webui.py` | Flask web UI for browsing messages |
| `extract-keys.sh` | Extracts encryption keys from macOS Keychain (legacy) |
| `tg_decrypt.py` | Legacy decryptor — tries multiple key formats via sqlcipher3 |

### Postbox database schema

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

## Output format

```
parsed_data/
  summary.json                     # Export metadata
  account-{id}/
    peers.json                     # All peers with names, usernames, phones
    messages.json                  # All messages with timestamps
    conversations_index.json       # Conversation list sorted by message count
    conversations/
      {username_or_name}.json      # Individual conversation with full history
```

<details>
<summary>Example message JSON</summary>

```json
{
  "peer_id": 11049657091,
  "text": "Message content here",
  "timestamp": 1764974409,
  "date": "2025-12-05T22:40:09+00:00",
  "peer_name": "Channel Name",
  "peer_username": "channel_handle"
}
```

</details>

## Supported Telegram versions

| Version | Location | Status |
|---------|----------|--------|
| App Store | `~/Library/Group Containers/6N38VWS5BX.ru.keepcoder.Telegram` | Full support |
| Desktop | `~/Library/Application Support/Telegram Desktop` | Backup only |
| Standalone | `~/Library/Application Support/Telegram` | Backup only |

## Requirements

- macOS with Telegram installed
- Python 3.7+
- Dependencies: `sqlcipher3`, `cryptography`, `flask`, `flask-cors`, `jinja2`

## Troubleshooting

<details>
<summary><b>Decryption fails with "file is not a database"</b></summary>

- Ensure `PRAGMA cipher_default_plaintext_header_size = 32` is set BEFORE the key
- Check that `.tempkeyEncrypted` exists in the backup directory

</details>

<details>
<summary><b>No keys found in keychain</b></summary>

- For App Store version: keys are in `.tempkeyEncrypted`, not keychain. Use `tg_appstore_decrypt.py`
- For Desktop version: check `key_data` file in tdata directory

</details>

<details>
<summary><b>Database locked</b></summary>

- Quit Telegram completely: `killall Telegram`

</details>

<details>
<summary><b>Custom passcode set</b></summary>

- Pass it as an argument: `python3 tg_appstore_decrypt.py ./data --password "your_passcode"`

</details>

## License

Private and proprietary.
