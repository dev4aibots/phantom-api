"""PhantomAPI — Vision support.

Extracts image parts from OpenAI-style messages (data: URLs and remote URLs),
materializes them to local files, and hands them to the browser engine which
uploads them into the ChatGPT composer before sending the prompt.
"""

import base64
import mimetypes
import re
import urllib.request
from pathlib import Path

DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9+.\-]+);base64,(.+)$", re.DOTALL)
MAX_IMAGES = 5
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per image


def extract_image_urls(messages: list) -> list:
    """Pull image parts out of OpenAI-style messages, in order.

    Handles both Chat Completions parts ({"type": "image_url", "image_url": {"url"}})
    and Responses API parts ({"type": "input_image", "image_url": "<url>"}).
    """
    urls: list = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "image_url":
                iu = item.get("image_url", {})
                url = iu.get("url") if isinstance(iu, dict) else None
            elif itype == "input_image":
                iu = item.get("image_url")
                url = iu if isinstance(iu, str) else (iu.get("url") if isinstance(iu, dict) else None)
            else:
                continue
            if url:
                urls.append(url)
    return urls[:MAX_IMAGES]


def materialize_images(urls: list, dest_dir: str) -> list:
    """Save data-URL / remote images to files. Returns list of Path objects."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    paths: list = []
    for i, url in enumerate(urls):
        try:
            url = url.strip()
            m = DATA_URL_RE.match(url)
            if m:
                mime, b64 = m.group(1), m.group(2)
                raw = base64.b64decode(b64)
                ext = mimetypes.guess_extension(mime) or ".png"
            elif url.startswith(("http://", "https://")):
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read(MAX_BYTES + 1)
                ctype = resp.headers.get_content_type() or ""
                ext = mimetypes.guess_extension(ctype) if ctype.startswith("image/") else ".png"
            else:
                continue
            if not raw or len(raw) > MAX_BYTES:
                continue
            path = dest / f"vision_{i}{ext}"
            path.write_bytes(raw)
            paths.append(path)
        except Exception as exc:
            print(f"[PhantomAPI] ⚠️ Skipping image {i}: {exc}")
    return paths
