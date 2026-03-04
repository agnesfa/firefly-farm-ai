#!/usr/bin/env python3
"""
Generate QR codes for section poles.

Reads sections.json and generates one QR code image per section,
pointing to the corresponding GitHub Pages URL.

Usage:
    python scripts/generate_qrcodes.py --base-url https://yourusername.github.io/firefly-farm-ai/
"""

import argparse
import json
from pathlib import Path

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.colormasks import SolidFillColorMask
except ImportError:
    print("Install qrcode: pip install qrcode[pil]")
    exit(1)


def generate_qr(url, label, output_path):
    """Generate a single QR code with a label."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Forest green on white
    img = qr.make_image(
        image_factory=StyledPilImage,
        color_mask=SolidFillColorMask(
            back_color=(255, 255, 255),
            front_color=(45, 80, 22),  # #2d5016
        ),
    )
    
    # Add label text below
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        qr_size = img.size[0]
        label_height = 60
        combined = Image.new("RGB", (qr_size, qr_size + label_height), "white")
        combined.paste(img, (0, 0))
        
        draw = ImageDraw.Draw(combined)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except OSError:
            font = ImageFont.load_default()
            font_small = font
        
        # Section label centered
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(((qr_size - text_w) / 2, qr_size + 5), label, fill=(45, 80, 22), font=font)
        
        # Farm name
        subtitle = "Firefly Corner Farm"
        bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
        text_w2 = bbox2[2] - bbox2[0]
        draw.text(((qr_size - text_w2) / 2, qr_size + 35), subtitle, fill=(150, 150, 150), font=font_small)
        
        combined.save(output_path)
    except ImportError:
        # No PIL text support, just save the QR
        img.save(output_path)
    
    print(f"  {label} → {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate QR codes for section poles")
    parser.add_argument("--base-url", required=True, help="Base URL for GitHub Pages (e.g., https://user.github.io/firefly-farm-ai/)")
    parser.add_argument("--data", default="site/src/data/sections.json", help="Path to sections.json")
    parser.add_argument("--output", default="site/public/qrcodes/", help="Output directory for QR images")
    args = parser.parse_args()
    
    base_url = args.base_url.rstrip("/") + "/"
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(args.data, "r") as f:
        data = json.load(f)
    
    sections = data.get("sections", {})
    print(f"Generating {len(sections)} QR codes...")
    
    for section_id in sorted(sections.keys()):
        url = f"{base_url}{section_id}.html"
        section = sections[section_id]
        label = f"{section_id}"
        output_path = output_dir / f"{section_id}.png"
        generate_qr(url, label, output_path)
    
    # Also generate index QR
    generate_qr(f"{base_url}index.html", "Paddock Guide", output_dir / "index.png")
    
    print(f"\nDone! {len(sections) + 1} QR codes in {output_dir}")
    print(f"Print at minimum 3cm × 3cm for reliable scanning.")


if __name__ == "__main__":
    main()
