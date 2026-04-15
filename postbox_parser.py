#!/usr/bin/env python3
"""
postbox_parser.py — Parse Telegram Postbox database format
Extracts messages, peer info, and metadata from decrypted SQLCipher databases.

Tables in Telegram Postbox:
  t2  - Peers (users, channels, groups) with serialized info
  t3  - Peer presence/status
  t4  - Message index (key=peer+msgid, value=small metadata)
  t6  - Media references
  t7  - Full message data (key=peer+msgid+ns, value=serialized message)
  t12 - Message tags/labels
  t62 - Message global index
  ft41_content - Full-text search index of messages
"""

import struct
import json
import re
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

import redact


def parse_peer_from_t2(key: int, value: bytes) -> Optional[Dict[str, Any]]:
    """Parse peer info from t2 table.

    Postbox binary format uses tagged fields:
      String fields: 02 + tag(2b) + 04 + length(uint32 LE) + utf-8 string
      Phone field:   01 + 'p' + 04 + length(uint32 LE) + utf-8 string
    """
    peer = {'id': key}

    # Tag -> field name mapping for 02-prefixed string fields
    field_map = {
        b'fn': 'first_name',
        b'ln': 'last_name',
        b'un': 'username',
    }

    pos = 0
    val = value
    while pos < len(val) - 6:
        if val[pos] == 0x02:
            tag = val[pos + 1:pos + 3]
            if tag in field_map and val[pos + 3] == 0x04:
                if pos + 8 <= len(val):
                    strlen = struct.unpack('<I', val[pos + 4:pos + 8])[0]
                    if 0 < strlen < 500 and pos + 8 + strlen <= len(val):
                        try:
                            s = val[pos + 8:pos + 8 + strlen].decode('utf-8').strip()
                            if s:
                                peer[field_map[tag]] = s
                            pos += 8 + strlen
                            continue
                        except (UnicodeDecodeError, ValueError):
                            pass
        # Fields with 01 prefix: 01 + tag(1b) + 04 + length(uint32 LE) + string
        # 01 + 'p' = phone, 01 + 't' = title (channel/group name)
        elif val[pos] == 0x01 and pos + 2 < len(val) and val[pos + 2] == 0x04:
            tag_byte = val[pos + 1]
            if pos + 7 <= len(val):
                strlen = struct.unpack('<I', val[pos + 3:pos + 7])[0]
                if 0 < strlen < 500 and pos + 7 + strlen <= len(val):
                    try:
                        s = val[pos + 7:pos + 7 + strlen].decode('utf-8').strip()
                        if tag_byte == ord('p') and s and re.match(r'^\d{6,15}$', s):
                            peer['phone'] = s
                        elif tag_byte == ord('t') and s:
                            peer['title'] = s
                            if 'first_name' not in peer:
                                peer['first_name'] = s
                        pos += 7 + strlen
                        continue
                    except (UnicodeDecodeError, ValueError):
                        pass
        pos += 1

    # For secret chats (namespace=3): extract remote peer from 'r' field
    # Format: 01 72 01 <user_id as LE int32/int64>
    r_pos = value.find(b'\x01r\x01')
    if r_pos >= 0 and r_pos + 11 <= len(value):
        r_chunk = value[r_pos + 3:r_pos + 11]
        if len(r_chunk) >= 8:
            # Try 4-byte LE first, then 8-byte LE as composite PeerId
            lo4 = struct.unpack('<I', r_chunk[:4])[0]
            le8 = struct.unpack('<q', r_chunk[:8])[0]
            peer['_remote_peer_id_lo4'] = lo4
            peer['_remote_peer_id_le8'] = le8

    if len(peer) > 1:
        return peer
    return None


METADATA_STRINGS = frozenset({
    '_rawValue', 'entities', 'src', 'content', 'discriminator',
    'fileId', 'title', 'slug', 'innerColor', 'outerColor',
    'patternColor', 'textColor', 'patternFileId',
    'uns', 'sth', 'clclr', 'nclr', 'bgem', 'pclr', 'pgem',
    'ssc', 'vfid', 'emjs', 'biri', 'fl',
})

