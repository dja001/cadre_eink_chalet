import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin


def download_plu_image(plu_code: str,
                        description: str,
                        out_dir: str = ".",
                        timeout: int = 10) -> str:
    """
    Download first DuckDuckGo image result for:
        PLU <code> <description>

    Returns local file path.
    """

    query = f"PLU {plu_code} {description}"
    headers = {"User-Agent": "Mozilla/5.0"}

    # DuckDuckGo image search HTML page
    url = f"https://duckduckgo.com/?q={quote_plus(query)}&iax=images&ia=images"

    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # image URLs are embedded in data attributes
    imgs = soup.find_all("img")

    image_url = None
    for img in imgs:
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http"):
            image_url = src
            break

    if not image_url:
        raise RuntimeError("No image found on result page.")

    # download image
    img_resp = requests.get(image_url, headers=headers, timeout=timeout)
    img_resp.raise_for_status()

    os.makedirs(out_dir, exist_ok=True)

    safe_desc = description.replace(" ", "_")
    filepath = os.path.join(out_dir, f"PLU_{plu_code}_{safe_desc}.jpg")

    with open(filepath, "wb") as f:
        f.write(img_resp.content)

    return filepath


if __name__ == '__main__':
    path = download_plu_image("4011", "banana", out_dir="fruits_et_legumes")
    print("Saved to:", path)
