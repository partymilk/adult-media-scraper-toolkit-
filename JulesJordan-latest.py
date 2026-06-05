import re
import sys
import os
from urllib.parse import urlparse, urljoin
import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'mobile': False
    }
)

TRAILER_QUALITY_PREFERENCE = [
    "Trailer_1080",
    "Trailer_720",
    "trailer",
    "Trailer_Mobile",
]

SUPPORTED_DOMAINS = [
    "julesjordan.com",
    "theassfactory.com",
    "manuelferrara.com",
    "girlgirl.com",
    "spermswallowers.com",
]

HOME_PAGES = {
    "julesjordan.com":     "https://www.julesjordan.com/trial/",
    "theassfactory.com":   "https://www.theassfactory.com/trial/",
    "manuelferrara.com":   "https://www.manuelferrara.com/trial/",
    "girlgirl.com":        "https://www.girlgirl.com/trial/",
    "spermswallowers.com": "https://www.spermswallowers.com/trial/",
}


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url.lower().rstrip("/"))
        hostname = parsed.hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return any(hostname == d for d in SUPPORTED_DOMAINS)
    except Exception:
        return False


def get_hostname(url: str) -> str:
    parsed = urlparse(url.lower())
    hostname = parsed.hostname or ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def get_studio_name(url: str) -> str:
    return {
        "julesjordan.com": "Jules Jordan",
        "theassfactory.com": "The Ass Factory",
        "manuelferrara.com": "Manuel Ferrara",
        "girlgirl.com": "Girl Girl",
        "spermswallowers.com": "Sperm Swallowers",
    }.get(get_hostname(url), get_hostname(url))


def get_latest_scene_url(site: str = "julesjordan.com") -> str | None:
    home = HOME_PAGES.get(site)
    if not home:
        print(f"  [ERROR] Unknown site: {site}")
        return None

    print(f"  Checking homepage for latest scene: {home}")
    try:
        response = scraper.get(home, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] Could not fetch homepage: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    for card in soup.select("div.jj-content-card"):
        thumb_link = card.select_one("a.jj-card-thumb[href]")
        if thumb_link:
            href = thumb_link.get("href", "")
            url = href if href.startswith("http") else urljoin(home, href)
            title = card.select_one("h2.jj-card-title")
            title_text = title.get_text(strip=True) if title else "Unknown"
            print(f"  Latest scene: {title_text}")
            print(f"  URL: {url}")
            return url

    print("  [ERROR] Could not find any scene cards on homepage.")
    return None


def download_file(url: str, filename: str) -> bool:
    print(f"  Downloading: {os.path.basename(filename)}")
    try:
        response = scraper.get(url, stream=True, timeout=60)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0

        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r    Progress: {percent:.1f}%", end='', flush=True)

        print(f"\r    [OK] {os.path.basename(filename)}")
        return True
    except Exception as e:
        print(f"\r    [FAIL] {e}")
        return False


def scrape_scene(url: str) -> dict | None:
    print(f"  Fetching page: {url}")
    try:
        response = scraper.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] Could not fetch page: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    scene = {}

    # --- Title ---
    title_tag = soup.select_one("h1.scene-title")
    scene["title"] = title_tag.get_text(strip=True) if title_tag else None

    # --- Date ---
    date_item = None
    for item in soup.select("div.meta-item"):
        lbl = item.select_one("div.lbl")
        if lbl and "Released" in lbl.get_text():
            date_item = item.select_one("div.val")
            break
    scene["date"] = date_item.get_text(strip=True) if date_item else None

    # --- Description ---
    desc_tag = soup.select_one("div.scene-desc")
    scene["details"] = desc_tag.get_text(strip=True) if desc_tag else None

    # --- Performers ---
    performers = []
    for item in soup.select("div.scene-info div.meta-item"):
        lbl = item.select_one("div.lbl")
        if lbl and "Starring" in lbl.get_text():
            for a in item.select("span.update_models a"):
                name = a.get_text(strip=True)
                if name:
                    performers.append({"name": name, "url": a.get("href", "")})
            break
    scene["performers"] = performers

    # --- Trailer sources ---
    video_tag = soup.select_one("video#video-player")
    trailers = {}
    if video_tag:
        for source in video_tag.select("source[data-bitrate]"):
            bitrate = source.get("data-bitrate")
            src = source.get("src")
            if bitrate and src:
                trailers[bitrate] = src
    scene["trailers"] = trailers

    scene["trailer_url"] = None
    scene["trailer_quality"] = None
    for quality in TRAILER_QUALITY_PREFERENCE:
        if quality in trailers:
            scene["trailer_url"] = trailers[quality]
            scene["trailer_quality"] = quality
            break

    scene["image"] = video_tag.get("poster") if video_tag else None
    scene["studio"] = get_studio_name(url)
    scene["url"] = url

    return scene


def scrape_and_save(
    url: str,
    output_filename: str = "scene_info.txt",
    download_trailer: bool = True,
) -> bool:

    print(f"\nProcessing URL: {url}")

    if not is_valid_url(url):
        print(f"\n[ERROR] '{url}' is not a supported Jules Jordan Network URL.")
        return False

    scene = scrape_scene(url)
    if not scene:
        print("\n[ERROR] Could not retrieve scene data.")
        return False

    # --- Download trailer ---
    if download_trailer and scene.get("trailer_url"):
        print("\n" + "=" * 60)
        print("Trailer Download")
        print("=" * 60)

        quality = scene.get("trailer_quality", "trailer")
        safe_title = re.sub(r'[^\w\s-]', '', scene.get('title') or 'scene')
        safe_title = re.sub(r'[-\s]+', '_', safe_title).strip('_')
        filename = f"{safe_title}_{quality}.mp4"

        print(f"  Quality: {quality}")
        print(f"  URL: {scene['trailer_url'][:80]}...")
        download_file(scene["trailer_url"], filename)
    elif download_trailer:
        print("\n  No trailer URL found on page.")

    # --- Output ---
    print("\n" + "=" * 60)
    print("Scene Information")
    print("=" * 60)

    performers = scene.get('performers', [])
    talent_str = ", ".join(p["name"] for p in performers) if performers else "N/A"

    lines = [
        f"**Title**: {scene.get('title') or 'N/A'}",
        f"**Performers**: {talent_str}",
        f"**Date**: {scene.get('date') or 'N/A'}",
        f"**Studio**: {scene.get('studio') or 'N/A'}",
        f"**URL**: {scene.get('url') or 'N/A'}",
    ]

    if scene.get('details'):
        lines.append(f"\n**Description**:\n{scene['details']}")

    output_text = "\n".join(lines)

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(output_text)

    print(output_text)
    print(f"\n[OK] Saved to: {output_filename}")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Jules Jordan Network Scraper")
    print("=" * 60)

    download_trailer = "--no-trailer" not in sys.argv

    # Determine URL — explicit arg, or default to latest from julesjordan.com
    url = None
    output_file = "scene_info.txt"

    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            continue
        # First non-flag arg is either a URL or output filename
        if arg.startswith("http"):
            url = arg
        else:
            output_file = arg

    if not url:
        site = "julesjordan.com"
        for arg in sys.argv:
            if arg.startswith("--site="):
                site = arg.split("=", 1)[1]
        url = get_latest_scene_url(site)
        if not url:
            print("[ERROR] Could not determine latest scene URL.")
            sys.exit(1)

    success = scrape_and_save(url, output_file, download_trailer)
    sys.exit(0 if success else 1)