# Metadata field names that indicate serialized Postbox data when found as substrings
_METADATA_SUBSTRINGS = (
    '_rawValue', 'entities', 'channelId', 'fileId', 'discriminator',
    'patternColor', 'textColor', 'innerColor', 'outerColor',
    'patternFileId', 'bubbleUpEmojiOrStickersets', 'cidbubbleUp',
)


def _looks_like_metadata(text: str) -> bool:
    """Return True if text looks like serialized metadata, not a real message."""
    stripped = text.strip()
    if stripped in METADATA_STRINGS:
        return True
    # Filter short strings that are just field tags with padding
    if len(stripped) < 4 and not any(c.isalpha() for c in stripped):
        return True
    # Text containing null bytes is binary data, not a real message
    if '\x00' in stripped:
        return True
    # Check for metadata field names embedded in binary-mixed text
    for substr in _METADATA_SUBSTRINGS:
        if substr in stripped:
            return True
    return False


MIME_SIGNATURES = [
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'GIF87a', 'image/gif'),
    (b'GIF89a', 'image/gif'),
    (b'\x1a\x45\xdf\xa3', 'video/webm'),
    (b'OggS', 'audio/ogg'),
    (b'\xff\xfb', 'audio/mpeg'),
    (b'\xff\xf3', 'audio/mpeg'),
    (b'\xff\xf2', 'audio/mpeg'),
    (b'ID3', 'audio/mpeg'),
    (b'%PDF', 'application/pdf'),
    (b'\x1f\x8b', 'application/gzip'),
]


def detect_mime_type(filepath: Path) -> str:
    """Detect MIME type from file magic bytes."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(12)
    except OSError:
        return 'application/octet-stream'

    for sig, mime in MIME_SIGNATURES:
        if header.startswith(sig):
            return mime

    # RIFF container: check for WEBP at offset 8
    if header[:4] == b'RIFF' and len(header) >= 12 and header[8:12] == b'WEBP':
        return 'image/webp'

    # ftyp container (MP4/M4A/MOV): check subtype at offset 8
    if len(header) >= 12 and header[4:8] == b'ftyp':
        subtype = header[8:12]
        if subtype == b'M4A ':
            return 'audio/mp4'
        return 'video/mp4'

    return 'application/octet-stream'


def classify_media_type(mime: str, filename: str) -> str:
    """Classify a file into a media type category."""
    if '-tgs' in filename or filename.endswith('.tgs'):
        return 'sticker'
    if mime.startswith('image/gif'):
        return 'gif'
    if mime.startswith('image/'):
        return 'photo'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    return 'document'


def extract_text_from_message(value: bytes) -> Optional[str]:
    """Extract message text from t7 serialized value.

    Postbox uses length-prefixed strings in both LE and BE uint32 formats.
    The main message text is typically the longest printable string found
    in the first 100 bytes of the value, excluding known metadata fields.
    """
    best_text = None
    best_len = 0

    for offset in range(4, min(100, len(value) - 4)):
        for endian in ('<I', '>I'):
            try:
                strlen = struct.unpack(endian, value[offset:offset + 4])[0]
            except struct.error:
                continue

            if strlen < 2 or strlen > 100000 or offset + 4 + strlen > len(value):
                continue

            try:
                decoded = value[offset + 4:offset + 4 + strlen].decode('utf-8')
            except (UnicodeDecodeError, ValueError):
                continue

            printable_count = sum(1 for c in decoded if c.isprintable() or c in '\n\r\t')
            if printable_count / max(len(decoded), 1) < 0.5:
                continue

            stripped = decoded.strip()
            if _looks_like_metadata(stripped):
                continue

            if len(stripped) > best_len:
                best_text = stripped
                best_len = len(stripped)

    return best_text


def extract_media_refs(value: bytes) -> List[Dict[str, Any]]:
    """Extract media file references from a t7 message value.

    Scans for Postbox-encoded tagged fields:
      - tag 'i' (Int64): file_id — pattern 01 69 01 <8b LE>
      - tag 'd' (Int32): datacenter_id — pattern 01 64 00 <4b LE>
      - tag 'dx'/'dy' (Int32): dimensions — pattern 02 64 78/79 00 <4b LE>

    Groups nearby (d, i, h, dx, dy) fields into media references.
    Returns list of dicts with keys: file_id, dc_id, width, height.
    """
    refs = []
    # Find all 'i' (file_id) Int64 fields: 01 69 01 <8 bytes LE>
    i_marker = b'\x01\x69\x01'
    pos = 0
    while pos < len(value) - 10:
        idx = value.find(i_marker, pos)
        if idx < 0:
            break
        file_id = struct.unpack('<q', value[idx + 3:idx + 11])[0]
        if file_id == 0:
            pos = idx + 11
            continue

        # Search backwards and forwards (within 80 bytes) for dc_id and dimensions
        window_start = max(0, idx - 80)
        window_end = min(len(value), idx + 80)
        window = value[window_start:window_end]
        rel = idx - window_start

        dc_id = 0
        width = 0
        height = 0

        # Look for 'd' Int32: 01 64 00 <4b LE>
        d_marker = b'\x01\x64\x00'
        d_pos = window.find(d_marker)
        if 0 <= d_pos and d_pos + 7 <= len(window):
            dc_id = struct.unpack('<I', window[d_pos + 3:d_pos + 7])[0]
            if dc_id > 10:
                dc_id = 0  # sanity check — dc_ids are small (1-5)

        # Look for 'dx' Int32: 02 64 78 00 <4b LE>
        dx_marker = b'\x02\x64\x78\x00'
        dx_pos = window.find(dx_marker)
        if 0 <= dx_pos and dx_pos + 8 <= len(window):
            width = struct.unpack('<I', window[dx_pos + 4:dx_pos + 8])[0]
            if width > 10000:
                width = 0

        # Look for 'dy' Int32: 02 64 79 00 <4b LE>
        dy_marker = b'\x02\x64\x79\x00'
        dy_pos = window.find(dy_marker)
        if 0 <= dy_pos and dy_pos + 8 <= len(window):
            height = struct.unpack('<I', window[dy_pos + 4:dy_pos + 8])[0]
            if height > 10000:
                height = 0

        # Skip duplicates (same file_id appears twice per message for thumb + full)
        if not any(r['file_id'] == file_id for r in refs):
            ref = {'file_id': file_id, 'dc_id': dc_id}
            if width:
                ref['width'] = width
            if height:
                ref['height'] = height
            refs.append(ref)

        pos = idx + 11

    return refs


def resolve_media_files(refs: List[Dict], media_index: set) -> List[Dict[str, Any]]:
    """Resolve media refs to actual filenames on disk.

    Tries patterns: telegram-cloud-photo-size-{dc}-{fid}-{suffix},
    telegram-cloud-document-{dc}-{fid}, and local-file variants.
    """
    resolved = []
    photo_suffixes = ['y', 'x', 'w', 'm', 'c', 's', 'a', 'b']

    for ref in refs:
        fid = ref['file_id']
        dc = ref.get('dc_id', 0)
        matched = None

        # Try photo patterns (largest size first)
        if dc:
            for suffix in photo_suffixes:
                candidate = f"telegram-cloud-photo-size-{dc}-{fid}-{suffix}"
                if candidate in media_index:
                    matched = candidate
                    break
            if not matched:
                candidate = f"telegram-cloud-document-{dc}-{fid}"
                if candidate in media_index:
                    matched = candidate

        # Try without dc_id (scan all dc values 1-5)
        if not matched:
            for try_dc in range(1, 6):
                for suffix in photo_suffixes:
                    candidate = f"telegram-cloud-photo-size-{try_dc}-{fid}-{suffix}"
                    if candidate in media_index:
                        matched = candidate
                        break
                if matched:
                    break
                candidate = f"telegram-cloud-document-{try_dc}-{fid}"
                if candidate in media_index:
                    matched = candidate
                    break

        if matched:
            entry = dict(ref)
            entry['filename'] = matched
            resolved.append(entry)

    return resolved


def build_media_index(media_dir: Path) -> set:
    """Build a set of media filenames for fast lookup."""
    if not media_dir.is_dir():
        return set()
    index = set()
    for f in media_dir.iterdir():
        if f.is_file() and not f.name.endswith('_partial.meta') and not f.name.endswith('_partial'):
            index.add(f.name)
    return index


def build_media_catalog(
    media_dir: Path,
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build a full media catalog by scanning the media directory.

    Cross-references files against parsed messages to link media to conversations.
    Returns a list of catalog entries with MIME type, size, dimensions, and linkage.
    """
    if not media_dir.is_dir():
        return []

    # Build filename -> message media info lookup from messages.json
    filename_to_msg: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        for m in msg.get('media', []):
            fname = m.get('filename')
            if fname and fname not in filename_to_msg:
                filename_to_msg[fname] = {
                    'peer_id': msg.get('peer_id'),
                    'peer_name': msg.get('peer_name'),
                    'timestamp': msg.get('timestamp'),
                    'date': msg.get('date'),
                    'width': m.get('width'),
                    'height': m.get('height'),
                }

    catalog = []
    file_count = 0

    for filepath in sorted(media_dir.iterdir()):
        if not filepath.is_file():
            continue
        if filepath.name.endswith('_partial') or filepath.name.endswith('_partial.meta'):
            continue

        file_count += 1
        if file_count % 500 == 0:
            print(f"    Scanning media: {file_count} files...")

        stat = filepath.stat()
        mime = detect_mime_type(filepath)
        media_type = classify_media_type(mime, filepath.name)

        entry = {
            'filename': filepath.name,
            'mime_type': mime,
            'size_bytes': stat.st_size,
            'width': None,
            'height': None,
            'media_type': media_type,
            'thumbnail': None,
            'linked_message': None,
        }

        # For photos, find a smaller Telegram variant for thumbnails
        # Telegram stores photos with suffixes: y(largest), x, w, m, c, s(smallest)
        if media_type == 'photo' and 'telegram-cloud-photo-size-' in filepath.name:
            base = filepath.name.rsplit('-', 1)[0]  # strip the suffix
            for thumb_suffix in ['s', 'm', 'c']:
                thumb_name = base + '-' + thumb_suffix
                if (media_dir / thumb_name).is_file():
                    entry['thumbnail'] = thumb_name
                    break

        # Link to message if available
        msg_info = filename_to_msg.get(filepath.name)
        if msg_info:
            entry['width'] = msg_info.get('width')
            entry['height'] = msg_info.get('height')
            entry['linked_message'] = {
                'peer_id': msg_info['peer_id'],
                'peer_name': msg_info.get('peer_name'),
                'timestamp': msg_info.get('timestamp'),
                'date': msg_info.get('date'),
            }

        catalog.append(entry)

    print(f"    Media catalog: {len(catalog)} files ({file_count} scanned)")
    return catalog


def parse_message_key(key: bytes) -> Dict[str, Any]:
    """Parse t7 message key (20 bytes).

    Format: namespace_hi(4b BE) + peer_id_lo(4b BE) + padding(4b) + timestamp(4b BE) + msg_tag(4b BE)
    - Bytes 0-7: peer_id as big-endian int64
    - Bytes 8-11: zero padding
    - Bytes 12-15: Unix timestamp (big-endian uint32)
    - Bytes 16-19: message namespace/tag
    """
    result = {}
    if len(key) >= 8:
        result['peer_id'] = struct.unpack('>q', key[:8])[0]
    if len(key) >= 16:
        ts = struct.unpack('>I', key[12:16])[0]
        if 1000000000 < ts < 2000000000:
            result['timestamp'] = ts
    if len(key) >= 20:
        result['namespace'] = struct.unpack('>I', key[16:20])[0]
    return result


def parse_messages_from_t7(
    conn, peers: Dict[int, Dict], media_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Parse all messages from t7 table."""
    messages = []
    batch_size = 10000
    offset = 0

    media_index = build_media_index(media_dir) if media_dir else set()
    if media_index:
        print(f"    Media index: {len(media_index)} files")

    while True:
        rows = conn.execute(
            f'SELECT key, value FROM t7 WHERE length(value) > 20 LIMIT {batch_size} OFFSET {offset}'
        ).fetchall()

        if not rows:
            break

        for key, value in rows:
            if len(key) < 16:
                continue

            key_info = parse_message_key(key)
            peer_id = key_info.get('peer_id')
            if not peer_id:
                continue

            text = extract_text_from_message(value)
            media = resolve_media_files(extract_media_refs(value), media_index) if media_index else []

            # For media-only messages, clear garbage text (binary noise)
            if text:
                printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
                if printable / max(len(text), 1) < 0.5:
                    text = None

            # Skip messages with no text and no media
            if not text and not media:
                continue

            # Determine outgoing flag based on message format.
            # Byte 9 is a format discriminator:
            #   0x00 = standard (user/group/bot): flags at byte 10, bit 2 = outgoing
            #   0x01 = secret chat: flags at byte 10, bit 2 = outgoing
            #   0x20/0x2c = channel format: flags at byte 18, but bit 2 means
            #     "channel posted this" (always set), NOT "user sent this"
            # For channels (hi=2), messages are always incoming from user perspective.
            hi = (peer_id >> 32) & 0xFFFFFFFF
            if hi == 2:
                is_outgoing = False
            else:
                is_outgoing = bool(len(value) > 10 and value[10] & 0x04)

            msg = {
                'peer_id': peer_id,
                'text': text or '',
                'outgoing': is_outgoing,
            }

            if media:
                msg['media'] = media

            timestamp = key_info.get('timestamp')
            if timestamp:
                msg['timestamp'] = timestamp
                msg['date'] = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

            peer_info = peers.get(peer_id)

            if peer_info:
                name_parts = []
                if 'first_name' in peer_info:
                    name_parts.append(peer_info['first_name'])
                if 'last_name' in peer_info:
                    name_parts.append(peer_info['last_name'])
                if name_parts:
                    msg['peer_name'] = ' '.join(name_parts)
                if 'username' in peer_info:
                    msg['peer_username'] = peer_info['username']

                # For secret chats: resolve remote peer name
                hi = (peer_id >> 32) & 0xFFFFFFFF
                if hi == 3 and not msg.get('peer_name'):
                    remote_id = peer_info.get('_remote_peer_id_lo4')
                    remote_le8 = peer_info.get('_remote_peer_id_le8')
                    remote_peer = peers.get(remote_id) if remote_id else None
                    if not remote_peer and remote_le8:
                        remote_peer = peers.get(remote_le8)
                    if remote_peer:
                        rname = remote_peer.get('first_name', '')
                        if 'last_name' in remote_peer:
                            rname += ' ' + remote_peer['last_name']
                        msg['peer_name'] = rname.strip()
                        if 'username' in remote_peer:
                            msg['peer_username'] = remote_peer['username']
                        msg['secret_chat'] = True

            messages.append(msg)

        offset += batch_size
        if offset % 50000 == 0:
            print(f"    Processed {offset:,} rows, {len(messages):,} messages extracted...")

    return messages


def parse_messages_from_fts(conn) -> List[Dict[str, Any]]:
    """Parse messages from full-text search index (ft41_content)."""
    messages = []

    try:
        rows = conn.execute('SELECT id, c0, c1, c2, c3 FROM ft41_content WHERE c2 != ""').fetchall()
        for row_id, peer_ref, msg_ref, text, extra in rows:
            if not text or len(text.strip()) < 1:
                continue

            msg = {
                'fts_id': row_id,
                'peer_ref': peer_ref,
                'msg_ref': msg_ref,
                'text': text.strip(),
                'source': 'fts'
            }
            if extra:
                msg['extra'] = extra
            messages.append(msg)

    except Exception as e:
        print(f"    FTS extraction error: {e}")

    return messages


def export_account(
    conn, account_id: str, output_dir: Path, backup_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Export all data from one account database."""
    account_dir = output_dir / f"account-{account_id}"
    account_dir.mkdir(parents=True, exist_ok=True)

    result = {
        'account_id': account_id,
        'peers': 0,
        'messages_t7': 0,
        'messages_fts': 0,
    }

    # Step 1: Parse peers from t2
    print("  Parsing peers (t2)...")
    peers = {}
    try:
        rows = conn.execute('SELECT key, value FROM t2').fetchall()
        for key, value in rows:
            peer = parse_peer_from_t2(key, value)
            if peer:
                peers[peer['id']] = peer
        print(f"    Found {len(peers)} peers with names")
        result['peers'] = len(peers)
    except Exception as e:
        print(f"    Peer parsing error: {e}")

    # Save peers
    if peers:
        with open(account_dir / 'peers.json', 'w', encoding='utf-8') as f:
            json.dump(list(peers.values()), f, indent=2, ensure_ascii=False)

    # Step 2: Parse messages from t7
    print("  Parsing messages (t7)...")
    media_dir = None
    if backup_dir:
        media_dir = backup_dir / f"account-{account_id}" / "postbox" / "media"
        if not media_dir.is_dir():
            media_dir = None
    messages_t7 = parse_messages_from_t7(conn, peers, media_dir)
    media_count = sum(1 for m in messages_t7 if m.get('media'))
    print(f"    Extracted {len(messages_t7):,} messages from t7 ({media_count:,} with media)")
    result['messages_t7'] = len(messages_t7)

    # Save t7 messages
    if messages_t7:
        with open(account_dir / 'messages.json', 'w', encoding='utf-8') as f:
            json.dump(messages_t7, f, indent=2, ensure_ascii=False)

    # Step 3: Parse FTS messages
    print("  Parsing full-text search index (ft41)...")
    messages_fts = parse_messages_from_fts(conn)
    print(f"    Extracted {len(messages_fts):,} messages from FTS")
    result['messages_fts'] = len(messages_fts)

    if messages_fts:
        with open(account_dir / 'messages_fts.json', 'w', encoding='utf-8') as f:
            json.dump(messages_fts, f, indent=2, ensure_ascii=False)

    # Step 4: Create combined export
    all_messages = messages_t7 + [
        {**m, 'text': m['text']}
        for m in messages_fts
        if not any(t7m['text'] == m['text'] for t7m in messages_t7[:100])
    ]

    all_messages.sort(key=lambda m: m.get('timestamp', 0), reverse=True)

    with open(account_dir / 'all_messages.json', 'w', encoding='utf-8') as f:
        json.dump(all_messages, f, indent=2, ensure_ascii=False)

    # Step 5: Group by conversation
    print("  Grouping into conversations...")
    conversations = {}
    for msg in all_messages:
        peer_key = msg.get('peer_username') or msg.get('peer_name') or str(msg.get('peer_id', 'unknown'))
        if peer_key not in conversations:
            conversations[peer_key] = {
                'peer_id': msg.get('peer_id'),
                'all_peer_ids': set(),
                'peer_name': msg.get('peer_name'),
                'peer_username': msg.get('peer_username'),
                'message_count': 0,
                'messages': [],
            }
        mid = msg.get('peer_id')
        if mid is not None:
            conversations[peer_key]['all_peer_ids'].add(mid)
        conversations[peer_key]['message_count'] += 1
        conversations[peer_key]['messages'].append({
            'text': msg['text'],
            'date': msg.get('date', ''),
            'timestamp': msg.get('timestamp', 0),
        })

    # Sort conversations by message count
    sorted_convos = sorted(conversations.values(), key=lambda c: c['message_count'], reverse=True)

    # Save conversations index
    convo_index = [
        {
            'peer_id': c['peer_id'],
            'all_peer_ids': sorted(c['all_peer_ids']),
            'peer_name': c['peer_name'],
            'peer_username': c['peer_username'],
            'message_count': c['message_count'],
            'first_message': c['messages'][-1]['date'] if c['messages'] else None,
            'last_message': c['messages'][0]['date'] if c['messages'] else None,
        }
        for c in sorted_convos
    ]

    with open(account_dir / 'conversations_index.json', 'w', encoding='utf-8') as f:
        json.dump(convo_index, f, indent=2, ensure_ascii=False)

    # Save individual conversations
    convos_dir = account_dir / 'conversations'
    convos_dir.mkdir(exist_ok=True)
    for convo in sorted_convos:
        export_convo = {**convo, 'all_peer_ids': sorted(convo['all_peer_ids'])}
        safe_name = re.sub(r'[^\w\-]', '_', str(convo.get('peer_username') or convo.get('peer_name') or str(convo.get('peer_id', 'unknown'))))[:80]
        with open(convos_dir / f'{safe_name}.json', 'w', encoding='utf-8') as f:
            json.dump(export_convo, f, indent=2, ensure_ascii=False)

    print(f"    {len(conversations)} conversations saved")
    print(f"    Total combined: {len(all_messages):,} messages")
    result['total_messages'] = len(all_messages)
    result['conversations'] = len(conversations)

    return result


def open_database(db_path: str, db_key: bytes, db_salt: bytes):
    """Open SQLCipher database with Telegram settings."""
    try:
        import sqlcipher3
    except ImportError:
        print("ERROR: sqlcipher3 required. Install with: pip install sqlcipher3")
        sys.exit(1)

    hex_key = (db_key + db_salt).hex()
    conn = sqlcipher3.connect(db_path)
    conn.execute("PRAGMA cipher_default_plaintext_header_size = 32")
    conn.execute(f'PRAGMA key = "x\'{hex_key}\'"')

    # Verify
    count = conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
    print(f"  Database opened: {count} schema objects")
    return conn


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Parse Telegram Postbox database')
    parser.add_argument('backup_dir', help='Backup directory with account-* folders')
    parser.add_argument('--db-key', help='Hex database key (32 bytes)')
    parser.add_argument('--db-salt', help='Hex database salt (16 bytes)')
    parser.add_argument('--tempkey', help='Path to .tempkeyEncrypted')
    parser.add_argument('--password', default='no-matter-key', help='Passcode')
    parser.add_argument('--output', help='Output directory')
    parser.add_argument('--account', help='Only process specific account ID')
    parser.add_argument('--redact', action='store_true',
                        help='Mask sensitive values (account IDs, keys, paths) in console output')

    args = parser.parse_args()
    redact.set_enabled(args.redact)
    backup_dir = Path(args.backup_dir)

    if not backup_dir.exists():
        print(f"ERROR: {redact.path(backup_dir)} not found")
        sys.exit(1)

    # Get keys
    if args.db_key and args.db_salt:
        db_key = bytes.fromhex(args.db_key)
        db_salt = bytes.fromhex(args.db_salt)
    else:
        # Import decrypt function from tg_appstore_decrypt
        from tg_appstore_decrypt import decrypt_tempkey

        tempkey_path = args.tempkey
        if not tempkey_path:
            for candidate in [backup_dir / '.tempkeyEncrypted', backup_dir / 'appstore' / '.tempkeyEncrypted']:
                if candidate.exists():
                    tempkey_path = str(candidate)
                    break

        if not tempkey_path:
            print("ERROR: No --db-key/--db-salt and no .tempkeyEncrypted found")
            sys.exit(1)

        print(f"Decrypting tempkey: {redact.path(tempkey_path)}")
        db_key, db_salt = decrypt_tempkey(tempkey_path, args.password)
        print(f"  Key: {redact.hexkey(db_key.hex()[:8] + '...' + db_key.hex()[-4:])}")
        print(f"  Salt: {redact.hexkey(db_salt.hex()[:8] + '...' + db_salt.hex()[-4:])}")

    output_dir = Path(args.output) if args.output else backup_dir / "parsed_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find accounts
    if args.account:
        account_dirs = [backup_dir / f"account-{args.account}"]
    else:
        account_dirs = sorted(backup_dir.glob("account-*"))

    if not account_dirs:
        print("No account directories found")
        sys.exit(1)

    results = {}

    for account_dir in account_dirs:
        if not account_dir.is_dir():
            continue

        account_id = account_dir.name.replace('account-', '')
        db_path = account_dir / "postbox" / "db" / "db_sqlite"

        if not db_path.exists():
            print(f"\nAccount {redact.account(account_id)}: no database")
            continue

        db_size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"\n{'='*60}")
        print(f"Account: {redact.account(account_id)} ({db_size_mb:.1f} MB)")
        print(f"{'='*60}")

        try:
            conn = open_database(str(db_path), db_key, db_salt)
            result = export_account(conn, account_id, output_dir, backup_dir)
            results[account_id] = result
            conn.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            results[account_id] = {'error': str(e)}

    # Save summary
    summary = {
        'timestamp': datetime.now(tz=timezone.utc).isoformat(),
        'backup_dir': str(backup_dir),
        'accounts': results,
        'total_messages': sum(r.get('total_messages', 0) for r in results.values())
    }

    with open(output_dir / 'summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"EXPORT COMPLETE")
    print(f"  Total messages: {summary['total_messages']:,}")
    print(f"  Output: {redact.path(output_dir)}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
