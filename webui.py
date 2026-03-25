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

        databases[account_id] = {
            'decrypted': True,
            'messages': messages,
            'messages_fts': messages_fts,
            'peers': peers,
            'conversations': conversations,
            'schema': {'tables': ['t2 (peers)', 't7 (messages)']},
        }

        print(f"  {account_id}: {len(messages)} messages, {len(peers)} peers, {len(conversations)} conversations, {len(messages_fts)} fts")

    return {'databases': databases}


def load_telegram_data(data_dir: str):
    """Load exported Telegram data from directory"""
    global telegram_data, export_dir, backup_dir
    export_dir = Path(data_dir)

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

    all_messages = []

    # Collect messages from specified database or all databases
    databases_to_search = [db_name] if db_name else telegram_data.get('databases', {}).keys()

    for db in databases_to_search:
        db_data = telegram_data.get('databases', {}).get(db, {})
        messages = db_data.get('messages', [])

        for msg in messages:
            # Filter by peer_id
            if peer_id and str(msg.get('peer_id', '')) != peer_id:
                continue

            # Add database/account info to message
            msg['_database'] = db
            msg['_account'] = db

            # Simple search filtering
            if search:
                msg_text = str(msg).lower()
                if search not in msg_text:
                    continue

            all_messages.append(msg)

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
                if chat_id and chat_id not in chats:
                    pid = conv.get('peer_id') or 0
                    chats[chat_id] = {
                        'id': chat_id,
                        'name': conv.get('peer_name') or f"Chat {chat_id}",
                        'username': conv.get('peer_username') or '',
                        'type': _peer_type(pid),
                        'has_fts': chat_id in fts_peer_refs,
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

def create_templates():
    """Create HTML templates"""
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    
    # Main template
    index_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Data Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header h1 { color: #333; margin-bottom: 10px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-number { font-size: 2em; font-weight: bold; color: #0088cc; }
        .stat-label { color: #666; margin-top: 5px; }
        .tabs { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .tab-buttons { display: flex; background: #f8f9fa; }
        .tab-button { flex: 1; padding: 15px; border: none; background: transparent; cursor: pointer; border-bottom: 3px solid transparent; }
        .tab-button.active { background: white; border-bottom-color: #0088cc; }
        .tab-content { padding: 20px; }
        .tab-pane { display: none; }
        .tab-pane.active { display: block; }
        .message-list { max-height: 600px; overflow-y: auto; }
        .message { border-bottom: 1px solid #eee; padding: 15px; }
        .message:hover { background: #f8f9fa; }
        .message-meta { color: #666; font-size: 0.9em; margin-bottom: 5px; }
        .message-content { margin: 10px 0; }
        .search-box { width: 100%; padding: 10px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 4px; }
        .pagination { text-align: center; margin-top: 20px; }
        .pagination button { margin: 0 5px; padding: 8px 12px; border: 1px solid #ddd; background: white; cursor: pointer; }
        .pagination button.active { background: #0088cc; color: white; }
        .loading { text-align: center; padding: 40px; color: #666; }
        .database-list { display: grid; gap: 10px; }
        .database-item { padding: 15px; border: 1px solid #ddd; border-radius: 4px; background: white; }
        .database-item.decrypted { border-color: #28a745; }
        .database-item.encrypted { border-color: #dc3545; }
        .chat-list { display: grid; gap: 10px; }
        .chat-item { padding: 15px; border: 1px solid #ddd; border-radius: 4px; background: white; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
        .chat-item:hover { border-color: #0088cc; background: #f0f8ff; }
        .chat-item.selected { border-color: #0088cc; border-width: 2px; background: #e8f4fd; }
        .chat-info h4 { margin-bottom: 5px; }
        .chat-info small { color: #666; }
        .chat-stats { text-align: right; flex-shrink: 0; }
        .filter-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
        .filter-btn { padding: 6px 14px; border: 1px solid #ddd; border-radius: 16px; background: white; cursor: pointer; font-size: 0.9em; transition: all 0.15s; }
        .filter-btn:hover { border-color: #0088cc; color: #0088cc; }
        .filter-btn.active { background: #0088cc; color: white; border-color: #0088cc; }
        .filter-btn .badge { display: inline-block; background: rgba(0,0,0,0.1); padding: 1px 6px; border-radius: 10px; font-size: 0.85em; margin-left: 4px; }
        .filter-btn.active .badge { background: rgba(255,255,255,0.3); }
        .user-list { display: grid; gap: 8px; }
        .user-item { padding: 12px 15px; border: 1px solid #ddd; border-radius: 4px; background: white; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
        .user-item:hover { border-color: #0088cc; background: #f0f8ff; }
        .user-name { font-weight: 600; }
        .user-details { color: #666; font-size: 0.9em; }
        .chat-type-tag { display: inline-block; font-size: 0.75em; padding: 2px 7px; border-radius: 10px; margin-left: 6px; vertical-align: middle; }
        .chat-type-tag.secret { background: #ffe0e0; color: #c00; }
        .chat-type-tag.bot { background: #e0e0ff; color: #44c; }
        .chat-type-tag.channel { background: #e0ffe0; color: #070; }
        .chat-type-tag.group { background: #fff3e0; color: #a60; }
        .chat-type-tag.fts { background: #fff0f0; color: #c55; }
        .conversation-panel { margin-top: 15px; border-top: 2px solid #0088cc; padding-top: 15px; }
        .conversation-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .conversation-header h3 { color: #0088cc; }
        .conversation-header button { padding: 6px 14px; border: 1px solid #ddd; background: white; border-radius: 4px; cursor: pointer; }
        .conversation-header button:hover { background: #f8f9fa; }

        .conv-message { padding: 10px 14px; margin-bottom: 6px; border-radius: 12px; max-width: 80%; }
        .conv-message.incoming { background: #f0f0f0; align-self: flex-start; border-bottom-left-radius: 2px; }
        .conv-message.outgoing { background: #dcf8c6; align-self: flex-end; border-bottom-right-radius: 2px; }
        .conv-message .msg-time { font-size: 0.8em; color: #888; }
        .conv-message .msg-text { margin-top: 4px; }
        .conv-message img { max-width: 100%; border-radius: 8px; margin-top: 6px; cursor: pointer; display: block; }
        .conv-message video { max-width: 100%; border-radius: 8px; margin-top: 6px; display: block; }
        .conversation-messages { max-height: 500px; overflow-y: auto; display: flex; flex-direction: column; }
        .error { color: #dc3545; padding: 20px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📱 Telegram Data Viewer</h1>
            <p>Explore your decrypted Telegram messages, chats, and databases</p>
        </div>

        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="total-messages">-</div>
                <div class="stat-label">Total Messages</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="total-chats">-</div>
                <div class="stat-label">Chats</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="total-databases">-</div>
                <div class="stat-label">Databases</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="decrypted-databases">-</div>
                <div class="stat-label">Decrypted</div>
            </div>
        </div>

        <div class="tabs">
            <div class="tab-buttons">
                <button class="tab-button active" onclick="showTab('messages')">Messages</button>
                <button class="tab-button" onclick="showTab('chats')">Chats</button>
                <button class="tab-button" onclick="showTab('users')">Users</button>
                <button class="tab-button" onclick="showTab('databases')">Databases</button>
            </div>

            <div class="tab-content">
                <div class="tab-pane active" id="messages-tab">
                    <input type="text" class="search-box" id="message-search" placeholder="Search messages..." onkeyup="searchMessages()">
                    <div class="message-list" id="message-list">
                        <div class="loading">Loading messages...</div>
                    </div>
                    <div class="pagination" id="message-pagination"></div>
                </div>

                <div class="tab-pane" id="chats-tab">
                    <input type="text" class="search-box" id="chat-search" placeholder="Search conversations by name or username..." onkeyup="searchChats()">
                    <div class="filter-bar" id="chat-filters"></div>
                    <div class="chat-list" id="chat-list">
                        <div class="loading">Loading chats...</div>
                    </div>
                    <div id="conversation-panel"></div>
                    <div class="pagination" id="conversation-pagination"></div>
                </div>

                <div class="tab-pane" id="users-tab">
                    <input type="text" class="search-box" id="user-search" placeholder="Search people by name, username, or phone..." onkeyup="searchUsers()">
                    <div class="user-list" id="user-list">
                        <div class="loading">Loading users...</div>
                    </div>
                    <div class="pagination" id="user-pagination"></div>
                </div>

                <div class="tab-pane" id="databases-tab">
                    <div class="database-list" id="database-list">
                        <div class="loading">Loading databases...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentPage = 1;
        let searchTimeout;
        let chatSearchTimeout;
        let userSearchTimeout;
        let selectedChatId = null;
        let selectedChatName = null;
        let chatTypeFilter = '';

        async function fetchAPI(endpoint) {
            try {
                const response = await fetch(`/api/${endpoint}`);
                return await response.json();
            } catch (error) {
                console.error('API Error:', error);
                return null;
            }
        }

        async function loadStats() {
            const stats = await fetchAPI('stats');
            if (stats) {
                document.getElementById('total-messages').textContent = stats.total_messages.toLocaleString();
                document.getElementById('total-chats').textContent = stats.total_chats.toLocaleString();
                document.getElementById('total-databases').textContent = stats.total_databases;
                document.getElementById('decrypted-databases').textContent = stats.decrypted_databases;
            }
        }

        async function loadMessages(page = 1) {
            const search = document.getElementById('message-search').value;
            const params = new URLSearchParams({ page, per_page: 50 });
            if (search) params.append('search', search);
            
            const data = await fetchAPI(`messages?${params}`);
            const messageList = document.getElementById('message-list');
            
            if (!data || !data.messages) {
                messageList.innerHTML = '<div class="error">Failed to load messages</div>';
                return;
            }
            
            if (data.messages.length === 0) {
                messageList.innerHTML = '<div class="loading">No messages found</div>';
                return;
            }
            
            messageList.innerHTML = data.messages.map(msg => `
                <div class="message">
                    <div class="message-meta">
                        Database: ${msg._database || 'Unknown'} | 
                        Table: ${msg._table || 'Unknown'} |
                        Time: ${formatTimestamp(msg.timestamp || msg.date)}
                    </div>
                    <div class="message-content">
                        ${formatMessageContent(msg)}
                    </div>
                </div>
            `).join('');
            
            // Update pagination
            updatePagination(data, 'message-pagination', loadMessages);
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        function renderChatFilters(allChats) {
            const bar = document.getElementById('chat-filters');
            bar.innerHTML = '';

            // Count types from unfiltered data (fetch all to count)
            const filters = [
                { key: '', label: 'All' },
                { key: 'secret', label: 'Secret' },
                { key: 'fts', label: 'Cached/Deleted' },
                { key: 'user', label: 'Users' },
                { key: 'channel', label: 'Channels' },
                { key: 'bot', label: 'Bots' },
                { key: 'group', label: 'Groups' },
            ];

            filters.forEach(f => {
                const btn = document.createElement('button');
                btn.className = 'filter-btn' + (chatTypeFilter === f.key ? ' active' : '');
                btn.textContent = f.label;
                btn.onclick = () => { chatTypeFilter = f.key; loadChats(); };
                bar.appendChild(btn);
            });
        }

        async function loadChats(fromUser) {
            const search = document.getElementById('chat-search').value;
            const params = new URLSearchParams();
            if (search) params.append('search', search);
            if (chatTypeFilter) params.append('type', chatTypeFilter);
            if (fromUser) params.append('user_id', fromUser);

            const chats = await fetchAPI(`chats?${params}`);
            const chatList = document.getElementById('chat-list');

            renderChatFilters(chats || []);

            if (!chats) {
                chatList.textContent = 'Failed to load chats';
                return;
            }

            if (chats.length === 0) {
                chatList.textContent = search ? 'No conversations matching "' + search + '"' : 'No conversations found';
                return;
            }

            chatList.innerHTML = '';
            chats.forEach(chat => {
                const item = document.createElement('div');
                item.className = 'chat-item' + (selectedChatId === chat.id ? ' selected' : '');
                item.onclick = () => openConversation(chat.id, chat.name);

                const info = document.createElement('div');
                info.className = 'chat-info';
                const h4 = document.createElement('h4');
                h4.textContent = chat.name;

                // Type tag
                if (chat.type && chat.type !== 'other') {
                    const tag = document.createElement('span');
                    tag.className = 'chat-type-tag ' + chat.type;
                    tag.textContent = chat.type;
                    h4.appendChild(tag);
                }
                if (chat.has_fts) {
                    const ftsTag = document.createElement('span');
                    ftsTag.className = 'chat-type-tag fts';
                    ftsTag.textContent = 'cached';
                    h4.appendChild(ftsTag);
                }

                const small = document.createElement('small');
                small.textContent = (chat.username ? '@' + chat.username + ' | ' : '') + chat.message_count.toLocaleString() + ' messages';
                info.appendChild(h4);
                info.appendChild(small);

                const stats = document.createElement('div');
                stats.className = 'chat-stats';
                const timeSmall = document.createElement('small');
                timeSmall.textContent = formatTimestamp(chat.last_message);
                stats.appendChild(timeSmall);

                item.appendChild(info);
                item.appendChild(stats);
                chatList.appendChild(item);
            });
        }

        function searchChats() {
            clearTimeout(chatSearchTimeout);
            chatSearchTimeout = setTimeout(() => loadChats(), 300);
        }

        async function openConversation(peerId, peerName) {
            selectedChatId = peerId;
            selectedChatName = peerName;
            await loadChats();
            loadConversation(1);
        }

        async function loadConversation(page = 1) {
            const panel = document.getElementById('conversation-panel');
            if (!selectedChatId) { panel.textContent = ''; return; }

            const params = new URLSearchParams({ peer_id: selectedChatId, page, per_page: 50 });
            const data = await fetchAPI(`messages?${params}`);

            panel.innerHTML = '';
            const wrapper = document.createElement('div');
            wrapper.className = 'conversation-panel';

            const header = document.createElement('div');
            header.className = 'conversation-header';
            const title = document.createElement('h3');
            title.textContent = selectedChatName + ' (' + (data ? data.total.toLocaleString() : '0') + ' messages)';
            const closeBtn = document.createElement('button');
            closeBtn.textContent = 'Close';
            closeBtn.onclick = closeConversation;
            header.appendChild(title);
            header.appendChild(closeBtn);
            wrapper.appendChild(header);

            if (!data || !data.messages || data.messages.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'loading';
                empty.textContent = 'No messages found';
                wrapper.appendChild(empty);
                panel.appendChild(wrapper);
                return;
            }

            const msgs = [...data.messages].sort((a, b) =>
                (a.timestamp || a.date || 0) - (b.timestamp || b.date || 0)
            );

            const container = document.createElement('div');
            container.className = 'conversation-messages';
            msgs.forEach(msg => {
                const el = document.createElement('div');
                const direction = msg.outgoing ? 'outgoing' : 'incoming';
                el.className = 'conv-message ' + direction;
                const time = document.createElement('span');
                time.className = 'msg-time';
                time.textContent = formatTimestamp(msg.timestamp || msg.date) + (msg.outgoing ? ' (you)' : '');
                const text = document.createElement('div');
                text.className = 'msg-text';
                const msgText = msg.text || msg.message || msg.content || '';
                if (msgText) {
                    text.textContent = msgText;
                    el.appendChild(time);
                    el.appendChild(text);
                } else {
                    el.appendChild(time);
                }

                // Render media (images/videos)
                if (msg.media && msg.media.length > 0) {
                    const account = msg._account || msg._database || '';
                    msg.media.forEach(m => {
                        if (!m.filename) return;
                        const url = '/api/media/' + account + '/' + m.filename;
                        const fname = m.filename.toLowerCase();
                        if (fname.includes('document') && fname.endsWith('.mp4')) {
                            const vid = document.createElement('video');
                            vid.src = url;
                            vid.controls = true;
                            vid.preload = 'none';
                            el.appendChild(vid);
                        } else {
                            const img = document.createElement('img');
                            img.src = url;
                            img.loading = 'lazy';
                            if (m.width && m.height) {
                                img.width = Math.min(m.width, 400);
                            }
                            img.onclick = () => window.open(url, '_blank');
                            el.appendChild(img);
                        }
                    });
                }

                container.appendChild(el);
            });

            wrapper.appendChild(container);
            panel.appendChild(wrapper);

            updatePagination(data, 'conversation-pagination', loadConversation);
        }

        function closeConversation() {
            selectedChatId = null;
            selectedChatName = null;
            document.getElementById('conversation-panel').innerHTML = '';
            document.getElementById('conversation-pagination').innerHTML = '';
            loadChats();
        }

        async function loadUsers(page = 1) {
            const search = document.getElementById('user-search').value;
            const params = new URLSearchParams({ page, per_page: 100 });
            if (search) params.append('search', search);

            const data = await fetchAPI(`users?${params}`);
            const userList = document.getElementById('user-list');

            if (!data || !data.users) {
                userList.textContent = 'Failed to load users';
                return;
            }

            if (data.users.length === 0) {
                userList.textContent = search ? 'No users matching "' + search + '"' : 'No users found';
                return;
            }

            userList.innerHTML = '';
            data.users.forEach(user => {
                const item = document.createElement('div');
                item.className = 'user-item';
                item.onclick = () => showUserChats(user.id, user.name);

                const left = document.createElement('div');
                const nameEl = document.createElement('span');
                nameEl.className = 'user-name';
                nameEl.textContent = user.name;
                left.appendChild(nameEl);

                if (user.username) {
                    const un = document.createElement('span');
                    un.className = 'user-details';
                    un.textContent = '  @' + user.username;
                    left.appendChild(un);
                }

                const right = document.createElement('div');
                right.className = 'user-details';
                right.textContent = user.phone || '';

                item.appendChild(left);
                item.appendChild(right);
                userList.appendChild(item);
            });

            updatePagination(data, 'user-pagination', loadUsers);
        }

        function searchUsers() {
            clearTimeout(userSearchTimeout);
            userSearchTimeout = setTimeout(() => loadUsers(1), 300);
        }

        function showUserChats(userId, userName) {
            // Switch to chats tab and filter by user
            document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
            document.querySelectorAll('.tab-button')[1].classList.add('active');
            document.getElementById('chats-tab').classList.add('active');

            document.getElementById('chat-search').value = userName;
            chatTypeFilter = '';
            loadChats();
        }

        async function loadDatabases() {
            const databases = await fetchAPI('databases');
            const dbList = document.getElementById('database-list');
            
            if (!databases) {
                dbList.innerHTML = '<div class="error">Failed to load databases</div>';
                return;
            }
            
            if (databases.length === 0) {
                dbList.innerHTML = '<div class="loading">No databases found</div>';
                return;
            }
            
            dbList.innerHTML = databases.map(db => `
                <div class="database-item ${db.decrypted ? 'decrypted' : 'encrypted'}">
                    <h4>${db.name}</h4>
                    <p>Status: ${db.decrypted ? '✅ Decrypted' : '❌ Encrypted'}</p>
                    <p>Messages: ${db.message_count.toLocaleString()}</p>
                    <p>Tables: ${db.tables.join(', ')}</p>
                </div>
            `).join('');
        }

        function showTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // Update tab content
            document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
            document.getElementById(tabName + '-tab').classList.add('active');
            
            // Load tab content
            switch(tabName) {
                case 'messages': loadMessages(); break;
                case 'chats': loadChats(); break;
                case 'users': loadUsers(); break;
                case 'databases': loadDatabases(); break;
            }
        }

        function searchMessages() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => loadMessages(1), 500);
        }

        function formatTimestamp(timestamp) {
            if (!timestamp) return 'Unknown';
            try {
                return new Date(timestamp * 1000).toLocaleString();
            } catch {
                return timestamp;
            }
        }

        function formatMessageContent(msg) {
            // Extract meaningful content from message object
            const textFields = ['text', 'message', 'content', 'body'];
            for (let field of textFields) {
                if (msg[field]) {
                    return `<strong>${field}:</strong> ${msg[field]}`;
                }
            }
            
            // Show first few key-value pairs
            const keys = Object.keys(msg).filter(k => !k.startsWith('_')).slice(0, 5);
            return keys.map(key => `<strong>${key}:</strong> ${msg[key]}`).join('<br>');
        }

        function updatePagination(data, elementId, loadFunc) {
            const pagination = document.getElementById(elementId);
            if (data.total_pages <= 1) {
                pagination.innerHTML = '';
                return;
            }
            
            let buttons = [];
            for (let i = 1; i <= data.total_pages; i++) {
                if (i === 1 || i === data.total_pages || Math.abs(i - data.page) <= 2) {
                    buttons.push(`
                        <button class="${i === data.page ? 'active' : ''}" 
                                onclick="${loadFunc.name}(${i})">
                            ${i}
                        </button>
                    `);
                } else if (buttons[buttons.length - 1] !== '...') {
                    buttons.push('<span>...</span>');
                }
            }
            
            pagination.innerHTML = buttons.join('');
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadStats();
            loadMessages();
        });
    </script>
</body>
</html>'''
    
    with open(templates_dir / "index.html", "w") as f:
        f.write(index_html)

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
    
    # Create templates
    create_templates()
    
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