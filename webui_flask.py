#!/usr/bin/env python3
"""
webui.py — Telegram Data Web UI
Web interface for visualizing decrypted Telegram data
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory

app = Flask(__name__)

# Global data storage
telegram_data = {}
export_dir = None
backup_dir = None

def load_parsed_data(data_dir: Path) -> dict:
    """Load parsed_data format from postbox_parser.py"""
    databases = {}

    for account_dir in sorted(data_dir.glob("account-*")):
        account_id = account_dir.name

        messages = []
        messages_file = account_dir / "messages.json"
        if messages_file.exists():
            with open(messages_file) as f:
                messages = json.load(f)

        peers = []
        peers_file = account_dir / "peers.json"
        if peers_file.exists():
            with open(peers_file) as f:
                peers = json.load(f)

        conversations = []
        conversations_file = account_dir / "conversations_index.json"
        if conversations_file.exists():
            with open(conversations_file) as f:
                conversations = json.load(f)

        messages_fts = []
        fts_file = account_dir / "messages_fts.json"
        if fts_file.exists():
            with open(fts_file) as f:
                messages_fts = json.load(f)

        media_catalog = []
        catalog_file = account_dir / "media_catalog.json"
        if catalog_file.exists():
            with open(catalog_file) as f:
                media_catalog = json.load(f)

        databases[account_id] = {
            'decrypted': True,
            'messages': messages,
            'messages_fts': messages_fts,
            'peers': peers,
            'conversations': conversations,
            'media_catalog': media_catalog,
            'schema': {'tables': ['t2 (peers)', 't7 (messages)']},
        }

        print(f"  {account_id}: {len(messages)} messages, {len(peers)} peers, "
              f"{len(conversations)} conversations, {len(messages_fts)} fts, "
              f"{len(media_catalog)} media")

    return {'databases': databases}


def load_telegram_data(data_dir: str):
    """Load exported Telegram data from directory"""
    global telegram_data, export_dir, backup_dir
    export_dir = Path(data_dir)

    # Auto-descend: if pointed at a backup root that contains a parsed_data/
    # subdirectory, use that instead. This lets the user pass either
    # `./tg_<timestamp>/` or `./tg_<timestamp>/parsed_data/` interchangeably.
    nested = export_dir / "parsed_data"
    if nested.is_dir() and (
        (nested / "summary.json").exists() or any(nested.glob("account-*/messages.json"))
    ):
        print(f"Auto-detected parsed_data subdirectory: {nested}")
        export_dir = nested

    # Derive backup_dir (parent of parsed_data)
    backup_dir = export_dir.parent
    # Also try summary.json for explicit backup_dir
    summary_file = export_dir / "summary.json"
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                summary = json.load(f)
            if 'backup_dir' in summary:
                backup_dir = Path(summary['backup_dir'])
        except Exception:
            pass

    has_account_dirs = any(export_dir.glob("account-*"))

    if summary_file.exists() or has_account_dirs:
        print("Detected parsed_data format (postbox_parser.py)")
        telegram_data = load_parsed_data(export_dir)
    else:
        # Legacy format: telegram_export.json or *_export.json
        master_file = export_dir / "telegram_export.json"
        if master_file.exists():
            with open(master_file) as f:
                telegram_data = json.load(f)
        else:
            telegram_data = {'databases': {}}
            for export_file in export_dir.glob("*_export.json"):
                db_name = export_file.stem.replace('_export', '')
                with open(export_file) as f:
                    telegram_data['databases'][db_name] = json.load(f)

    db_count = len(telegram_data.get('databases', {}))
    msg_count = sum(len(db.get('messages', [])) for db in telegram_data.get('databases', {}).values())
    print(f"Loaded {db_count} databases with {msg_count} total messages")
    if db_count > 0 and msg_count == 0:
        print()
        print("WARNING: account-* directories were found but contain no messages.json.")
        print(f"  This usually means '{export_dir}' is a raw backup root, not parsed_data.")
        print(f"  Try: python3 postbox_parser.py '{export_dir}'  (then re-run this command)")

MIME_SIGNATURES = [
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'GIF87a', 'image/gif'),
    (b'GIF89a', 'image/gif'),
    (b'RIFF', 'image/webp'),  # RIFF....WEBP
    (b'\x1a\x45\xdf\xa3', 'video/webm'),
]


def _detect_mime(filepath: Path) -> str:
    """Detect MIME type from file magic bytes."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(12)
    except OSError:
        return 'application/octet-stream'

    for sig, mime in MIME_SIGNATURES:
        if header.startswith(sig):
            if sig == b'RIFF' and len(header) >= 12 and header[8:12] == b'WEBP':
                return 'image/webp'
            elif sig == b'RIFF':
                continue
            return mime

    # MP4/MOV: check for 'ftyp' at offset 4
    if len(header) >= 8 and header[4:8] == b'ftyp':
        return 'video/mp4'

    return 'application/octet-stream'


