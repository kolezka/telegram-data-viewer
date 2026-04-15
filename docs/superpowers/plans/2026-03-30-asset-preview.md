# Asset Preview Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a filterable Assets gallery tab and improved inline media previews to the Telegram viewer web UI.

**Architecture:** Parser scans `postbox/media/` at parse time to build `media_catalog.json` per account. Web UI loads this catalog and serves it via new API endpoints. Frontend adds an Assets tab with grid/lightbox and expands inline message media rendering.

**Tech Stack:** Python 3 (Flask), vanilla JavaScript, HTML/CSS (no build tools — matches existing project)

**Spec:** `docs/superpowers/specs/2026-03-30-asset-preview-design.md`

**Security note:** All user-facing content is rendered via safe DOM methods (`textContent`, `createElement`) — no `innerHTML` with untrusted data. The existing `escapeHtml()` helper is used for any dynamic HTML insertion. Media filenames are validated server-side before serving.

---

## Chunk 1: Parser — Media Catalog

### Task 1: Add MIME detection to postbox_parser.py

**Files:**
- Modify: `postbox_parser.py:108-129` (after `_looks_like_metadata`, before `extract_text_from_message`)

- [ ] **Step 1: Add `detect_mime_type()` function**

Add after the `_looks_like_metadata` function (line 129), before `extract_text_from_message`:

```python
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
```

- [ ] **Step 2: Verify parse still works**

Run: `python3 postbox_parser.py --help`
Expected: help text prints, no import errors

- [ ] **Step 3: Commit**

```bash
git add postbox_parser.py
git commit -m "feat: add MIME detection and media type classification to parser"
```

---

### Task 2: Add `build_media_catalog()` function

**Files:**
- Modify: `postbox_parser.py` (add after `build_media_index` at line 301)

- [ ] **Step 1: Add `build_media_catalog()` function**

Add after `build_media_index()` (line 301):

```python
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
            # Extract base pattern (dc-fid) from filename like
            # telegram-cloud-photo-size-4-5994637137116515304-y
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
```

- [ ] **Step 2: Verify parse still works**

Run: `python3 postbox_parser.py --help`
Expected: help text, no errors

- [ ] **Step 3: Commit**

```bash
git add postbox_parser.py
git commit -m "feat: add build_media_catalog() for scanning media directory"
```

---

### Task 3: Integrate catalog into export pipeline

**Files:**
- Modify: `postbox_parser.py:460-590` (`export_account` function)

- [ ] **Step 1: Add catalog generation to `export_account()`**

After the t7 messages save block (after line 508, `json.dump(messages_t7, ...)`), add:

```python
    # Step 2b: Build media catalog
    if media_dir and media_dir.is_dir():
        print("  Building media catalog...")
        media_catalog = build_media_catalog(media_dir, messages_t7)
        if media_catalog:
            with open(account_dir / 'media_catalog.json', 'w', encoding='utf-8') as f:
                json.dump(media_catalog, f, indent=2, ensure_ascii=False)
            result['media_files'] = len(media_catalog)
            print(f"    Saved {len(media_catalog)} media catalog entries")
    else:
        result['media_files'] = 0
```

- [ ] **Step 2: Test by running parser on test data**

Run: `cd /Users/me/Development/tg-viewer && python3 postbox_parser.py test-data/tg_2026-03-26_01-47-29/ --output test-data/tg_2026-03-26_01-47-29/parsed_data`
Expected: Output includes "Building media catalog..." and "Saved X media catalog entries"

- [ ] **Step 3: Verify catalog file exists and has correct structure**

Run: `python3 -c "import json; d=json.load(open('test-data/tg_2026-03-26_01-47-29/parsed_data/account-12103474868840298699/media_catalog.json')); print(f'{len(d)} entries'); print(json.dumps(d[0], indent=2))"`
Expected: Shows entry count and first entry with filename, mime_type, size_bytes, media_type, linked_message fields

- [ ] **Step 4: Commit**

```bash
git add postbox_parser.py
git commit -m "feat: integrate media catalog generation into parse pipeline"
```

---

## Chunk 2: Web UI Backend — API Endpoints

### Task 4: Load media catalog in webui.py

**Files:**
- Modify: `webui.py:23-65` (`load_parsed_data` function)

- [ ] **Step 1: Load media_catalog.json in `load_parsed_data()`**

After loading `messages_fts` (line 52), add:

```python
        media_catalog = []
        catalog_file = account_dir / "media_catalog.json"
        if catalog_file.exists():
            with open(catalog_file) as f:
                media_catalog = json.load(f)
```

Then update the database dict (line 54-61) to include `media_catalog`:

```python
        databases[account_id] = {
            'decrypted': True,
            'messages': messages,
            'messages_fts': messages_fts,
            'peers': peers,
            'conversations': conversations,
            'media_catalog': media_catalog,
            'schema': {'tables': ['t2 (peers)', 't7 (messages)']},
        }
```

Update the print line (line 63) to include media count:

```python
        print(f"  {account_id}: {len(messages)} messages, {len(peers)} peers, {len(conversations)} conversations, {len(messages_fts)} fts, {len(media_catalog)} media")
```

- [ ] **Step 2: Verify by starting webui**

Run: `cd /Users/me/Development/tg-viewer && python3 webui.py test-data/tg_2026-03-26_01-47-29/parsed_data &`
Expected: Startup log includes media count per account

- [ ] **Step 3: Commit**

```bash
git add webui.py
git commit -m "feat: load media_catalog.json in web UI backend"
```

---

### Task 5: Expand MIME detection in webui.py

**Files:**
- Modify: `webui.py:108-138` (`MIME_SIGNATURES` and `_detect_mime`)

- [ ] **Step 1: Update `MIME_SIGNATURES` and `_detect_mime()`**

Replace the existing `MIME_SIGNATURES` list and `_detect_mime` function (lines 108-138):

```python
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


def _detect_mime(filepath: Path) -> str:
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

    # ftyp container (MP4/M4A/MOV)
    if len(header) >= 12 and header[4:8] == b'ftyp':
        if header[8:12] == b'M4A ':
            return 'audio/mp4'
        return 'video/mp4'

    return 'application/octet-stream'
```

- [ ] **Step 2: Commit**

```bash
git add webui.py
git commit -m "feat: expand MIME detection for audio, PDF, and TGS"
```

---

### Task 6: Add /api/assets and /api/assets/stats endpoints

**Files:**
- Modify: `webui.py` (add after `serve_media` route, before `_peer_type`)

- [ ] **Step 1: Add `/api/assets` endpoint**

Add after the `serve_media` route (after line 166):

