#!/usr/bin/env python3
"""
Multi-Site Unified Media Scraper
================================
Supports auto-discovery and manual processing for:
    - https://www.angelslove.xxx/
    - https://www.sensuallove.xxx/
    - https://www.ultrafilms.xxx/
    - https://www.wowgirlsblog.com/

Downloads video assets, full-res photo galleries, and formats 
scene information into a clean tracking text document inside a single folder.

Dependencies:
    pip install cloudscraper beautifulsoup4

Usage:
    python network_scraper.py            # Automatically updates from all sites
    python network_scraper.py <url>      # Targets a specific scene or gallery link
"""

import json
import os
import re
import sys
from urllib.parse import urlparse, urljoin
import cloudscraper
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Global Session Settings
# ---------------------------------------------------------------------------
scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False,
    }
)

# Supported domain array mapping
SUPPORTED_DOMAINS = [
    "angelslove.xxx",
    "sensuallove.xxx",
    "ultrafilms.xxx",
    "wowgirlsblog.com"
]

# ---------------------------------------------------------------------------
# Core Utilities
# ---------------------------------------------------------------------------
def get_hostname(url: str) -> str:
    parsed = urlparse(url.lower())
    hostname = parsed.hostname or ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname

def get_site_display_name(url: str) -> str:
    """Maps domains to clean metadata branding strings."""
    return {
        "angelslove.xxx": "Angels.Love",
        "sensuallove.xxx": "Sensual.Love",
        "ultrafilms.xxx": "UltraFilms",
        "wowgirlsblog.com": "WowGirlsBlog",
    }.get(get_hostname(url), "Unknown Studio")

def download_file(url: str, dest_path: str) -> bool:
    """Downloads a file chunk-by-chunk matching the preference layout."""
    if os.path.exists(dest_path):
        print(f"  [➔] File already exists, skipping: {os.path.basename(dest_path)}")
        return True

    try:
        response = scraper.get(url, stream=True, timeout=45)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        total_mb = f"{total_size / (1024*1024):.2f} MB" if total_size > 0 else "Unknown Size"
        print(f"  [↓] Downloading: {os.path.basename(dest_path)} ({total_mb})...", end="", flush=True)
        
        downloaded = 0
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r    Progress: {percent:.1f}%", end='', flush=True)
                        
        print(f"\r    [OK] Completed asset: {os.path.basename(dest_path)}")
        return True
    except Exception as e:
        print(f"\r    [FAIL] Download execution broke: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False

# ---------------------------------------------------------------------------
# Metadata Tracking Engine Document Writer
# ---------------------------------------------------------------------------
def save_metadata_txt(folder: str, filename_slug: str, title: str, site_display: str, date: str, performers: list) -> None:
    """Creates a neatly formatted text document tracking scene setups."""
    meta_path = os.path.join(folder, f"{filename_slug}_info.txt")
    performers_str = ", ".join(performers) if performers else "N/A"
    
    lines = [
        f"Title: {title}",
        f"Site: {site_display}",
        f"Release Date: {date}",
        f"Performers: {performers_str}"
    ]
    
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  [✓] Documentation structured text saved to folder.")
    except Exception as e:
        print(f"  [✗] Failed to write metadata file context: {e}")

# ---------------------------------------------------------------------------
# Auto-Discovery Index Scanner
# ---------------------------------------------------------------------------
def get_latest_site_media(domain_root: str) -> tuple:
    """Scans clean RetroTube target IDs for active scene elements."""
    base = f"https://www.{domain_root}/"
    print(f"[➔] Querying landing content matrix: {base}")
    try:
        res = scraper.get(base, timeout=25)
        if res.status_code != 200:
            return None, None

        soup = BeautifulSoup(res.text, 'html.parser')
        movie_url, photo_url = None, None

        # Extract Video Link
        movie_section = soup.find('section', id='widget_videos_block-1')
        if movie_section:
            first_movie = movie_section.find('article', class_='loop-video')
            if first_movie:
                link = first_movie.find('a', href=True)
                if link: movie_url = link['href']

        # Extract Photos Gallery Link
        photo_section = soup.find('section', id='widget_videos_block-3')
        if photo_section:
            first_gallery = photo_section.find('article', class_='format-gallery')
            if first_gallery:
                link = first_gallery.find('a', href=True)
                if link: photo_url = link['href']

        return movie_url, photo_url
    except Exception as e:
        print(f"  [!] Index crawling run broke on platform {domain_root}: {e}")
        return None, None

# ---------------------------------------------------------------------------
# Main Scraper Execution Pipelines
# ---------------------------------------------------------------------------
def scrape_movie_page(url: str, target_folder: str = None) -> str:
    """Extracts internal Flowplayer payloads and writes local folder structures."""
    print(f"\n  Parsing Video Content Node: {url}")
    try:
        res = scraper.get(url, timeout=25)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # Title Processing
        title_tag = soup.find('h1', class_='entry-title') or soup.find('meta', property='og:title')
        title = "Unknown Video"
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title_tag.get('content'):
                title = title_tag['content'].split('‣')[-1].strip()

        # Performers Mapping
        models = []
        actors_div = soup.find('div', id='video-actors')
        if actors_div:
            models = [a.get_text(strip=True) for a in actors_div.find_all('a')]

        # Date Tracking
        release_date = "N/A"
        date_meta = soup.find('meta', property='article:published_time')
        if date_meta and date_meta.get('content'):
            release_date = date_meta['content'].split('T')[0]

        # Flowplayer Asset Extraction Block
        media_url = None
        flowplayer_div = soup.find('div', class_='flowplayer')
        if flowplayer_div and flowplayer_div.get('data-item'):
            try:
                data_item = json.loads(flowplayer_div['data-item'])
                if data_item.get('sources') and len(data_item['sources']) > 0:
                    media_url = data_item['sources'][0].get('src')
            except Exception:
                pass

        if not media_url:
            print("  [✗] Could not trace high-resolution stream payload assets.")
            return target_folder

        # Standardize naming configuration parameters
        safe_title = re.sub(r'\W+', '_', title).strip('_')
        if not target_folder:
            target_folder = f"Scene - {safe_title}"
        os.makedirs(target_folder, exist_ok=True)

        # Export scene document details safely
        site_display = get_site_display_name(url)
        save_metadata_txt(target_folder, safe_title, title, site_display, release_date, models)

        # Pull high-resolution video stream
        ext = os.path.splitext(urlparse(media_url).path)[-1] or ".mp4"
        video_dest = os.path.join(target_folder, f"{safe_title}{ext}")
        download_file(media_url, video_dest)

        return target_folder
    except Exception as e:
        print(f"  [ERROR] Processing video payload execution dropped: {e}")
        return target_folder

def scrape_photos_page(url: str, target_folder: str = None):
    """Parses photo galleries via high-res HTML5 data-src elements."""
    print(f"\n  Parsing Photo Gallery Node: {url}")
    try:
        res = scraper.get(url, timeout=25)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        title_tag = soup.find('h1', class_='entry-title')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Gallery"

        if not target_folder:
            safe_title = re.sub(r'\W+', '_', title).strip('_')
            target_folder = f"Scene - {safe_title}"
        os.makedirs(target_folder, exist_ok=True)

        # Pull explicit image links out of data-src NextGEN tags safely
        image_links = []
        gallery_overview = soup.find('div', class_='ngg-galleryoverview')
        if gallery_overview:
            for a in gallery_overview.find_all('a'):
                img_url = a.get('data-src') or a.get('href')
                if img_url:
                    if "title" in img_url and not img_url.endswith('.jpg'):
                        img_url = img_url.split('title')[0].strip()
                    if img_url not in image_links and any(img_url.lower().endswith(x) for x in ['.jpg', '.jpeg', '.png']):
                        image_links.append(img_url)

        if not image_links:
            print("  [✗] No gallery picture reference points found.")
            return

        print(f"  Found {len(image_links)} images. Commencing unified downloading loop...")
        
        # Pull standalone metadata if photos are targeted directly via direct link argument step execution
        safe_title = os.path.basename(target_folder).replace("Scene - ", "")
        if not os.path.exists(os.path.join(target_folder, f"{safe_title}_info.txt")):
            models = []
            actors_div = soup.find('div', id='video-actors')
            if actors_div: models = [a.get_text(strip=True) for a in actors_div.find_all('a')]
            
            release_date = "N/A"
            date_meta = soup.find('meta', property='article:published_time')
            if date_meta and date_meta.get('content'): release_date = date_meta['content'].split('T')[0]
            
            save_metadata_txt(target_folder, safe_title, title, get_site_display_name(url), release_date, models)

        # Batch write images cleanly sequentially into the shared folder setup context
        for idx, img_url in enumerate(image_links, 1):
            ext = os.path.splitext(urlparse(img_url).path)[-1] or ".jpg"
            img_dest = os.path.join(target_folder, f"{idx:03d}{ext}")
            download_file(img_url, img_dest)

    except Exception as e:
        print(f"  [ERROR] Image download routine dropped processing error bounds: {e}")

# ---------------------------------------------------------------------------
# Main Routing Application Logic Entry Block
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 66)
    print("  Unified Multi-Site Retrotube Engine Scraper Pipeline")
    print("=" * 66)
    
    args = sys.argv[1:]

    if args:
        target_url = args[0].strip()
        # Evaluate explicit site processing types dynamically based on sub-slug extensions
        if "-2/" in target_url or target_url.rstrip('/').endswith('-2'):
            shared_dir = scrape_movie_page(target_url)
            guessed_photo_url = target_url.replace("-2/", "/")
            scrape_photos_page(guessed_photo_url, target_folder=shared_dir)
        else:
            # Handles routing variants where video URLs don't explicitly carry standard indicators
            hostname = get_hostname(target_url)
            if hostname in SUPPORTED_DOMAINS:
                shared_dir = scrape_movie_page(target_url)
                # Fallback to standard check if no streaming parameters are initialized
                scrape_photos_page(target_url, target_folder=shared_dir)
            else:
                scrape_photos_page(target_url)
    else:
        print("[!] No direct URL provided. Starting auto-update cycles across network instances...")
        for domain in SUPPORTED_DOMAINS:
            print(f"\n--- Processing Profile: {domain} ---")
            latest_movie, latest_photo = get_latest_site_media(domain)
            
            if latest_movie:
                shared_dir = scrape_movie_page(latest_movie)
                if latest_photo:
                    scrape_photos_page(latest_photo, target_folder=shared_dir)
            elif latest_photo:
                scrape_photos_page(latest_photo)
            else:
                print(f"  [➔] No active update points pulled down for {domain}.")

    print(f"\n{'=' * 66}\n  Process complete. Task execution logs terminated cleanly.\n{'=' * 66}")

if __name__ == "__main__":
    main()