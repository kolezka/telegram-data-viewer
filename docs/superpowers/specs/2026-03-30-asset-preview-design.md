# Asset Preview Design Spec

## Context

The web UI currently displays photos and MP4 videos inline within conversation messages, but has no way to browse all cached media files (13GB+ per account) independently. Many media types (audio, stickers, GIFs, documents) are present in the backup but not rendered at all. This spec adds a standalone Assets gallery tab and improves inline message previews to cover all media types.

## Requirements

- New "Assets" tab: filterable, paginated grid of all media files in `postbox/media/`
- Lightbox with prev/next navigation and metadata sidebar
- Inline message previews expanded to cover audio, stickers, GIFs, and documents
- Per-account browsing (select account first, then browse assets)
- Pagination at 50 items per page
- Download fallback for unsupported/unknown types

## Design

### 1. Media Index (Parser Layer)

During parsing, scan `postbox/media/` and build `media_catalog.json` per account.

**Note:** The existing `build_media_index()` function (line 293) builds a `set` of filenames used internally for resolving media references during message parsing. The new `build_media_catalog()` function is separate — it calls `build_media_index()` internally and produces the full JSON catalog described below.

**Entry structure:**
```json
{
  "filename": "telegram-cloud-photo-size-4-5994637137116515304-y",
  "mime_type": "image/jpeg",
  "size_bytes": 45230,
  "width": 240,
  "height": 320,
  "media_type": "photo",
  "linked_message": {
    "peer_id": 11049657091,
    "peer_name": "THC - General Chat",
    "timestamp": 1764471490,
    "date": "2025-11-30T02:58:10+00:00"
  }
}
```

**Field nullability:** `width` and `height` are optional — set to `null` for audio, documents, and any file where dimensions are unavailable. They are only populated when the file is linked to a parsed message that already carries dimension data from `extract_media_refs()`. No external tools (ffprobe, Pillow) are used for dimension extraction.

**Media type classification** (from MIME + filename patterns):
- `photo` — image/jpeg, image/png, image/gif, image/webp (non-sticker)
- `video` — video/mp4, video/webm
- `audio` — audio/ogg, audio/mpeg, audio/mp4
- `sticker` — files matching `*-tgs` or small webp stickers
- `gif` — GIF files or MP4s from animation cache
- `document` — everything else (PDF, ZIP, etc.)

**Message linkage:** Cross-reference each media filename against `media` arrays in `messages.json` (the raw message export that includes `media` arrays). Do NOT use conversation files — those strip media references. Files not referenced by any message get `linked_message: null` (orphaned cache files).

**Thumbnail strategy:** For photos, prefer smaller Telegram variants (suffixes `-s`, `-m`, `-c`) for grid thumbnails, linking to the largest variant (`-y`) in the lightbox. For videos, audio, stickers, and documents, use CSS-styled placeholder icons in the grid (no generated thumbnails). All images use `loading="lazy"` for progressive loading.

**Performance:** Scanning `postbox/media/` involves `os.stat()` + reading file headers for MIME detection on every file. For large directories (thousands of files), print progress every 500 files to indicate activity, consistent with existing parser output style.

**Output:** `parsed_data/account-{id}/media_catalog.json`

### 2. API Endpoints (Web UI Backend)

New endpoints in `webui.py`:

**`GET /api/assets`**
- Params: `account_id`, `page`, `per_page` (default 50), `media_type`, `conversation` (peer_id), `sort` (date/size/type)
- Returns: paginated array of media index entries, total count, available filter values

**`GET /api/assets/stats`**
- Params: `account_id`
- Returns: count per media_type, total file size, total asset count

Existing `/api/media/<account_id>/<filename>` continues serving files. MIME detection expanded with these magic byte signatures:

| Type | Signature bytes | MIME type | Notes |
|------|----------------|-----------|-------|
| OGG | `4F 67 67 53` ("OggS") | audio/ogg | Voice messages |
| MP3 | `FF FB` / `FF F3` / `FF F2` or `49 44 33` (ID3) | audio/mpeg | Music |
| M4A | `ftyp` at offset 4 + `M4A` subtype | audio/mp4 | Disambiguate from MP4 video by checking `ftypM4A ` vs `ftypisom` |
| PDF | `25 50 44 46` ("%PDF") | application/pdf | Documents |
| TGS | `1F 8B` (gzip header) | application/gzip | Animated stickers |
| WebP | `52 49 46 46` ("RIFF") + `57 45 42 50` ("WEBP") at offset 8 | image/webp | Stickers (already partially supported) |

### 3. Assets Tab (Frontend)

New tab alongside Messages/Chats/Users/Databases.

**Layout:**
- **Top bar:** media type dropdown, searchable conversation dropdown, sort dropdown (Date/Size/Type)
- **Stats row:** "1,234 assets (456 photos, 78 videos, ...)" — updates with filters
- **Grid:** Responsive thumbnail grid (4-6 columns). Each cell: thumbnail + type badge (play icon for video, speaker for audio, etc.)
- **Pagination:** Bottom page controls, 50 per page, matching existing style
- **Empty state:** "No assets found" for empty filter results

**Grid cell behavior:**
- Photo: thumbnail, click opens lightbox
- Video: thumbnail + play badge, click opens lightbox with player
- Audio: waveform placeholder icon, click opens lightbox with audio player
- Sticker/GIF: rendered inline (WebP/GIF displayed, TGS static fallback + download)
- Document: file type icon, click opens lightbox with metadata + download

**Lightbox/Detail Panel:**
- Modal overlay with dark backdrop
- Left: full-size preview (image, video player, audio player, or file icon)
- Right sidebar: filename, type, dimensions, file size, linked conversation + date, download button
- Prev/Next arrows within current filtered set
- Keyboard: arrow keys for nav, Escape to close

### 4. Improved Inline Message Previews

Expand message media rendering in conversation view:

- **Audio:** `<audio>` player with controls
- **GIF:** `<img>` for real GIFs, auto-playing muted `<video>` for MP4 animations
- **Sticker:** Inline at 128x128, WebP displayed directly, TGS static fallback
- **Document:** Styled link with file type icon + filename + size
- **Click-to-lightbox:** All inline media opens the shared lightbox component

No changes to message text, bubble layout, pagination, or existing API responses.

## Key Files to Modify

| File | Changes |
|------|---------|
| `postbox_parser.py` | Add `build_media_catalog()` function, write `media_catalog.json` |
| `webui.py` | Add `/api/assets`, `/api/assets/stats` endpoints, expand MIME detection |
| `templates/index.html` | Add Assets tab, grid, filters, lightbox component, improved inline previews |

## Verification

1. Run `./tg-viewer parse` on test data — verify `media_catalog.json` is created with correct entries
2. Run `./tg-viewer webui` — verify Assets tab loads, filters work, pagination works
3. Click through each media type in grid — verify lightbox renders correctly
4. Open a conversation with media — verify improved inline previews (audio, sticker, document)
5. Test keyboard navigation in lightbox (arrows, escape)
6. Test with empty account (no media) — verify graceful empty state
