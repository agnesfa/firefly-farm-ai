#!/usr/bin/env python3
"""
Generate QR codes for nursery locations and seed bank.

Creates QR codes that link to observe pages for each nursery zone,
plus one for the Seed Bank. These allow workers to scan and record
observations/inventory updates at each nursery location.

Usage:
    python scripts/generate_nursery_qrcodes.py --base-url https://agnesfa.github.io/firefly-farm-ai/
"""

import argparse
import math
from pathlib import Path

try:
    import qrcode
except ImportError:
    print("Install qrcode: pip install qrcode[pil]")
    exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Install Pillow: pip install Pillow")
    exit(1)

# Nursery locations to generate QR codes for
# Format: (id, display_label, subtitle)
NURSERY_LOCATIONS = [
    # Shelving unit 1
    ("NURS.SH1-1", "Shelf 1-1", "Nursery — Shelving Unit 1, Top"),
    ("NURS.SH1-2", "Shelf 1-2", "Nursery — Shelving Unit 1"),
    ("NURS.SH1-3", "Shelf 1-3", "Nursery — Shelving Unit 1"),
    ("NURS.SH1-4", "Shelf 1-4", "Nursery — Shelving Unit 1, Bottom"),
    # Shelving unit 2
    ("NURS.SH2-1", "Shelf 2-1", "Nursery — Shelving Unit 2, Top"),
    ("NURS.SH2-2", "Shelf 2-2", "Nursery — Shelving Unit 2"),
    ("NURS.SH2-3", "Shelf 2-3", "Nursery — Shelving Unit 2"),
    ("NURS.SH2-4", "Shelf 2-4", "Nursery — Shelving Unit 2, Bottom"),
    # Shelving unit 3
    ("NURS.SH3-1", "Shelf 3-1", "Nursery — Shelving Unit 3, Top"),
    ("NURS.SH3-2", "Shelf 3-2", "Nursery — Shelving Unit 3"),
    ("NURS.SH3-3", "Shelf 3-3", "Nursery — Shelving Unit 3"),
    ("NURS.SH3-4", "Shelf 3-4", "Nursery — Shelving Unit 3, Bottom"),
    # Ground areas
    ("NURS.GR", "Ground", "Nursery — Ground Area"),
    ("NURS.GL", "Ground Left", "Nursery — Ground Left"),
    ("NURS.FRT", "Front", "Nursery — Front Area"),
    ("NURS.BCK", "Back", "Nursery — Back Area"),
    ("NURS.HILL", "Hill", "Nursery — Hillside"),
    ("NURS.STRB", "Strawberry", "Nursery — Strawberry Area"),
    # Seed bank (single code for fridge + freezer)
    ("SEED.BANK", "Seed Bank", "Firefly Corner Farm"),
]


def get_fonts():
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    font_large = font_small = None
    for path in font_paths:
        try:
            font_large = ImageFont.truetype(path, 28)
            font_small = ImageFont.truetype(path, 16)
            break
        except (OSError, IOError):
            continue
    if not font_large:
        font_large = ImageFont.load_default()
        font_small = font_large
    return font_large, font_small


def generate_qr(url, label, output_path, subtitle="Firefly Corner Farm"):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color=(45, 80, 22), back_color=(255, 255, 255))
    img = img.convert("RGB")

    qr_size = img.size[0]
    label_height = 60
    combined = Image.new("RGB", (qr_size, qr_size + label_height), "white")
    combined.paste(img, (0, 0))

    font_large, font_small = get_fonts()
    draw = ImageDraw.Draw(combined)

    bbox = draw.textbbox((0, 0), label, font=font_large)
    text_w = bbox[2] - bbox[0]
    draw.text(((qr_size - text_w) / 2, qr_size + 5), label, fill=(45, 80, 22), font=font_large)

    bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
    text_w2 = bbox2[2] - bbox2[0]
    draw.text(((qr_size - text_w2) / 2, qr_size + 35), subtitle, fill=(150, 150, 150), font=font_small)

    combined.save(output_path)
    return combined


def generate_a4_sheets(qr_images, output_dir):
    A4_W, A4_H = 2480, 3508
    MARGIN = 100
    COLS, ROWS = 2, 4
    PER_PAGE = COLS * ROWS

    usable_w = A4_W - 2 * MARGIN
    usable_h = A4_H - 2 * MARGIN
    cell_w = usable_w // COLS
    cell_h = usable_h // ROWS

    pages = math.ceil(len(qr_images) / PER_PAGE)
    sheet_paths = []

    for page_idx in range(pages):
        sheet = Image.new("RGB", (A4_W, A4_H), "white")
        start = page_idx * PER_PAGE
        page_items = qr_images[start:start + PER_PAGE]

        for i, (label, qr_img) in enumerate(page_items):
            col = i % COLS
            row = i // COLS
            qr_w, qr_h = qr_img.size
            scale = min((cell_w - 40) / qr_w, (cell_h - 40) / qr_h)
            new_w = int(qr_w * scale)
            new_h = int(qr_h * scale)
            resized = qr_img.resize((new_w, new_h), Image.LANCZOS)
            x = MARGIN + col * cell_w + (cell_w - new_w) // 2
            y = MARGIN + row * cell_h + (cell_h - new_h) // 2
            sheet.paste(resized, (x, y))

        sheet_path = output_dir / f"nursery_print_sheet_{page_idx + 1}.png"
        sheet.save(sheet_path, dpi=(300, 300))
        sheet_paths.append(sheet_path)
        print(f"  Print sheet {page_idx + 1}/{pages}: {len(page_items)} QR codes")

    return sheet_paths


def main():
    parser = argparse.ArgumentParser(description="Generate QR codes for nursery locations")
    parser.add_argument("--base-url", required=True, help="Base URL for GitHub Pages")
    parser.add_argument("--output", default="site/public/qrcodes/", help="Output directory")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/") + "/"
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(NURSERY_LOCATIONS)} nursery QR codes...")

    qr_images = []
    for loc_id, label, subtitle in NURSERY_LOCATIONS:
        # QR links to the observe page for this location
        url = f"{base_url}{loc_id}-observe.html"
        output_path = output_dir / f"{loc_id}.png"
        img = generate_qr(url, label, output_path, subtitle)
        qr_images.append((label, img))
        print(f"  {loc_id} → {output_path}")

    print(f"\n{len(NURSERY_LOCATIONS)} individual QR codes in {output_dir}")

    print(f"\nGenerating A4 print sheets (8 per page)...")
    sheets = generate_a4_sheets(qr_images, output_dir)
    print(f"\n{len(sheets)} nursery print sheets ready at 300 DPI")


if __name__ == "__main__":
    main()
