#!/usr/bin/env python3
"""
Vixen Network Scraper
=====================
Scrapes publicly available scene metadata, gallery images, and trailer
videos from Vixen Network sites (Vixen, Blacked, Tushy, Deeper, etc.)

Dependencies:
    pip install cloudscraper beautifulsoup4 requests

Usage:
    python vixenNetwork_scraper.py <url> [output_file] [--no-images] [--no-trailer]
    python vixenNetwork_scraper.py  # interactive prompt
"""

import json
import os
import re
import sys
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Global cloudscraper session (shared across all requests)
# ---------------------------------------------------------------------------

_scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False,
    }
)

_HEADERS = {
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "DNT": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# File downloader
# ---------------------------------------------------------------------------

def download_file(url: str, dest_path: str) -> bool:
    """
    Stream-download *url* to *dest_path*, printing a live percentage bar.

    Returns True on success, False on any error.
    """
    label = os.path.basename(dest_path)
    print(f"  Downloading: {label}")
    try:
        response = _scraper.get(url, stream=True, timeout=60)
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        received = 0
        chunk_size = 65_536  # 64 KiB

        with open(dest_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                received += len(chunk)
                if total:
                    pct = received / total * 100
                    bar_len = 30
                    filled = int(bar_len * received / total)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    print(f"\r    [{bar}] {pct:5.1f}%", end="", flush=True)

        print(f"\r    [✓] {label}{' ' * 40}")
        return True

    except Exception as exc:
        print(f"\r    [✗] {label} — {exc}{' ' * 40}")
        return False


# ---------------------------------------------------------------------------
# GraphQL queries
# ---------------------------------------------------------------------------

_QUERY_GET_VIDEO = """
query getVideo($videoSlug: String, $site: Site) {
    findOneVideo(input: {slug: $videoSlug, site: $site}) {
        videoId
        title
        description
        releaseDate
        models {
            name
        }
    }
}
"""

_QUERY_GET_TOKEN = """
query getToken($videoId: ID!, $device: Device!) {
    generateVideoToken(input: {videoId: $videoId, device: $device}) {
        p1080 { token }
        p720  { token }
        p480  { token }
    }
}
"""


# ---------------------------------------------------------------------------
# Site class
# ---------------------------------------------------------------------------

class Site:
    """Represents a single Vixen Network studio."""

    def __init__(self, name: str, default_tags: list[str] | None = None):
        self.name = name
        self.default_tags: list[str] = default_tags or []

        # "Blacked Raw" → "BLACKEDRAW", "Tushy Raw" → "TUSHYRAW"
        self.site_id: str = name.replace(" ", "").upper()

        # Derive domain: "BLACKEDRAW" → "blackedraw.com"
        self.home: str = f"https://www.{self.site_id.lower()}.com"
        self.graphql_url: str = f"{self.home}/graphql"

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def matches_url(self, url: str) -> bool:
        """Return True if *url* belongs to this studio."""
        try:
            parsed = urlparse(url.lower().rstrip("/"))
            if not parsed.hostname:
                return False
            parts = parsed.hostname.split(".")
            # Accept www.vixen.com or vixen.com
            base = parts[1] if len(parts) >= 3 and parts[0] == "www" else parts[0]
            if base != self.site_id.lower():
                return False
            path_parts = [p for p in parsed.path.split("/") if p]
            # Expect …/videos/<slug>
            return len(path_parts) >= 2 and path_parts[-2] == "videos"
        except Exception:
            return False

    @staticmethod
    def slug_from_url(url: str) -> str:
        return url.rstrip("/").split("/")[-1].lower()

    # ------------------------------------------------------------------
    # GraphQL helper
    # ------------------------------------------------------------------

    def _graphql(self, payload: dict, referer: str) -> dict | None:
        """POST a GraphQL request and return the parsed JSON, or None on error."""
        headers = {**_HEADERS, "Referer": referer}
        try:
            resp = _scraper.post(
                self.graphql_url, json=payload, headers=headers, timeout=30
            )
            if resp.status_code != 200:
                print(f"  ✗ GraphQL HTTP {resp.status_code}")
                resp.raise_for_status()
                return None

            body = resp.json()
            errors = body.get("errors") or []
            if errors:
                for err in errors:
                    msg = err.get("message", err) if isinstance(err, dict) else err
                    print(f"  ✗ GraphQL error: {msg}")
                return None
            return body

        except Exception as exc:
            print(f"  ✗ GraphQL request failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Scene metadata
    # ------------------------------------------------------------------

    def fetch_scene(self, url: str) -> dict | None:
        """
        Query the GraphQL API for scene metadata.

        Returns a normalised dict with keys:
            video_id, title, description, date, performers, studio, url
        or None on failure.
        """
        print(f"  Querying {self.name} GraphQL API for metadata…")
        slug = self.slug_from_url(url)

        payload = {
            "query": _QUERY_GET_VIDEO,
            "operationName": "getVideo",
            "variables": {"site": self.site_id, "videoSlug": slug},
        }
        body = self._graphql(payload, referer=url)
        if not body or not body.get("data"):
            return None

        raw = body["data"].get("findOneVideo")
        if not raw:
            return None

        performers = [
            m["name"]
            for m in (raw.get("models") or [])
            if isinstance(m, dict) and m.get("name")
        ]

        release_date = raw.get("releaseDate") or ""
        return {
            "video_id": raw.get("videoId"),
            "title": raw.get("title"),
            "description": raw.get("description"),
            "date": release_date.split("T")[0] if release_date else None,
            "performers": performers,
            "studio": self.name,
            "url": url,
        }

    # ------------------------------------------------------------------
    # Trailer token → URL
    # ------------------------------------------------------------------

    def fetch_trailer_url(self, video_id: str | int, referer: str) -> str | None:
        """
        Ask the API to generate a signed streaming token for the trailer.

        Returns the signed CDN URL (which *is* the token value), or None.
        """
        print(f"  Requesting trailer token for videoId={video_id}…")
        payload = {
            "query": _QUERY_GET_TOKEN,
            "operationName": "getToken",
            "variables": {"videoId": video_id, "device": "trailer"},
        }
        body = self._graphql(payload, referer=referer)
        if not body or not body.get("data"):
            return None

        token_data = body["data"].get("generateVideoToken") or {}

        # Prefer 1080p, fall back to 720p, then 480p
        for quality in ("p1080", "p720", "p480"):
            entry = token_data.get(quality) or {}
            token = entry.get("token")
            if token:
                print(f"  ✓ Got {quality.replace('p', '')}p trailer token.")
                return token

        print("  ✗ No trailer token found in response.")
        return None

    # ------------------------------------------------------------------
    # Gallery images (Next.js __NEXT_DATA__ scraping)
    # ------------------------------------------------------------------

    def fetch_gallery_images(self, url: str) -> list[str]:
        """
        Scrape the scene page for gallery image URLs embedded in __NEXT_DATA__.

        Returns a (possibly empty) list of image URL strings.
        """
        print(f"  Fetching page HTML for gallery images…")
        try:
            resp = _scraper.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  ✗ Could not fetch page: {exc}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script_tag or not script_tag.string:
            print("  ✗ __NEXT_DATA__ script tag not found.")
            return []

        try:
            page_data = json.loads(script_tag.string)
        except json.JSONDecodeError as exc:
            print(f"  ✗ Failed to parse __NEXT_DATA__ JSON: {exc}")
            return []

        props = page_data.get("props", {}).get("pageProps", {})

        # ---- Path 1: props.pageProps.galleryImages[] ----
        gallery = props.get("galleryImages") or []
        urls = self._extract_urls_from_list(gallery)
        if urls:
            print(f"  ✓ Found {len(urls)} images via galleryImages path.")
            return urls

        # ---- Path 2: props.pageProps.video / scene.images / gallery ----
        video_obj = (
            props.get("video")
            or props.get("scene")
            or (props.get("data") or {}).get("findOneVideo")
            or {}
        )
        for key in ("images", "gallery", "galleryImages", "photos", "stills"):
            candidate = video_obj.get(key) or []
            urls = self._extract_urls_from_list(candidate)
            if urls:
                print(f"  ✓ Found {len(urls)} images via video.{key} path.")
                return urls

        # ---- Path 3: recursive fallback ----
        print("  Standard paths empty; running recursive image search…")
        urls = self._find_images_recursive(props)
        if urls:
            print(f"  ✓ Found {len(urls)} images via recursive search.")
        else:
            print("  ✗ No gallery images found.")
        return urls

    @staticmethod
    def _extract_urls_from_list(items: list) -> list[str]:
        """Pull image URL strings out of a list of dicts or plain strings."""
        result = []
        for item in items:
            if isinstance(item, dict):
                src = (
                    item.get("url")
                    or item.get("src")
                    or item.get("imageUrl")
                    or item.get("fullUrl")
                    or ""
                )
            elif isinstance(item, str) and item.startswith("http"):
                src = item
            else:
                src = ""
            if src:
                result.append(src)
        return result

    def _find_images_recursive(self, obj, depth: int = 0) -> list[str]:
        """Walk the __NEXT_DATA__ tree looking for image URL arrays."""
        if depth > 7:
            return []
        results: list[str] = []
        _image_keys = {"images", "gallery", "galleryimages", "photos", "stills", "snapshots"}

        if isinstance(obj, dict):
            for key, val in obj.items():
                if key.lower() in _image_keys and isinstance(val, list):
                    found = self._extract_urls_from_list(val)
                    results.extend(found)
                else:
                    results.extend(self._find_images_recursive(val, depth + 1))

        elif isinstance(obj, list):
            for item in obj:
                results.extend(self._find_images_recursive(item, depth + 1))

        return results


# ---------------------------------------------------------------------------
# Supported studios
# ---------------------------------------------------------------------------

STUDIOS: list[Site] = [
    Site("Blacked Raw", ["Black Male"]),
    Site("Blacked",     ["Black Male"]),
    Site("Deeper",      []),
    Site("Milfy",       ["MILF"]),
    Site("Tushy Raw",   ["Anal Sex"]),
    Site("Tushy",       ["Anal Sex"]),
    Site("Slayed",      ["Lesbian Sex"]),
    Site("Vixen",       []),
    Site("Wifey",       []),
]


def find_studio(url: str) -> Site | None:
    """Return the first studio whose domain matches *url*, or None."""
    for studio in STUDIOS:
        if studio.matches_url(url):
            return studio
    return None


# ---------------------------------------------------------------------------
# Safe filename helper
# ---------------------------------------------------------------------------

def safe_name(text: str, fallback: str = "scene") -> str:
    """Convert *text* to a filesystem-safe slug."""
    name = re.sub(r"[^\w\s-]", "", text or fallback)
    name = re.sub(r"[-\s]+", "_", name).strip("_")
    return name or fallback


# ---------------------------------------------------------------------------
# Main scraping orchestrator
# ---------------------------------------------------------------------------

def scrape(
    url: str,
    output_file: str = "scene_info.txt",
    download_images: bool = True,
    download_trailer: bool = True,
) -> bool:
    """
    Full scrape pipeline for a Vixen Network URL.

    1. Identify studio from URL.
    2. Fetch scene metadata via GraphQL.
    3. (Optional) Fetch & download gallery images from __NEXT_DATA__.
    4. (Optional) Fetch trailer token via GraphQL and download.
    5. Write scene info to *output_file*.

    Returns True on overall success (metadata retrieved), False otherwise.
    """
    _banner("Vixen Network Scraper")
    print(f"URL : {url}\n")

    # ---- 1. Identify studio ----
    studio = find_studio(url)
    if studio is None:
        print("[ERROR] URL did not match any supported Vixen Network site.")
        print("\nSupported sites:")
        for s in STUDIOS:
            print(f"  {s.home}/videos/<scene-slug>")
        return False

    print(f"Studio identified: {studio.name}")

    # ---- 2. Scene metadata ----
    _section("Scene Metadata")
    scene = studio.fetch_scene(url)
    if not scene:
        print(
            "[ERROR] Could not retrieve scene metadata.\n"
            "The GraphQL API may have changed, or the slug is invalid."
        )
        return False

    title_slug = safe_name(scene.get("title") or "scene")

    # ---- 3. Gallery images ----
    downloaded_images: list[str] = []
    if download_images:
        _section("Gallery Images")
        image_urls = studio.fetch_gallery_images(url)

        if image_urls:
            folder = f"{title_slug}_images"
            os.makedirs(folder, exist_ok=True)
            print(f"  Saving {len(image_urls)} images → {folder}/\n")

            for idx, img_url in enumerate(image_urls, start=1):
                # Strip query parameters to get the extension
                base = img_url.split("?")[0]
                ext = ("." + base.rsplit(".", 1)[-1]) if "." in base else ".jpg"
                dest = os.path.join(folder, f"image_{idx:03d}{ext}")
                if download_file(img_url, dest):
                    downloaded_images.append(dest)

            print(f"\n  Result: {len(downloaded_images)}/{len(image_urls)} images downloaded.")
        else:
            print("  No gallery images found.")

    # ---- 4. Trailer ----
    trailer_path: str | None = None
    if download_trailer:
        _section("Trailer Download")
        video_id = scene.get("video_id")

        if not video_id:
            print("  ✗ videoId not present in metadata — skipping trailer.")
        else:
            trailer_url = studio.fetch_trailer_url(video_id, referer=url)
            if trailer_url:
                trailer_file = f"{title_slug}_trailer_1080p.mp4"
                if download_file(trailer_url, trailer_file):
                    trailer_path = trailer_file
                    print(f"  Saved: {trailer_file}")
            else:
                print("  ✗ Could not obtain a trailer token — skipping download.")

    # ---- 5. Write scene info ----
    _section("Scene Information")

    performers = scene.get("performers") or []
    talent = ", ".join(performers) if performers else "N/A"

    lines: list[str] = [
        f"**Title**: {scene.get('title') or 'N/A'}",
        f"**Studio**: {scene.get('studio') or 'N/A'}",
        f"**Performers**: {talent}",
        f"**Release Date**: {scene.get('date') or 'N/A'}",
        f"**URL**: {scene.get('url') or 'N/A'}",
    ]

    if scene.get("description"):
        lines += ["", "**Description**:", scene["description"]]

    if downloaded_images:
        lines += [
            "",
            f"**Gallery Images** : {len(downloaded_images)} downloaded → {title_slug}_images/",
        ]
    if trailer_path:
        lines += [f"**Trailer**        : {trailer_path}"]

    output_text = "\n".join(lines)
    print(output_text)

    try:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(output_text + "\n")
        print(f"\n[✓] Scene info saved to: {output_file}")
    except OSError as exc:
        print(f"\n[✗] Could not write output file: {exc}")

    return True


# ---------------------------------------------------------------------------
# Console formatting helpers
# ---------------------------------------------------------------------------

def _banner(text: str) -> None:
    width = 62
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def _section(title: str) -> None:
    print(f"\n{'─' * 62}")
    print(f"  {title}")
    print(f"{'─' * 62}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _banner("Vixen Network Scraper")

    # Parse arguments
    args = sys.argv[1:]

    if args:
        url = args[0]
    else:
        print("\nEnter a Vixen Network video URL.")
        print("  e.g. https://www.vixen.com/videos/scene-slug\n")
        url = input("URL: ").strip()

    if not url:
        print("[ERROR] No URL provided.")
        sys.exit(1)

    output_file   = next((a for a in args[1:] if not a.startswith("-")), "scene_info.txt")
    skip_images   = "--no-images"  in args
    skip_trailer  = "--no-trailer" in args

    success = scrape(
        url=url,
        output_file=output_file,
        download_images=not skip_images,
        download_trailer=not skip_trailer,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
