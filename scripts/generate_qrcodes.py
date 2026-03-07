#!/usr/bin/env python3
"""
Generate QR codes for section poles and printable A4 sheets.

Reads sections.json and generates:
1. Individual QR code PNGs (one per section)
2. Printable A4 sheets with 8 QR codes per page (for bulk printing)

Usage:
    python scripts/generate_qrcodes.py --base-url https://agnesfa.github.io/firefly-farm-ai/
"""

import argparse
import json
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


def get_fonts():
    """Get available fonts, with fallbacks."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font_large = None
    font_small = None
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
    """Generate a single QR code PNG with label."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Generate QR as standard PIL image
    img = qr.make_image(fill_color=(45, 80, 22), back_color=(255, 255, 255))
    img = img.convert("RGB")

    qr_size = img.size[0]
    label_height = 60
    combined = Image.new("RGB", (qr_size, qr_size + label_height), "white")
    combined.paste(img, (0, 0))

    font_large, font_small = get_fonts()
    draw = ImageDraw.Draw(combined)

    # Section label centered
    bbox = draw.textbbox((0, 0), label, font=font_large)
    text_w = bbox[2] - bbox[0]
    draw.text(((qr_size - text_w) / 2, qr_size + 5), label, fill=(45, 80, 22), font=font_large)

    # Farm name
    bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
    text_w2 = bbox2[2] - bbox2[0]
    draw.text(((qr_size - text_w2) / 2, qr_size + 35), subtitle, fill=(150, 150, 150), font=font_small)

    combined.save(output_path)
    return combined


def generate_a4_sheets(qr_images, output_dir):
    """Generate A4 print sheets with 8 QR codes per page (2 columns x 4 rows).

    Each QR code is sized to ~4cm x 4cm at 300 DPI for reliable scanning.
    A4 at 300 DPI = 2480 x 3508 pixels.
    """
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

            # Scale QR to fit cell with padding
            qr_w, qr_h = qr_img.size
            scale = min((cell_w - 40) / qr_w, (cell_h - 40) / qr_h)
            new_w = int(qr_w * scale)
            new_h = int(qr_h * scale)
            resized = qr_img.resize((new_w, new_h), Image.LANCZOS)

            # Center in cell
            x = MARGIN + col * cell_w + (cell_w - new_w) // 2
            y = MARGIN + row * cell_h + (cell_h - new_h) // 2
            sheet.paste(resized, (x, y))

        sheet_path = output_dir / f"print_sheet_{page_idx + 1}.png"
        sheet.save(sheet_path, dpi=(300, 300))
        sheet_paths.append(sheet_path)
        print(f"  Print sheet {page_idx + 1}/{pages}: {len(page_items)} QR codes → {sheet_path}")

    return sheet_paths


def main():
    parser = argparse.ArgumentParser(description="Generate QR codes for section poles")
    parser.add_argument("--base-url", required=True,
                        help="Base URL for GitHub Pages")
    parser.add_argument("--data", default="site/src/data/sections.json",
                        help="Path to sections.json")
    parser.add_argument("--output", default="site/public/qrcodes/",
                        help="Output directory for QR images")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/") + "/"
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.data, "r") as f:
        data = json.load(f)

    sections = data.get("sections", {})
    print(f"Generating {len(sections)} QR codes...")

    qr_images = []  # (label, PIL Image) for A4 sheets

    for section_id in sorted(sections.keys()):
        url = f"{base_url}{section_id}.html"
        output_path = output_dir / f"{section_id}.png"
        img = generate_qr(url, section_id, output_path)
        qr_images.append((section_id, img))
        print(f"  {section_id} → {output_path}")

    # Index QR
    index_img = generate_qr(f"{base_url}index.html", "Paddock Guide",
                            output_dir / "index.png")

    print(f"\n{len(sections)} individual QR codes in {output_dir}")

    # Generate A4 print sheets
    print(f"\nGenerating A4 print sheets (8 per page)...")
    sheets = generate_a4_sheets(qr_images, output_dir)
    print(f"\n{len(sheets)} print sheets ready at 300 DPI")
    print(f"Print at actual size for ~4cm QR codes (minimum for reliable scanning)")


if __name__ == "__main__":
    main()