@app.route('/api/media/<account_id>/<filename>')
def serve_media(account_id, filename):
    """Serve a media file from the backup's media directory."""
    # Validate account_id to prevent path traversal
    if not re.match(r'^account-\d+$', account_id):
        return 'Invalid account ID', 400
    if '..' in filename or '/' in filename or '\\' in filename:
        return 'Invalid filename', 400

    if not backup_dir:
        return 'No backup directory configured', 404

    media_dir = backup_dir / account_id / 'postbox' / 'media'
    filepath = media_dir / filename

    # Verify resolved path stays within media_dir
    try:
        filepath.resolve().relative_to(media_dir.resolve())
    except ValueError:
        return 'Invalid path', 400

    if not filepath.is_file():
        return 'File not found', 404

    mime = _detect_mime(filepath)
    return send_from_directory(str(media_dir), filename, mimetype=mime)


def _peer_type(peer_id: int) -> str:
    """Derive chat type from Postbox peer_id high bytes."""
    hi = (peer_id >> 32) & 0xFFFFFFFF
    if hi == 0:
        return 'user'
    elif hi == 1:
        return 'group'
    elif hi == 2:
        return 'channel'
    elif hi == 3:
        return 'secret'
    elif hi == 8:
        return 'bot'
    return 'other'


@app.route('/api/users')
def get_users():
    """Get all people (peers with first_name), with optional search."""
    search = request.args.get('search', '').lower()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 100))

    users = []
    seen_ids = set()

    for db_name, db_data in telegram_data.get('databases', {}).items():
        for peer in db_data.get('peers', []):
            pid = peer.get('id')
            if pid in seen_ids:
                continue
            # Only show peers with a real name (skip emoji-only or empty)
            first_name = peer.get('first_name', '')
            if not first_name:
                continue
            name = first_name
            if peer.get('last_name'):
                name += ' ' + peer['last_name']
            # Require at least one letter or digit
            if not any(c.isalnum() for c in name):
                continue
            seen_ids.add(pid)

            user = {
                'id': pid,
                'name': name,
                'username': peer.get('username', ''),
                'phone': peer.get('phone', ''),
                'database': db_name,
            }

            if search:
                haystack = (name + ' ' + (user['username'] or '') + ' ' + (user['phone'] or '')).lower()
                if search not in haystack:
                    continue

            users.append(user)

    users.sort(key=lambda u: u['name'].lower())

    total = len(users)
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({
        'users': users[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
    })


@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/api/databases')
def get_databases():
    """Get list of available databases"""
    databases = []
    for db_name, db_data in telegram_data.get('databases', {}).items():
        db_info = {
            'name': db_name,
            'decrypted': db_data.get('decrypted', False),
            'message_count': len(db_data.get('messages', [])),
            'tables': list(db_data.get('schema', {}).get('tables', []))
        }
        databases.append(db_info)
    
    return jsonify(databases)

@app.route('/api/database/<db_name>')
def get_database_info(db_name):
    """Get detailed info about a database"""
    db_data = telegram_data.get('databases', {}).get(db_name)
    if not db_data:
        return jsonify({'error': 'Database not found'}), 404
    
    return jsonify(db_data)

@app.route('/api/messages')
def get_messages():
    """Get messages with filtering and pagination"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    db_name = request.args.get('database')
    search = request.args.get('search', '').lower()
    peer_id = request.args.get('peer_id', '')

    # Support multiple peer_ids (comma-separated) for conversations spanning secret+regular chats
    peer_id_set: set = set()
    if peer_id:
        peer_id_set = set(peer_id.split(','))

    all_messages = []

    # Collect messages from specified database or all databases
    databases_to_search = [db_name] if db_name else telegram_data.get('databases', {}).keys()

    for db in databases_to_search:
        db_data = telegram_data.get('databases', {}).get(db, {})
        messages = db_data.get('messages', [])

        # Track t7 messages by (peer_id, text) so we can dedupe FTS entries
        # that are just cached copies of the live message.
        t7_keys: set = set()

        for msg in messages:
            # Filter by peer_id(s)
            if peer_id_set and str(msg.get('peer_id', '')) not in peer_id_set:
                continue

            # Add database/account info to message
            msg['_database'] = db
            msg['_account'] = db

            text = msg.get('text', '')
            if text:
                t7_keys.add((str(msg.get('peer_id', '')), text))

            # Simple search filtering
            if search:
                msg_text = str(msg).lower()
                if search not in msg_text:
                    continue

            all_messages.append(msg)

        # Include FTS (cached/deleted) messages — skip entries already present in t7.
        fts_peer_refs = {f'p{pid}' for pid in peer_id_set} if peer_id_set else set()
        for fts_msg in db_data.get('messages_fts', []):
            ref = str(fts_msg.get('peer_ref', ''))
            if fts_peer_refs and ref not in fts_peer_refs:
                continue

            fts_text = fts_msg.get('text', '')
            peer_str = ref.lstrip('p')

            # Dedup: same (peer, text) already shipped from t7.
            if (peer_str, fts_text) in t7_keys:
                continue

            if search and search not in fts_text.lower():
                continue

            all_messages.append({
                'text': fts_text,
                'peer_id': peer_str,
                'source': 'fts',
                'fts_id': fts_msg.get('fts_id'),
                'msg_ref': fts_msg.get('msg_ref', ''),
                'timestamp': 0,
                # Direction unknown for cached/deleted FTS entries — UI renders
                # these in a neutral style instead of forcing "incoming".
                'outgoing': None,
                '_database': db,
                '_account': db,
            })

    # Sort by timestamp if available
    try:
        all_messages.sort(key=lambda x: x.get('timestamp', x.get('date', 0)), reverse=True)
    except Exception:
        pass

    # Pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_messages = all_messages[start_idx:end_idx]

    return jsonify({
        'messages': paginated_messages,
        'total': len(all_messages),
        'page': page,
        'per_page': per_page,
        'total_pages': (len(all_messages) + per_page - 1) // per_page
    })

@app.route('/api/chats')
def get_chats():
    """Get chats with optional search and type filters."""
    search = request.args.get('search', '').lower()
    type_filter = request.args.get('type', '')       # secret, user, channel, bot, group
    user_id = request.args.get('user_id', '')         # show chats involving this user
    chats = {}

    # Collect FTS peer_refs so we can mark chats that have deleted/cached messages
    # FTS peer_ref has a 'p' prefix (e.g. 'p13467916798'), strip it for matching
    fts_peer_refs: set = set()
    for db_data in telegram_data.get('databases', {}).values():
        for m in db_data.get('messages_fts', []):
            ref = str(m.get('peer_ref', ''))
            fts_peer_refs.add(ref.lstrip('p'))

    for db_name, db_data in telegram_data.get('databases', {}).items():
        conversations = db_data.get('conversations', [])
        if conversations:
            for conv in conversations:
                chat_id = str(conv.get('peer_id', ''))
                all_ids = [str(x) for x in conv.get('all_peer_ids', [])] or ([chat_id] if chat_id else [])
                if chat_id and chat_id not in chats:
                    pid = conv.get('peer_id') or 0
                    has_fts = any(aid in fts_peer_refs for aid in all_ids)
                    chats[chat_id] = {
                        'id': chat_id,
                        'all_peer_ids': all_ids,
                        'name': conv.get('peer_name') or f"Chat {chat_id}",
                        'username': conv.get('peer_username') or '',
                        'type': _peer_type(pid),
                        'has_fts': has_fts,
                        'message_count': conv.get('message_count', 0),
                        'last_message': conv.get('last_message'),
                        'databases': [db_name],
                    }
                elif chat_id and chat_id in chats:
                    chats[chat_id]['message_count'] += conv.get('message_count', 0)
                    chats[chat_id]['databases'].append(db_name)
            continue

        # Legacy path
        for msg in db_data.get('messages', []):
            chat_id = None
            chat_name = None
            for field in ['chat_id', 'peer_id', 'dialog_id', 'from_id', 'to_id']:
                if field in msg and msg[field]:
                    chat_id = str(msg[field])
                    break
            for field in ['chat_title', 'peer_name', 'from_name', 'title']:
                if field in msg and msg[field]:
                    chat_name = str(msg[field])
                    break
            if chat_id:
                if chat_id not in chats:
                    pid = msg.get('peer_id') or 0
                    chats[chat_id] = {
                        'id': chat_id,
                        'all_peer_ids': [chat_id],
                        'name': chat_name or f"Chat {chat_id}",
                        'username': msg.get('peer_username') or '',
                        'type': _peer_type(pid) if isinstance(pid, int) else 'other',
                        'has_fts': chat_id in fts_peer_refs,
                        'message_count': 0,
                        'last_message': None,
                        'databases': set(),
                    }
                chats[chat_id]['message_count'] += 1
                chats[chat_id]['databases'].add(db_name)
                msg_time = msg.get('timestamp', msg.get('date', 0))
                if not chats[chat_id]['last_message'] or msg_time > chats[chat_id]['last_message']:
                    chats[chat_id]['last_message'] = msg_time

    for chat in chats.values():
        if isinstance(chat['databases'], set):
            chat['databases'] = list(chat['databases'])

    # Apply filters
    if search:
        chats = {
            cid: c for cid, c in chats.items()
            if search in (c.get('name') or '').lower()
            or search in (c.get('username') or '').lower()
            or search in cid
        }

    if type_filter == 'secret':
        chats = {cid: c for cid, c in chats.items() if c['type'] == 'secret'}
    elif type_filter == 'fts':
        chats = {cid: c for cid, c in chats.items() if c['has_fts']}
    elif type_filter:
        chats = {cid: c for cid, c in chats.items() if c['type'] == type_filter}

    # Filter to chats involving a specific user (by matching peer name from users list)
    if user_id:
        # Find user name from peers
        user_name = None
        for db_data in telegram_data.get('databases', {}).values():
            for peer in db_data.get('peers', []):
                if str(peer.get('id', '')) == user_id:
                    user_name = peer.get('first_name', '')
                    if peer.get('last_name'):
                        user_name += ' ' + peer['last_name']
                    break
            if user_name:
                break
        if user_name:
            needle = user_name.lower()
            chats = {
                cid: c for cid, c in chats.items()
                if needle in (c.get('name') or '').lower()
            }

    sorted_chats = sorted(
        chats.values(),
        key=lambda x: x.get('message_count', 0),
        reverse=True,
    )

    return jsonify(sorted_chats)

@app.route('/api/media')
def get_media():
    """Get media catalog across all accounts with search + filter + pagination."""
    search = request.args.get('search', '').lower()
    media_type = request.args.get('type', '')   # photo, video, audio, document, sticker, gif
    account_filter = request.args.get('account', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 60))

    items = []
    for db_name, db_data in telegram_data.get('databases', {}).items():
        if account_filter and db_name != account_filter:
            continue
        for entry in db_data.get('media_catalog', []):
            if media_type and entry.get('media_type') != media_type:
                continue
            if search:
                hay_parts = [
                    entry.get('filename', ''),
                    entry.get('mime_type', ''),
                    entry.get('media_type', ''),
                ]
                linked = entry.get('linked_message') or {}
                hay_parts.append(linked.get('peer_name') or '')
                if search not in ' '.join(hay_parts).lower():
                    continue
            items.append({**entry, 'account': db_name})

    # Sort newest first when timestamp available, otherwise by filename.
    def _sort_key(e):
        linked = e.get('linked_message') or {}
        return -(linked.get('timestamp') or 0)
    items.sort(key=_sort_key)

    # Per-type counts (always over the full unfiltered set, for filter-bar badges).
    counts = {'all': 0}
    for db_data in telegram_data.get('databases', {}).values():
        for entry in db_data.get('media_catalog', []):
            counts['all'] += 1
            mt = entry.get('media_type') or 'document'
            counts[mt] = counts.get(mt, 0) + 1

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({
        'media': items[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'counts': counts,
    })


@app.route('/api/export-data')
def get_export_data():
    """Get all export data for the viewer"""
    # Calculate total media files
    total_media = 0
    if 'media_files' in telegram_data:
        for media in telegram_data.get('media_files', []):
            total_media += media.get('count', 0)
    
    return jsonify({
        'accounts': telegram_data.get('accounts', []),
        'databases': telegram_data.get('databases', {}),
        'media_files': telegram_data.get('media_files', []),
        'total_media': total_media,
        'backup_size': '15 GB'  # You could calculate this dynamically
    })

@app.route('/api/stats')
def get_stats():
    """Get overview statistics"""
    stats = {
        'total_databases': 0,
        'decrypted_databases': 0,
        'total_messages': 0,
        'total_chats': 0,
        'databases': {}
    }
    
    for db_name, db_data in telegram_data.get('databases', {}).items():
        stats['total_databases'] += 1
        
        if db_data.get('decrypted'):
            stats['decrypted_databases'] += 1
        
        messages = db_data.get('messages', [])
        message_count = len(messages)
        stats['total_messages'] += message_count
        
        stats['databases'][db_name] = {
            'decrypted': db_data.get('decrypted', False),
            'message_count': message_count,
            'tables': len(db_data.get('schema', {}).get('tables', []))
        }
    
    # Count unique chats
    chats_response = get_chats()
    stats['total_chats'] = len(chats_response.json)
    
    return jsonify(stats)

@app.template_filter('datetime')
def datetime_filter(timestamp):
    """Convert timestamp to readable datetime"""
    if not timestamp:
        return 'Unknown'
    
    try:
        # Handle different timestamp formats
        if isinstance(timestamp, str):
            timestamp = float(timestamp)
        
        # Convert from seconds to datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(timestamp)

def main():
    parser = argparse.ArgumentParser(description='Start Telegram Data Web UI')
    parser.add_argument('data_dir', help='Directory containing decrypted data')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    if not Path(args.data_dir).exists():
        print(f"ERROR: Data directory not found: {args.data_dir}")
        sys.exit(1)

    # Load data
    load_telegram_data(args.data_dir)
    
    if not telegram_data.get('databases'):
        print("WARNING: No Telegram data found in directory")
        print("Make sure you've run the decryption script first")
    
    print(f"\n🚀 Starting Telegram Data Web UI")
    print(f"📂 Data directory: {args.data_dir}")
    print(f"🌐 URL: http://{args.host}:{args.port}")
    print(f"📊 Loaded {len(telegram_data.get('databases', {}))} databases")
    print("\nPress Ctrl+C to stop")
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()