```python
@app.route('/api/assets')
def get_assets():
    """Get paginated, filterable media assets."""
    account_id = request.args.get('account_id', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    media_type = request.args.get('media_type', '')
    conversation = request.args.get('conversation', '')
    sort = request.args.get('sort', 'date')

    assets = []
    for db_name, db_data in telegram_data.get('databases', {}).items():
        if account_id and db_name != account_id:
            continue
        for entry in db_data.get('media_catalog', []):
            if media_type and entry.get('media_type') != media_type:
                continue
            if conversation:
                linked = entry.get('linked_message')
                if not linked or str(linked.get('peer_id', '')) != conversation:
                    continue
            tagged = dict(entry)
            tagged['_account'] = db_name
            assets.append(tagged)

    # Sort
    if sort == 'size':
        assets.sort(key=lambda a: a.get('size_bytes', 0), reverse=True)
    elif sort == 'type':
        assets.sort(key=lambda a: a.get('media_type', ''))
    else:
        # Default: sort by date (linked message timestamp), unlinked last
        assets.sort(
            key=lambda a: (a.get('linked_message') or {}).get('timestamp', 0),
            reverse=True,
        )

    total = len(assets)
    start = (page - 1) * per_page
    end = start + per_page

    # Collect unique conversations for filter dropdown
    conversations_map = {}
    for db_name, db_data in telegram_data.get('databases', {}).items():
        if account_id and db_name != account_id:
            continue
        for entry in db_data.get('media_catalog', []):
            linked = entry.get('linked_message')
            if linked and linked.get('peer_id'):
                pid = str(linked['peer_id'])
                if pid not in conversations_map:
                    conversations_map[pid] = linked.get('peer_name', f'Chat {pid}')

    return jsonify({
        'assets': assets[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
        'conversations': [
            {'peer_id': pid, 'name': name}
            for pid, name in sorted(conversations_map.items(), key=lambda x: x[1])
        ],
    })


@app.route('/api/assets/stats')
def get_assets_stats():
    """Get asset statistics per account."""
    account_id = request.args.get('account_id', '')

    type_counts = {}
    total_size = 0
    total_count = 0

    for db_name, db_data in telegram_data.get('databases', {}).items():
        if account_id and db_name != account_id:
            continue
        for entry in db_data.get('media_catalog', []):
            mt = entry.get('media_type', 'document')
            type_counts[mt] = type_counts.get(mt, 0) + 1
            total_size += entry.get('size_bytes', 0)
            total_count += 1

    return jsonify({
        'type_counts': type_counts,
        'total_size': total_size,
        'total_count': total_count,
    })
```

- [ ] **Step 2: Test endpoint**

Start webui if not running, then:
Run: `curl -s 'http://127.0.0.1:5000/api/assets?per_page=2' | python3 -m json.tool | head -30`
Expected: JSON with `assets` array, `total`, `page`, `total_pages` fields

Run: `curl -s 'http://127.0.0.1:5000/api/assets/stats' | python3 -m json.tool`
Expected: JSON with `type_counts`, `total_size`, `total_count`

- [ ] **Step 3: Commit**

```bash
git add webui.py
git commit -m "feat: add /api/assets and /api/assets/stats endpoints"
```

---

## Chunk 3: Frontend — Assets Tab, Grid, and Filters

### Task 7: Add Assets tab button and pane

**Files:**
- Modify: `templates/index.html:106-146` (tabs section)

- [ ] **Step 1: Add Assets tab button**

In the `tab-buttons` div (line 107-112), add a new button after Databases:

```html
<button class="tab-button" onclick="showTab('assets')">Assets</button>
```

- [ ] **Step 2: Add Assets tab pane**

After the databases-tab pane (after line 145), add:

```html
<div class="tab-pane" id="assets-tab">
    <div class="filter-bar" id="asset-filters">
        <select id="asset-account" class="search-box" style="width:auto;margin:0" onchange="loadAssets(1)">
            <option value="">All Accounts</option>
        </select>
        <select id="asset-type-filter" class="search-box" style="width:auto;margin:0" onchange="loadAssets(1)">
            <option value="">All Types</option>
            <option value="photo">Photos</option>
            <option value="video">Videos</option>
            <option value="audio">Audio</option>
            <option value="sticker">Stickers</option>
            <option value="gif">GIFs</option>
            <option value="document">Documents</option>
        </select>
        <select id="asset-conversation" class="search-box" style="width:auto;margin:0" onchange="loadAssets(1)">
            <option value="">All Conversations</option>
        </select>
        <select id="asset-sort" class="search-box" style="width:auto;margin:0" onchange="loadAssets(1)">
            <option value="date">Sort: Date</option>
            <option value="size">Sort: Size</option>
            <option value="type">Sort: Type</option>
        </select>
    </div>
    <div id="asset-stats-row" style="color:#666;margin-bottom:12px;font-size:0.9em;"></div>
    <div id="asset-grid" class="asset-grid">
        <div class="loading">Select an account or click Assets to browse media</div>
    </div>
    <div class="pagination" id="asset-pagination"></div>
</div>
```

- [ ] **Step 3: Update `showTab()` to handle assets**

