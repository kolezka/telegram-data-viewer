# Encrypted Telegram Database Cheat Sheet (macOS App Store)

Quick reference for working with Telegram macOS App Store data: decryption, Postbox binary format, peer/message layout, and known gotchas. All references point to files in this repo.

---

## 0. Terminology

| Term | Definition |
|------|------------|
| **MTProto** | Telegram's wire protocol — defines transport-layer encryption, RPC framing, and the secret-chat E2EE handshake. Not used by this toolkit (we read on-disk artifacts), but secret-chat keys originated from it. |
| **Postbox** | Telegram's local storage layer (a custom key-value engine on top of SQLite + binary blobs). The "Postbox format" is the binary serialization Postbox writes inside `t2`, `t7`, etc. — proprietary, no public spec. |
| **SQLCipher** | A drop-in SQLite fork that encrypts pages with AES-256. Telegram uses raw-key mode (no PBKDF2). |
| **DC / dc_id** | **Data Center ID.** Telegram operates ~5 numbered datacenters (`1`–`5` in production, code defensively allows `1`–`10`). Every cloud-stored file is pinned to the DC that holds it; `dc_id` is part of the file URL and is stored next to `file_id` in message blobs so the client knows where to fetch from. |
| **peer_id** | **Composite int64 identifier** for any conversation endpoint (user, group, channel, secret-chat session, bot). Encoded as `(type_hi << 32) \| id_lo` — see §5. The same human user can appear under different `peer_id`s (e.g. user vs. secret chat with that user). |
| **file_id** | **Postbox-internal numeric ID** for a media file, unique within a DC. Reused by Telegram to deduplicate uploads. Sanity-checked as `> 1_000_000_000` to avoid false-positive matches in binary scans. Distinct from the API-level `file_reference` (not stored locally). |
| **access_hash** | API-level int64 token Telegram requires to fetch a peer/file from the network. Largely irrelevant for offline forensics — backups already contain the bytes. |
| **namespace** | Postbox concept for partitioning messages within a peer (e.g. cloud messages vs. scheduled vs. secret). Stored in t7 key bytes 16–19. Most regular messages use namespace `0`. |
| **tempkey** | The contents of `.tempkeyEncrypted` — the AES-CBC-encrypted blob holding `dbKey + dbSalt + verification hash`. "Decrypting the tempkey" yields the SQLCipher raw key. |
| **dbKey / dbSalt** | The 32-byte AES key and 16-byte salt that together (concatenated) form the 48-byte SQLCipher raw key. |
| **t2 / t7 / t12 / t62** | Postbox tables — see §3 for the inventory. Naming is internal; numbers are stable across versions. |
| **ft41** | The FTS5 (full-text search) virtual table backing message search. `ft41_content` is the content table — often the **only** place "deleted" message text survives because FTS rows aren't always pruned with the source row. |
| **secret chat** | Telegram's E2EE 1:1 chat. Identified by `peer_id` hi32 = `0x03`. Direction lives in the t7 key, not the value. Media is symlinked into the live app's directory and uses a different filename scheme (`secret-file-*`). |
| **service message** | Auto-generated message (joins, leaves, title/photo changes, pinned-message events). Currently **not** parsed by this toolkit — the binary tags are unknown. |
| **Saved Messages** | Telegram's per-user "notes to self" chat. Conventionally `peer_id == own_user_id`. Not specially handled; appears as a regular user-type peer pointing at the account owner. |
| **Group Container** | macOS sandbox-shared directory under `~/Library/Group Containers/`. Telegram App Store uses `6N38VWS5BX.ru.keepcoder.Telegram` (Team ID + bundle ID) so its main app and extensions can share data. |
| **`.tempkeyEncrypted`** | The on-disk file holding the encrypted tempkey. Lives at the root of `appstore/`. |

---

## 1. File paths

```
~/Library/Group Containers/6N38VWS5BX.ru.keepcoder.Telegram/
└── appstore/
    ├── .tempkeyEncrypted         # AES-CBC encrypted db key (~52 bytes)
    ├── accounts-shared-data      # JSON: account_id ↔ peerName
    ├── accounts-metadata/        # login tokens, guard DB
    └── account-{id}/
        ├── postbox/
        │   ├── db/db_sqlite      # encrypted SQLCipher DB
        │   └── media/            # cached media files
        ├── cached/               # peer-specific cached blobs
        ├── network-stats
        └── notificationsKey
```

Legacy variants (backup-only support):
- `~/Library/Application Support/Telegram Desktop/`
- `~/Library/Application Support/Telegram/`

Refs: `apps/tool/tg-backup.sh:51`, `apps/tool/extract-keys.sh:97`.

### `accounts-shared-data` JSON shape

```json
{ "accounts": [ { "id": <int64>, "peerName": "<str>" }, ... ] }
```

Folder name is derived as `account-{id % 2^64}` — i.e. raw user_id cast to unsigned 64-bit, **not** a hash. This is the only reliable account_id ↔ peerName map you get before decryption.

Ref: `apps/tool/tg-backup.sh:140-152`.

---

## 2. Cryptography

### `.tempkeyEncrypted` → raw db key

| Step | Value |
|------|-------|
| Cipher | AES-256-CBC |
| Password (default) | `"no-matter-key"` (when no local passcode set) |
| Key derivation | `SHA-512(password)` → first 32 bytes = AES key, last 16 bytes = IV |
| Plaintext layout | `dbKey(32) ‖ dbSalt(16) ‖ hash(4) ‖ padding` |

Refs: `apps/tool/tg_appstore_decrypt.py:85-86`.

### Key verification (MurmurHash3 x86 32-bit)

| Constant | Value |
|----------|-------|
| Seed | `0xF7CA7FD2` |
| c1 | `0xCC9E2D51` |
| c2 | `0x1B873593` |
| fmix1 | `0x85EBCA6B` |
| fmix2 | `0xC2B2AE35` |
| body increment | `h1 * 5 + 0xE6546B64` |

Input: `dbKey ‖ dbSalt` (48 bytes). Compare 32-bit output to the trailing 4 bytes of the decrypted tempkey.

Ref: `apps/tool/tg_appstore_decrypt.py:33-78,109`.

### Opening SQLCipher

Order matters — set the header pragma **before** the key.

```sql
PRAGMA cipher_plaintext_header_size = 32;
PRAGMA cipher_memory_security = OFF;
PRAGMA key = "x'<96-hex-chars>'";   -- hex(dbKey ‖ dbSalt), 48 bytes → 96 hex
```

No PBKDF2 — raw key mode. Refs: `apps/tool/tg_appstore_decrypt.py:137-140`, `apps/tool/postbox_parser.py:849-850`.

---

## 3. Database tables

| Table | Key | Value | Purpose |
|-------|-----|-------|---------|
| `t2` | int64 peer_id | binary peer record | Users, channels, groups |
| `t3` | — | — | Peer presence/status |
| `t4` | peer + msg_id | small metadata | Message index |
| `t6` | — | file refs + dc_id | Media references |
| `t7` | **20-byte composite** | binary message + text + media refs | **Full messages** |
| `t12` | — | — | Message tags / labels |
| `t62` | — | — | Global message index |
| `ft41_content` | rowid | c0=peer_ref, c1=msg_ref, c2=text, c3=extra | FTS5 full-text index (also surfaces deleted rows) |

Ref: `apps/tool/postbox_parser.py:1-15`.

A live Postbox DB contains additional `t*` tables (`t1`, `t5`, `t8`, `t9`, …) that this toolkit doesn't parse yet — `tg_appstore_decrypt.py` enumerates them via `sqlite_master` for inspection (`apps/tool/tg_appstore_decrypt.py:236-254`) but only `t2` and `t7` are decoded end-to-end. To map a new one, dump its schema with `PRAGMA table_info('tN')` and hex-dump a few values.

---

## 4. Postbox binary format

### Tag template

```
<tag bytes> 04 <uint32 LE length> <utf-8 string>
```

- `01 XX` — single-byte tag (XX is ASCII for the field letter)
- `02 XX YY` — two-byte tag
- `04` — string length-prefix marker
- Lengths are uint32 LE; reject if > ~500 bytes (heuristic).

### Peer field tags (`t2` value)

