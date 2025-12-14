import random
import io
import textwrap
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}

def random_google_patent_url():
    import random
    from datetime import date, timedelta
    from urllib.parse import quote_plus

    # General technical keywords suitable for older patents
    keywords = [
        "sensor", "transistor", "amplifier", "oscillator", "semiconductor",
        "antenna", "radar", "telemetry", "signal", "circuit",
        "detector", "controller", "feedback", "modulator", "converter",
        "encoder", "receiver", "transmitter", "measurement", "calibration"
    ]

    # Pick a random keyword
    keyword = random.choice(keywords)

    # Random date between 1950-01-01 and 1980-12-31
    start_date = date(1950, 1, 1)
    end_date = date(1980, 12, 31)
    delta_days = (end_date - start_date).days
    random_date = start_date + timedelta(days=random.randint(0, delta_days))

    # Fixed bounds as requested
    before = "priority:19800101"
    after = "priority:19500101"

    # URL encode keyword
    q = quote_plus(f"({keyword})")

    url = (
        "https://patents.google.com/"
        f"?q={q}&before={before}&after={after}"
    )

    return url


def random_patent_figure_png(
    output_path="patent_figure.png",
    canvas_size=(1200, 1600),
    query_terms=("sensor", "apparatus", "method", "system"),
    font_path=None,
    max_attempts=5,
):
    """
    Fetch a random Google Patents figure and caption and render it to a PNG.
    """

    W, H = canvas_size
    margin = 60
    caption_height = 360

    font = (
        ImageFont.truetype(font_path, 28)
        if font_path
        else ImageFont.load_default()
    )

    for _ in range(max_attempts):

        # ---------------------------------------------------------
        # 1. Search Google Patents (correct endpoint)
        # ---------------------------------------------------------
        #query = random.choice(query_terms)
        #search_url = f"https://patents.google.com/patents?q={query}"

        search_url = random_google_patent_url()
        print('A', search_url)

        r = requests.get(search_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        print('B', soup)

        patent_links = [
            "https://patents.google.com" + a["href"]
            for a in soup.select("a[href^='/patent/']")
        ]

        print('B', patent_links)
        exit()

        if not patent_links:
            continue

        patent_url = random.choice(patent_links)



        # ---------------------------------------------------------
        # 2. Load patent page
        # ---------------------------------------------------------
        r = requests.get(patent_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        print(soup)
        exit()

        figures = soup.select("figure")
        if not figures:
            continue

        fig = random.choice(figures)
        img_tag = fig.find("img")
        caption_tag = fig.find("figcaption")

        if not img_tag or not img_tag.get("src"):
            continue

        caption = (
            caption_tag.get_text(" ", strip=True)
            if caption_tag
            else "Figure from patent"
        )

        # ---------------------------------------------------------
        # 3. Download image
        # ---------------------------------------------------------
        img_url = img_tag["src"]
        img_data = requests.get(img_url, headers=HEADERS, timeout=10).content
        patent_img = Image.open(io.BytesIO(img_data)).convert("RGB")

        # ---------------------------------------------------------
        # 4. Render canvas
        # ---------------------------------------------------------
        canvas = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(canvas)

        image_area = (
            W - 2 * margin,
            H - caption_height - 2 * margin,
        )

        patent_img.thumbnail(image_area, Image.LANCZOS)

        img_x = (W - patent_img.width) // 2
        img_y = margin
        canvas.paste(patent_img, (img_x, img_y))

        # ---------------------------------------------------------
        # 5. Caption
        # ---------------------------------------------------------
        caption_y = img_y + patent_img.height + 40
        wrapped = textwrap.fill(caption, 90)

        draw.text(
            (margin, caption_y),
            wrapped,
            fill="black",
            font=font,
        )

        canvas.save(output_path, "PNG")
        return output_path

    raise RuntimeError("Failed to find a patent with usable figures.")




if __name__ == "__main__":

    random_patent_figure_png(
        output_path="random_patent.png",
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )


