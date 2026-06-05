# Adult Media Scraper Toolkit

A collection of Python CLI utilities for automated metadata extraction, full-resolution gallery archiving, and trailer video acquisition from adult content networks. Each script is purpose-built around a specific site's infrastructure — GraphQL APIs, Next.js hydration trees, and WordPress-based Flowplayer embeds — and outputs a structured local folder per scene containing the media assets alongside a formatted plain-text tracking document.

---

## Scripts Overview

| Script | Target Network | Tech Surface |
|---|---|---|
| `vixenNetwork_scraper_trailer.py` | Vixen, Blacked, Tushy, Deeper, Slayed, Milfy, Wifey, Blacked Raw, Tushy Raw | GraphQL API + `__NEXT_DATA__` tree traversal |
| `JulesJordan-latest.py` | Jules Jordan, The Ass Factory, Manuel Ferrara, Girl Girl, Sperm Swallowers | HTML scraping + progressive trailer download |
| `angelslove_scraper.py` | Angels Love, Sensual Love, UltraFilms, WowGirls Blog | Auto-discovery crawl + Flowplayer JSON + NextGEN gallery |

---

## Features

- **GraphQL metadata extraction** — `vixenNetwork_scraper_trailer.py` queries each studio's `/graphql` endpoint directly for structured scene data (title, performers, release date, description, video ID) without HTML parsing.
- **`__NEXT_DATA__` tree traversal** — recursively walks the hydrated Next.js page payload to locate gallery image arrays under any depth of nesting, handling key aliases (`images`, `gallery`, `stills`, `snapshots`, etc.).
- **Signed CDN token resolution** — fetches a time-limited streaming token from the Vixen Network GraphQL token endpoint, resolving the signed 1080p trailer URL before downloading.
- **Trailer quality selection** — `JulesJordan-latest.py` resolves the best available stream from a priority ladder (`Trailer_1080` → `Trailer_720` → `trailer` → `Trailer_Mobile`) and downloads it with live progress reporting. Supports `--no-trailer` to skip download and `--site=` to target any supported domain in auto mode.
- **Flowplayer JSON asset extraction** — `angelslove_scraper.py` parses the `data-item` attribute on Flowplayer `<div>` elements to extract direct HLS/MP4 source URLs from WordPress-hosted sites.
- **NextGEN gallery image discovery** — locates `data-src` attributes within `ngg-galleryoverview` containers and batch-downloads full-resolution `.jpg`/`.png` assets with sequential zero-padded filenames.
- **Auto-discovery crawl mode** — when run without arguments, `angelslove_scraper.py` scans the landing page of each supported domain, identifies the latest video and photo entries from their respective widget sections, and processes them automatically.
- **Live progress reporting** — all downloads print a real-time progress bar (`█░`) using content-length headers where available, falling back to byte-count output.
- **Idempotent downloads** — all three scrapers skip files that already exist at the destination path, making re-runs safe after interrupted sessions.
- **Structured metadata documents** — each scene produces a plain-text `_info.txt` file alongside the media assets, recording title, studio, release date, and performer list.
- **Cloudscraper bypass layer** — all HTTP sessions use `cloudscraper` with a Chrome/Windows browser fingerprint to handle JS challenge pages transparently.

---

## Prerequisites

**Python 3.8 or higher** is required (3.10+ recommended for union type hints used in `vixenNetwork_scraper_trailer.py`).

---

## Installation

**1. Clone the repository**
```bash
git clone https://github.com/<your-username>/adult-media-scraper-toolkit.git
cd adult-media-scraper-toolkit
```

**2. Create and activate a virtual environment**

macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**3. Install Python dependencies**
```bash
pip install cloudscraper beautifulsoup4 requests
```

---

## Usage

### `vixenNetwork_scraper_trailer.py` — Vixen Network

Scrapes scene metadata, downloads a full gallery image set, and streams the 1080p trailer. Requires a URL in the format `https://www.{site}.com/videos/{scene-slug}`.

```bash
# Interactive mode — prompts for URL
python vixenNetwork_scraper_trailer.py

# Explicit URL — downloads metadata, images, and trailer
python vixenNetwork_scraper_trailer.py https://www.vixen.com/videos/scene-slug

# Custom output filename for the metadata text file
python vixenNetwork_scraper_trailer.py https://www.blacked.com/videos/scene-slug my_scene.txt

# Skip gallery image download
python vixenNetwork_scraper_trailer.py https://www.tushy.com/videos/scene-slug --no-images

# Skip trailer download
python vixenNetwork_scraper_trailer.py https://www.deeper.com/videos/scene-slug --no-trailer

# Metadata only — no media downloaded
python vixenNetwork_scraper_trailer.py https://www.vixen.com/videos/scene-slug --no-images --no-trailer
```

**Supported sites:** `vixen.com`, `blacked.com`, `blackedraw.com`, `tushy.com`, `tushyraw.com`, `deeper.com`, `slayed.com`, `milfy.com`, `wifey.com`

**Output per scene:**
```
scene-title_images/
    image_001.jpg
    image_002.jpg
    ...
scene-title_trailer_1080p.mp4
scene_info.txt
```

---

### `JulesJordan-latest.py` — Jules Jordan Network

Fetches the latest scene from a supported site automatically, or targets a specific URL. Downloads the highest-quality available trailer with live progress reporting.

```bash
# Auto mode — scrapes the latest scene from julesjordan.com
python JulesJordan-latest.py

# Target a specific scene URL
python JulesJordan-latest.py https://www.julesjordan.com/trial/categories/movies/scene-slug.html

# Skip trailer download — metadata only
python JulesJordan-latest.py --no-trailer

# Auto mode targeting a different supported site
python JulesJordan-latest.py --site=girlgirl.com
```

Trailer quality preference order: `Trailer_1080` → `Trailer_720` → `trailer` → `Trailer_Mobile`

**Supported sites:** `julesjordan.com`, `theassfactory.com`, `manuelferrara.com`, `girlgirl.com`, `spermswallowers.com`

**Output per scene:**
```
Scene_Title_Trailer_1080.mp4   ← Highest available quality trailer
scene_info.txt                 ← Title, performers, date, studio, URL, description
```

---

### `angelslove_scraper.py` — Multi-Site (Angels Love / Sensual Love / UltraFilms / WowGirls)

Operates in either auto-discovery mode (no arguments) or targeted mode (explicit URL). Produces a unified per-scene folder containing the video stream, full photo gallery, and a formatted info document.

```bash
# Auto mode — crawls all four supported domains for latest content
python angelslove_scraper.py

# Target a specific video page
python angelslove_scraper.py https://www.angelslove.xxx/videos/scene-name-2/

# Target a specific photo gallery page directly
python angelslove_scraper.py https://www.ultrafilms.xxx/photos/gallery-slug/
```

**Supported domains:** `angelslove.xxx`, `sensuallove.xxx`, `ultrafilms.xxx`, `wowgirlsblog.com`

**Output per scene:**
```
Scene - Scene_Title/
    Scene_Title.mp4           ← Flowplayer source stream
    001.jpg
    002.jpg
    ...
    Scene_Title_info.txt      ← Title, site, release date, performers
```

---

## Project Directory Layout

```
adult-media-scraper-toolkit/
│
├── vixenNetwork_scraper_trailer.py     # Vixen Network GraphQL + Next.js scraper
├── JulesJordan-latest.py      # Jules Jordan HTML scraper + trailer downloader
├── angelslove_scraper.py          # Multi-site Flowplayer + NextGEN gallery scraper
│
├── README.md
├── .gitignore
│
└── output/                     # Default local download area (git-ignored)
    ├── Scene - Example Title/
    │   ├── Example_Title.mp4
    │   ├── 001.jpg
    │   └── Example_Title_info.txt
    ├── example_scene_images/
    │   ├── image_001.jpg
    │   └── image_002.jpg
    ├── Example_Title_Trailer_1080.mp4
    └── scene_info.txt
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `cloudscraper` | Cloudflare JS-challenge bypass layer for all HTTP sessions |
| `beautifulsoup4` | HTML parsing for WordPress/standard page structures |
| `requests` | HTTP transport (pulled in transitively by cloudscraper) |


---

## Notes

- These utilities target publicly accessible trailer and preview content. Membership-gated full-length video streams are not in scope and will not resolve.
- CDN tokens issued by the Vixen Network GraphQL API are time-limited. Begin the download promptly after token retrieval.
- `angelslove_scraper.py` auto-discovery mode targets the first result only from each domain's landing widget section. Run with an explicit URL to target a specific scene.
- Re-running any script against a previously downloaded output folder is safe — existing files are detected and skipped without re-downloading.