| Bytes | ASCII | Field |
|-------|-------|-------|
| `02 66 6E 04` | `fn` | first_name |
| `02 6C 6E 04` | `ln` | last_name |
| `02 75 6E 04` | `un` | username |
| `01 70 04` | `p` | phone (validated 6–15 digits) |
| `01 74 04` | `t` | title (channel/group) |
| `01 72 01` | `r` | secret-chat remote peer (8b LE int follows) |

Ref: `apps/tool/postbox_parser.py:29-97`.

### Message key (`t7`, 20 bytes, big-endian unless noted)

```
[ 0..7 ]  peer_id        int64 BE (composite, see §5)
[ 8..11 ] secret tag/ns  uint32 BE   (1 = outgoing, 2 = incoming for secret chats)
[12..15 ] timestamp      uint32 BE   (Unix seconds; sanity: 1e9 < ts < 2e9)
[16..19 ] namespace      uint32 BE
```

Ref: `apps/tool/postbox_parser.py:521-539`.

---

## 5. Peer ID encoding

`peer_id` is a composite int64 (read big-endian from the t7 key, native int from t2):

| Hi 32 bits | Type |
|-----------:|------|
| `0x00000000` | User |
| `0x00000001` | Group |
| `0x00000002` | Channel |
| `0x00000003` | Secret chat |
| `0x00000008` | Bot |

Lo 32 bits = the actual user / chat / channel ID.

Ref: `apps/api/peer.py:5-18`.

---

## 6. Direction detection

```python
if peer_hi == 0x02:                              # Channels — always incoming
    is_outgoing = False
elif peer_hi == 0x03:                            # Secret chats — read from KEY
    is_outgoing = struct.unpack('>I', key[8:12])[0] == 1
else:                                            # User / group / bot — read from VALUE
    is_outgoing = not bool(value[10] & 0x04)     # 0x04 = Incoming bit
```

Refs: `apps/tool/postbox_parser.py:584-606`.

**Gotcha:** for secret chats, byte 10 of the value is part of a random message ID, **not** a flags byte. Direction comes from the key only.

---

## 7. Media

### Filename schemes

| Pattern | Source |
|---------|--------|
| `telegram-cloud-photo-size-{dc_id}-{file_id}-{suffix}` | Cloud photos. Suffix = `y` (largest), `x`, `w`, `m`, `c`, `s` |
| `telegram-cloud-document-{dc_id}-{file_id}` | Cloud documents |
| `secret-file-{file_id}-{dc_id}[.ext]` | Secret chat media (note flipped order). ext ∈ `.jpg .mp4 .mp3 .webm .ogg .png` or none |

Ref: `apps/tool/postbox_parser.py:378-406`.

### Media references inside `t7` values

**Form 1** (regular):
```
01 69 01 <file_id LE int64>
…elsewhere…
01 64 00 <dc_id LE int32>
```

**Form 2** (bytes blob — secret chats):
```
01 69 0a 0c <dc_id BE int32> <4 bytes 00> <file_id LE int64>
```

Marker breakdown: `01 69` = field `i`, `0a` = BYTES type, `0c` = 12-byte payload length.

**Don't miss Form 2** — older parsers skipped it and silently produced zero secret-chat media hits. Sanity check: `file_id > 1_000_000_000` to avoid false positives.

Ref: `apps/tool/postbox_parser.py:273-372`.

### Adjacent media sub-tags

| Bytes | ASCII | Field | Format | Sanity |
|-------|-------|-------|--------|--------|
| `01 64 00` | `d` | dc_id | LE uint32 | 1 ≤ x ≤ 10 |
| `02 64 78 00` | `dx` | width | LE uint32 | x ≤ 10000 |
| `02 64 79 00` | `dy` | height | LE uint32 | x ≤ 10000 |

The width/height markers live within ±80 bytes of the file_id marker — scan a window, don't assume fixed offset.

Ref: `apps/tool/postbox_parser.py:308-335`.

### MIME sniffing

Recognises gzip-wrapped Lottie/SVG/ICNS, RIFF/WebP, MP4 `ftyp`, PDF, OGG, MP3. Returns one of: `image/jpeg`, `image/png`, `image/webp`, `audio/mpeg`, `audio/ogg`, `video/webm`, `application/x-tgsticker`, `application/gzip`, …

Ref: `apps/tool/postbox_parser.py:134-208`.

---

## 8. Timestamps

- Format: Unix seconds since 1970-01-01 UTC.
- Validation range: `1_000_000_000 < ts < 2_000_000_000` (Sept 2001 – May 2033) — anything outside is parser noise.
- JS convention: multiply by 1000 for `new Date(ts * 1000)`.

Refs: `apps/tool/postbox_parser.py:534-536`, `apps/web/src/lib/format.ts:10`.

---

## 9. Text extraction filters

When pulling text out of message values, drop strings that look like embedded metadata. Common substrings to skip:

```
_rawValue, fileId, discriminator,
patternColor, textColor, innerColor, outerColor, patternFileId
```

Heuristics: reject if length > 100 KB or printable-ratio < 50 %.

Ref: `apps/tool/postbox_parser.py:100-131,243-270`.

---

## 10. Backup hygiene (rsync)

Telegram writes continuously, so partial-source errors are normal:

| Exit code | Meaning | Action |
|----------:|---------|--------|
| 23 | Partial transfer | Ignore |
| 24 | Source vanished mid-copy | Ignore |

Always exclude: `*_partial.*`, `*.lock`, `*-journal`, `*-shm`, `*-wal`.

Ref: `apps/tool/tg-backup.sh:29-45`.

---

## 11. Keychain service patterns (legacy extractor)

```
Telegram
ru.keepcoder.Telegram
6N38VWS5BX.ru.keepcoder.Telegram
postbox
local_storage
temp_key
tempKeyEncrypted
masterKey
```

Used by `apps/tool/extract-keys.sh:27-36`. Not needed when `.tempkeyEncrypted` + default password is present.

---

## 12. Forensic gotchas (collected)

- **Secret-chat filename order is reversed** vs. cloud media (`{file_id}-{dc_id}` instead of `{dc_id}-{file_id}`).
- **Symlinks in `media/`** point into the live Telegram install. The webui's `serve_media` had to drop a `Path.resolve().relative_to(backup_dir)` check because resolved paths leave the backup root — filename-level validation is enough.
- **Channels are always "incoming"** — architectural, not a data quirk. Don't try to detect outgoing channel posts.
- **`ft41_content` is the only place "deleted" rows survive** — the live message row may already be gone from `t7`.
- **`accounts-shared-data` is the only place to map account_id → human peerName** before parsing per-account postboxes.
- **Secret-chat remote peer** (`01 72 01`) sometimes uses LE int32 vs. LE int64 — try both.
- **Reply / forward / reaction tags are not yet mapped.** Deep-grep on the parser turns up no markers for `reply_to_msg_id`, fwd headers, reactions, edits, view counts, or message entities — they're either stored as opaque chunks inside the value or simply not extracted. Hex-dump messages with known replies/reactions to find them.

---

## 13. Parser output (per-account)

After `./tg-viewer parse` runs, each `account-{id}/parsed_data/` contains:

| File | Contents |
|------|----------|
| `messages.json` | All extracted messages from `t7` |
| `peers.json` | Peer records from `t2` |
| `conversations_index.json` | `[{peer_id, all_peer_ids, peer_name, peer_username, message_count, messages: [...]}]` |
| `messages_fts.json` | Rows from `ft41_content` (often the only place deleted messages survive) |
| `media_catalog.json` | File inventory with `linked_message: {peer_id, peer_name, timestamp, date, width?, height?, thumbnail?}` (null when uncorrelated) |
| `summary.json` | `{ "backup_dir": <str>, ... }` plus per-account counts |

Refs: `apps/api/loader.py:15-72`, `docs/output-format.md`.

---

## 14. Quick command reference

```bash
# Full pipeline (backup + decrypt + parse + webui)
./tg-viewer full

# Individual stages
./tg-viewer backup  ./data
./tg-viewer decrypt ./data/tg_*/
./tg-viewer parse   ./data/tg_*/
./tg-viewer webui   ./data/tg_*/parsed_data
```

Useful flags:
- `--redact` — masks account IDs and paths in CLI output (handy for screenshots)
- `--host` / `--port` — webui binding (default `127.0.0.1:5000`)
- `apps/tool/tg-backup.sh --batch` — non-interactive mode for scripted runs

API: FastAPI mounted at `/api/*`, React bundle from `apps/web/dist/`, OpenAPI schema at `/openapi.json`. See [`docs/api.md`](api.md).
