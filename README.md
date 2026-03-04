# Firefly Corner Farm — AI + farmOS

AI-assisted farm management for a 25-hectare syntropic agroforestry operation in Krambach, NSW.

## What's Here

- **`site/`** — Public QR code landing pages for farm visitors ([live site →](#))
- **`scripts/`** — Data pipeline: farmOS export → site generation → QR codes
- **`mcp-server/`** — farmOS MCP server for AI integration (coming soon)
- **`knowledge/`** — Plant database and syntropic agriculture reference data
- **`skills/`** — Claude Skills for farm management tasks

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Generate the public site from farm data
python scripts/generate_site.py

# Generate QR codes for field poles
python scripts/generate_qrcodes.py --base-url https://your-github-pages-url
```

## About Firefly Corner

Firefly Corner practices syntropic agroforestry — building productive food forests by mimicking natural forest ecosystems. Each row is a polyculture designed with layered plant strata (emergent canopy, high canopy, medium, ground cover) and managed through succession stages (pioneer → secondary → climax).

The farm uses [farmOS](https://farmos.org/) for data management and Claude AI for operational assistance.

## Architecture

See [CLAUDE.md](CLAUDE.md) for full project context and conventions.

---

*Firefly Corner Farm · Krambach, NSW · Syntropic Agroforestry*