In the `showTab` function (line 520-525), add the assets case:

```javascript
case 'assets': loadAssets(); break;
```

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: add Assets tab HTML structure with filter controls"
```

---

### Task 8: Add Assets CSS styles

**Files:**
- Modify: `templates/index.html:7-78` (style block)

- [ ] **Step 1: Add asset grid and lightbox CSS**

Add before the closing `</style>` tag (before line 78):

```css
.asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.asset-cell { position: relative; aspect-ratio: 1; overflow: hidden; border-radius: 6px; cursor: pointer; background: #f0f0f0; border: 1px solid #ddd; display: flex; align-items: center; justify-content: center; }
.asset-cell:hover { border-color: #0088cc; box-shadow: 0 2px 8px rgba(0,136,204,0.2); }
.asset-cell img { width: 100%; height: 100%; object-fit: cover; }
.asset-cell .type-badge { position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.6); color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 8px; }
.asset-cell .placeholder-icon { font-size: 2.5em; color: #999; }

.lightbox-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.lightbox-content { display: flex; max-width: 90vw; max-height: 90vh; background: white; border-radius: 8px; overflow: hidden; }
.lightbox-preview { flex: 1; display: flex; align-items: center; justify-content: center; background: #111; min-width: 300px; max-width: 65vw; position: relative; }
.lightbox-preview img, .lightbox-preview video { max-width: 100%; max-height: 85vh; object-fit: contain; }
.lightbox-preview audio { width: 80%; }
.lightbox-sidebar { width: 280px; padding: 20px; overflow-y: auto; font-size: 0.9em; }
.lightbox-sidebar h4 { margin-bottom: 12px; color: #333; }
.lightbox-sidebar .meta-row { margin-bottom: 8px; }
.lightbox-sidebar .meta-label { color: #888; font-size: 0.85em; }
.lightbox-sidebar .meta-value { margin-top: 2px; word-break: break-all; }
.lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,0.9); border: none; font-size: 1.5em; padding: 8px 14px; cursor: pointer; border-radius: 4px; z-index: 1001; }
.lightbox-nav:hover { background: white; }
.lightbox-nav.prev { left: 10px; }
.lightbox-nav.next { right: 290px; }
.lightbox-close { position: absolute; top: 10px; right: 10px; background: rgba(255,255,255,0.9); border: none; font-size: 1.2em; padding: 6px 10px; cursor: pointer; border-radius: 4px; z-index: 1001; }
.lightbox-download { display: inline-block; margin-top: 12px; padding: 8px 16px; background: #0088cc; color: white; text-decoration: none; border-radius: 4px; text-align: center; }
.lightbox-download:hover { background: #006699; }

.conv-message audio { width: 100%; margin-top: 6px; }
.conv-message .doc-link { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; background: #f8f9fa; border: 1px solid #ddd; border-radius: 6px; margin-top: 6px; text-decoration: none; color: #333; font-size: 0.9em; }
.conv-message .doc-link:hover { background: #e8f4fd; border-color: #0088cc; }
```

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: add CSS for asset grid, lightbox, and inline media"
```

---

### Task 9: Add Assets JavaScript — grid loading and stats

**Files:**
- Modify: `templates/index.html` (script section, after existing functions)

- [ ] **Step 1: Add asset loading functions**

Add before the `// Initialize` comment (before line 581). All dynamic content uses safe DOM methods (`createElement`, `textContent`) — no raw HTML insertion with user data:

```javascript
let currentAssets = [];
let lightboxIndex = -1;

async function loadAssets(page = 1) {
    const accountId = document.getElementById('asset-account').value;
    const mediaType = document.getElementById('asset-type-filter').value;
    const conversation = document.getElementById('asset-conversation').value;
    const sort = document.getElementById('asset-sort').value;

    const params = new URLSearchParams({ page, per_page: 50 });
    if (accountId) params.append('account_id', accountId);
    if (mediaType) params.append('media_type', mediaType);
    if (conversation) params.append('conversation', conversation);
    if (sort) params.append('sort', sort);

    const [data, stats] = await Promise.all([
        fetchAPI('assets?' + params),
        fetchAPI('assets/stats?' + new URLSearchParams(accountId ? {account_id: accountId} : {})),
    ]);

    // Update stats row
    const statsRow = document.getElementById('asset-stats-row');
    if (stats) {
        const parts = Object.entries(stats.type_counts || {})
            .map(function([t, c]) { return c.toLocaleString() + ' ' + t + 's'; })
            .join(', ');
        const sizeMB = ((stats.total_size || 0) / 1048576).toFixed(1);
        statsRow.textContent = stats.total_count.toLocaleString() + ' assets (' + parts + ') \u2014 ' + sizeMB + ' MB';
    }

    // Populate conversation filter (safe DOM methods)
    if (data && data.conversations) {
        const sel = document.getElementById('asset-conversation');
        const current = sel.value;
        sel.textContent = '';
        const defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = 'All Conversations';
        sel.appendChild(defaultOpt);
        data.conversations.forEach(function(c) {
            const opt = document.createElement('option');
            opt.value = c.peer_id;
            opt.textContent = c.name;
            if (c.peer_id === current) opt.selected = true;
            sel.appendChild(opt);
        });
    }

    const grid = document.getElementById('asset-grid');
    if (!data || !data.assets || data.assets.length === 0) {
        grid.textContent = '';
        const empty = document.createElement('div');
        empty.className = 'loading';
        empty.textContent = 'No assets found';
        grid.appendChild(empty);
        document.getElementById('asset-pagination').textContent = '';
        currentAssets = [];
        return;
    }

    currentAssets = data.assets;
    grid.textContent = '';

    data.assets.forEach(function(asset, idx) {
        const cell = document.createElement('div');
        cell.className = 'asset-cell';
        cell.onclick = function() { openLightbox(idx); };

        const account = asset._account || '';
        const url = '/api/media/' + encodeURIComponent(account) + '/' + encodeURIComponent(asset.filename);

        if (asset.media_type === 'photo' || asset.media_type === 'sticker' || asset.media_type === 'gif') {
            var img = document.createElement('img');
            // Use thumbnail variant for grid if available
            var thumbUrl = asset.thumbnail
                ? '/api/media/' + encodeURIComponent(account) + '/' + encodeURIComponent(asset.thumbnail)
                : url;
            img.src = thumbUrl;
            img.loading = 'lazy';
            img.alt = asset.filename;
            cell.appendChild(img);
        } else if (asset.media_type === 'video') {
            const placeholder = document.createElement('div');
            placeholder.className = 'placeholder-icon';
            placeholder.textContent = '\u25B6';
            cell.appendChild(placeholder);
        } else if (asset.media_type === 'audio') {
            const placeholder = document.createElement('div');
            placeholder.className = 'placeholder-icon';
            placeholder.textContent = '\u266B';
            cell.appendChild(placeholder);
        } else {
            const placeholder = document.createElement('div');
            placeholder.className = 'placeholder-icon';
            placeholder.textContent = '\uD83D\uDCC4';
            cell.appendChild(placeholder);
        }

        // Type badge
        const badge = document.createElement('span');
        badge.className = 'type-badge';
        badge.textContent = asset.media_type;
        cell.appendChild(badge);

        grid.appendChild(cell);
    });

    updatePagination(data, 'asset-pagination', loadAssets);
}
```

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: add asset grid loading and stats JavaScript"
```

---

### Task 10: Add lightbox JavaScript

**Files:**
- Modify: `templates/index.html` (script section, after asset functions)

- [ ] **Step 1: Add lightbox functions**

Add after the `loadAssets` function. All rendering uses safe DOM methods — no innerHTML with user data:

```javascript
function openLightbox(index) {
    lightboxIndex = index;
    renderLightbox();
}

function renderLightbox() {
    var asset = currentAssets[lightboxIndex];
    if (!asset) return;

    // Remove existing lightbox
    var existing = document.getElementById('lightbox');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.id = 'lightbox';
    overlay.className = 'lightbox-overlay';
    overlay.onclick = function(e) { if (e.target === overlay) closeLightbox(); };

    var content = document.createElement('div');
    content.className = 'lightbox-content';

    // Preview area
    var preview = document.createElement('div');
    preview.className = 'lightbox-preview';
    var account = asset._account || '';
    var url = '/api/media/' + encodeURIComponent(account) + '/' + encodeURIComponent(asset.filename);

    if (asset.media_type === 'photo' || asset.media_type === 'sticker' || asset.media_type === 'gif') {
        var img = document.createElement('img');
        img.src = url;
        preview.appendChild(img);
    } else if (asset.media_type === 'video') {
        var vid = document.createElement('video');
        vid.src = url;
        vid.controls = true;
        vid.autoplay = true;
        preview.appendChild(vid);
    } else if (asset.media_type === 'audio') {
        var audio = document.createElement('audio');
        audio.src = url;
        audio.controls = true;
        audio.autoplay = true;
        preview.appendChild(audio);
    } else {
        var docIcon = document.createElement('div');
        docIcon.style.cssText = 'color:white;font-size:4em';
        docIcon.textContent = '\uD83D\uDCC4';
        preview.appendChild(docIcon);
    }

    // Nav buttons
    if (lightboxIndex > 0) {
        var prevBtn = document.createElement('button');
        prevBtn.className = 'lightbox-nav prev';
        prevBtn.textContent = '\u2039';
        prevBtn.onclick = function(e) { e.stopPropagation(); lightboxIndex--; renderLightbox(); };
        preview.appendChild(prevBtn);
    }
    if (lightboxIndex < currentAssets.length - 1) {
        var nextBtn = document.createElement('button');
        nextBtn.className = 'lightbox-nav next';
        nextBtn.textContent = '\u203A';
        nextBtn.onclick = function(e) { e.stopPropagation(); lightboxIndex++; renderLightbox(); };
        preview.appendChild(nextBtn);
    }

    // Close button
    var closeBtn = document.createElement('button');
    closeBtn.className = 'lightbox-close';
    closeBtn.textContent = '\u00D7';
    closeBtn.onclick = closeLightbox;
    preview.appendChild(closeBtn);

    // Sidebar
    var sidebar = document.createElement('div');
    sidebar.className = 'lightbox-sidebar';
    var title = document.createElement('h4');
    title.textContent = 'Details';
    sidebar.appendChild(title);

    var meta = [
        ['Filename', asset.filename],
        ['Type', asset.media_type],
        ['MIME', asset.mime_type],
        ['Size', formatFileSize(asset.size_bytes)],
    ];
    if (asset.width && asset.height) {
        meta.push(['Dimensions', asset.width + ' \u00D7 ' + asset.height]);
    }
    if (asset.linked_message) {
        var lm = asset.linked_message;
        if (lm.peer_name) meta.push(['Conversation', lm.peer_name]);
        if (lm.timestamp) meta.push(['Date', formatTimestamp(lm.timestamp)]);
    }

    meta.forEach(function(pair) {
        var row = document.createElement('div');
        row.className = 'meta-row';
        var label = document.createElement('div');
        label.className = 'meta-label';
        label.textContent = pair[0];
        var value = document.createElement('div');
        value.className = 'meta-value';
        value.textContent = String(pair[1] || '');
        row.appendChild(label);
        row.appendChild(value);
        sidebar.appendChild(row);
    });

    // Download link
    var dl = document.createElement('a');
    dl.className = 'lightbox-download';
    dl.href = url;
    dl.download = asset.filename;
    dl.textContent = 'Download';
    sidebar.appendChild(dl);

    content.appendChild(preview);
    content.appendChild(sidebar);
    overlay.appendChild(content);
    document.body.appendChild(overlay);
}

function closeLightbox() {
    var el = document.getElementById('lightbox');
    if (el) el.remove();
    lightboxIndex = -1;
}

function openInlineLightbox(mediaInfo, accountId) {
    // Open a single-item lightbox for inline message media
    currentAssets = [{
        filename: mediaInfo.filename,
        media_type: mediaInfo.media_type || 'photo',
        mime_type: mediaInfo.mime_type || '',
        size_bytes: mediaInfo.size_bytes || 0,
        width: mediaInfo.width || null,
        height: mediaInfo.height || null,
        linked_message: null,
        _account: accountId,
    }];
    lightboxIndex = 0;
    renderLightbox();
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// Keyboard navigation for lightbox
document.addEventListener('keydown', function(e) {
    if (lightboxIndex < 0) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft' && lightboxIndex > 0) { lightboxIndex--; renderLightbox(); }
    if (e.key === 'ArrowRight' && lightboxIndex < currentAssets.length - 1) { lightboxIndex++; renderLightbox(); }
});
```

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: add lightbox with navigation, metadata sidebar, and keyboard support"
```

---

## Chunk 4: Improved Inline Message Previews

### Task 11: Expand inline media rendering in conversation view

**Files:**
- Modify: `templates/index.html:377-401` (media rendering in `loadConversation`)

- [ ] **Step 1: Replace the media rendering block**

Replace the existing media rendering block (lines 377-401) in `loadConversation`. Uses safe DOM methods throughout:

```javascript
// Render media (images/videos/audio/stickers/documents)
if (msg.media && msg.media.length > 0) {
    var account = msg._account || msg._database || '';
    msg.media.forEach(function(m) {
        if (!m.filename) return;
        var url = '/api/media/' + encodeURIComponent(account) + '/' + encodeURIComponent(m.filename);
        var fname = m.filename.toLowerCase();

        // Video: document files that are mp4/webm
        if (fname.includes('document') && (fname.endsWith('.mp4') || fname.endsWith('.webm'))) {
            var vid = document.createElement('video');
            vid.src = url;
            vid.controls = true;
            vid.preload = 'none';
            vid.onclick = function(e) { e.stopPropagation(); };
            el.appendChild(vid);
        }
        // Audio: ogg, mp3, m4a, voice
        else if (fname.endsWith('.ogg') || fname.endsWith('.mp3') || fname.endsWith('.m4a') || fname.includes('voice')) {
            var aud = document.createElement('audio');
            aud.src = url;
            aud.controls = true;
            aud.preload = 'none';
            el.appendChild(aud);
        }
        // Sticker: tgs (animated sticker, show download link)
        else if (fname.includes('-tgs') || fname.endsWith('.tgs')) {
            var stickerLink = document.createElement('a');
            stickerLink.className = 'doc-link';
            stickerLink.href = url;
            stickerLink.download = m.filename;
            stickerLink.textContent = '\uD83C\uDFAD Sticker (download)';
            el.appendChild(stickerLink);
        }
        // GIF
        else if (fname.endsWith('.gif')) {
            var gifImg = document.createElement('img');
            gifImg.src = url;
            gifImg.loading = 'lazy';
            gifImg.style.cursor = 'pointer';
            if (m.width && m.height) gifImg.width = Math.min(m.width, 400);
            (function(mediaRef, acc) {
                gifImg.onclick = function() {
                    openInlineLightbox({filename: mediaRef.filename, media_type: 'gif'}, acc);
                };
            })(m, account);
            el.appendChild(gifImg);
        }
        // Photo
        else if (fname.includes('photo') || fname.endsWith('.jpg') || fname.endsWith('.png') || fname.endsWith('.webp')) {
            var photoImg = document.createElement('img');
            photoImg.src = url;
            photoImg.loading = 'lazy';
            photoImg.style.cursor = 'pointer';
            if (m.width && m.height) photoImg.width = Math.min(m.width, 400);
            (function(mediaRef, acc) {
                photoImg.onclick = function() {
                    openInlineLightbox(
                        {filename: mediaRef.filename, media_type: 'photo', width: mediaRef.width, height: mediaRef.height},
                        acc
                    );
                };
            })(m, account);
            el.appendChild(photoImg);
        }
        // Document: download link
        else {
            var docLink = document.createElement('a');
            docLink.className = 'doc-link';
            docLink.href = url;
            docLink.download = m.filename;
            docLink.textContent = '\uD83D\uDCCE ' + m.filename;
            el.appendChild(docLink);
        }
    });
}
```

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: expand inline message previews for audio, stickers, GIFs, and documents"
```

---

## Chunk 5: Integration and Verification

### Task 12: Wire up account filter and initialization

**Files:**
- Modify: `webui.py` (stats endpoint)
- Modify: `templates/index.html` (initialization block)

- [ ] **Step 1: Add account list to /api/stats response**

In `webui.py`, update the `/api/stats` endpoint to include account list. Add after `stats['total_chats']` (after line 520):

```python
    stats['accounts'] = list(telegram_data.get('databases', {}).keys())
```

- [ ] **Step 2: Update frontend initialization**

Replace the `DOMContentLoaded` handler (lines 581-584) and the `loadStats` function (lines 169-177):

```javascript
document.addEventListener('DOMContentLoaded', async function() {
    var stats = await fetchAPI('stats');
    if (stats) {
        document.getElementById('total-messages').textContent = stats.total_messages.toLocaleString();
        document.getElementById('total-chats').textContent = stats.total_chats.toLocaleString();
        document.getElementById('total-databases').textContent = stats.total_databases;
        document.getElementById('decrypted-databases').textContent = stats.decrypted_databases;

        // Populate account filter for Assets tab
        var sel = document.getElementById('asset-account');
        if (sel && stats.accounts) {
            stats.accounts.forEach(function(acc) {
                var opt = document.createElement('option');
                opt.value = acc;
                opt.textContent = acc;
                sel.appendChild(opt);
            });
        }
    }
    loadMessages();
});
```

Remove the separate `loadStats` function and its call from the old DOMContentLoaded.

- [ ] **Step 3: Commit**

```bash
git add webui.py templates/index.html
git commit -m "feat: wire up account filter and initialize Assets tab"
```

---

### Task 13: End-to-end verification

- [ ] **Step 1: Re-parse test data**

Run: `cd /Users/me/Development/tg-viewer && python3 postbox_parser.py test-data/tg_2026-03-26_01-47-29/ --output test-data/tg_2026-03-26_01-47-29/parsed_data`
Expected: "Building media catalog..." in output, `media_catalog.json` created

- [ ] **Step 2: Start web UI**

Run: `cd /Users/me/Development/tg-viewer && python3 webui.py test-data/tg_2026-03-26_01-47-29/parsed_data`
Expected: Startup log shows media count

- [ ] **Step 3: Test Assets tab**

Open http://127.0.0.1:5000 in browser:
- Click "Assets" tab — grid loads with thumbnails
- Filter by media type — grid updates
- Filter by conversation — grid filters
- Change sort — grid reorders
- Stats row shows counts

- [ ] **Step 4: Test lightbox**

- Click any asset in grid — lightbox opens with preview + sidebar
- Click prev/next arrows — navigates
- Press arrow keys — navigates
- Press Escape — closes
- Metadata sidebar shows filename, type, size, conversation link

- [ ] **Step 5: Test inline message previews**

- Go to Chats tab, open a conversation with media
- Photos still display correctly
- Audio/document media (if exists) uses new renderers

- [ ] **Step 6: Test pagination**

- Assets tab pagination controls appear for large sets
- Navigate to page 2+ — new assets load

- [ ] **Step 7: Test empty state**

- Filter to a type with 0 results — "No assets found" shown

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "feat: complete asset preview feature — gallery tab, lightbox, inline previews"
```
