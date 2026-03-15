# farmOS API Reference

## API Endpoints

farmOS uses JSON:API standard. Base URL: `https://margregen.farmos.net/api`

### Asset Types

| Type | Endpoint | Description |
|------|----------|-------------|
| plant | `/api/asset/plant` | Plant assets (crops, trees) |
| land | `/api/asset/land` | Land areas (paddocks, rows, beds) |
| equipment | `/api/asset/equipment` | Farm equipment |
| structure | `/api/asset/structure` | Buildings, greenhouses |
| water | `/api/asset/water` | Water sources, irrigation |
| compost | `/api/asset/compost` | Compost piles/bins |
| material | `/api/asset/material` | Materials and supplies |
| group | `/api/asset/group` | Asset groupings |
| seed | `/api/asset/seed` | Seed inventory |
| animal | `/api/asset/animal` | Livestock |

### Log Types

| Type | Endpoint | Description |
|------|----------|-------------|
| activity | `/api/log/activity` | General activities |
| observation | `/api/log/observation` | Field observations |
| harvest | `/api/log/harvest` | Harvest records |
| seeding | `/api/log/seeding` | Seeding events |
| transplanting | `/api/log/transplanting` | Transplanting events |
| input | `/api/log/input` | Inputs (fertilizer, amendments) |
| maintenance | `/api/log/maintenance` | Equipment maintenance |
| purchase | `/api/log/purchase` | Purchases |
| sale | `/api/log/sale` | Sales |
| lab_test | `/api/log/lab_test` | Soil/water tests |

### Taxonomy Vocabularies

| Vocabulary | Endpoint | Description |
|------------|----------|-------------|
| plant_type | `/api/taxonomy_term/plant_type` | Crop/plant varieties |
| animal_type | `/api/taxonomy_term/animal_type` | Animal breeds |
| season | `/api/taxonomy_term/season` | Growing seasons |
| unit | `/api/taxonomy_term/unit` | Measurement units |
| log_category | `/api/taxonomy_term/log_category` | Log categories |
| material_type | `/api/taxonomy_term/material_type` | Material categories |
| crop_family | `/api/taxonomy_term/crop_family` | Botanical families |

## Data Structures

### Land Asset
```json
{
  "type": "asset--land",
  "attributes": {
    "name": "P1R1",
    "status": "active",
    "notes": { "value": "Description...", "format": "default" },
    "geometry": {
      "value": "LINESTRING(...)",
      "geo_type": "LineString",
      "lat": -32.069,
      "lon": 152.256
    },
    "land_type": "bed",
    "is_location": true,
    "is_fixed": true
  },
  "relationships": {
    "parent": { "data": [{ "type": "asset--land", "id": "..." }] },
    "location": { "data": [] }
  }
}
```

### Plant Asset
```json
{
  "type": "asset--plant",
  "attributes": {
    "name": "Tomatoes 2026",
    "status": "active",
    "notes": { "value": "...", "format": "default" }
  },
  "relationships": {
    "plant_type": { "data": { "type": "taxonomy_term--plant_type", "id": "..." } },
    "location": { "data": [{ "type": "asset--land", "id": "..." }] }
  }
}
```

### Activity Log
```json
{
  "type": "log--activity",
  "attributes": {
    "name": "Activity description",
    "status": "done",
    "timestamp": "2026-01-12T10:00:00+00:00",
    "notes": { "value": "...", "format": "default" }
  },
  "relationships": {
    "asset": { "data": [{ "type": "asset--land", "id": "..." }] },
    "location": { "data": [{ "type": "asset--land", "id": "..." }] },
    "category": { "data": [{ "type": "taxonomy_term--log_category", "id": "..." }] }
  }
}
```

### Plant Type (Taxonomy Term)
```json
{
  "type": "taxonomy_term--plant_type",
  "attributes": {
    "name": "Tomato (Marmande)",
    "description": {
      "value": "French beefsteak...\n\n---\n**Syntropic Agriculture Data:**\n**Botanical Name:** Solanum lycopersicum\n...",
      "format": "default"
    },
    "maturity_days": null,
    "transplant_days": 42,
    "harvest_days": 85
  },
  "relationships": {
    "crop_family": { "data": { "type": "taxonomy_term--crop_family", "id": "..." } }
  }
}
```

## Python farmOS.py Library

```python
import os
from dotenv import load_dotenv
from farmOS import farmOS

load_dotenv()

# Initialize and authenticate (credentials from .env)
client = farmOS(
    hostname=os.getenv("FARMOS_URL"),
    client_id=os.getenv("FARMOS_CLIENT_ID", "farm"),
    scope=os.getenv("FARMOS_SCOPE", "farm_manager"),
)
client.authorize(
    username=os.getenv("FARMOS_USERNAME"),
    password=os.getenv("FARMOS_PASSWORD"),
)

# Iterate all assets of a type
for asset in client.asset.iterate("land"):
    print(asset["attributes"]["name"])

# Filter assets
params = {"filter[status]": "active", "filter[land_type]": "bed"}
for asset in client.asset.iterate("land", params=params):
    print(asset["attributes"]["name"])

# Create new log
new_log = {
    "attributes": {
        "name": "Planted tomatoes in P2R3.15-21",
        "status": "done",
        "timestamp": "2026-01-12T10:00:00+00:00",
    },
    "relationships": {
        "location": {"data": [{"type": "asset--land", "id": "uuid-here"}]},
    },
}
client.log.send("seeding", new_log)

# Create taxonomy term
new_term = {
    "attributes": {
        "name": "New Variety",
        "description": {"value": "Description here", "format": "default"},
    }
}
client.term.send("plant_type", new_term)
```

## Filtering & Pagination

```python
# Filter by status
params = {"filter[status]": "active"}

# Filter by name (contains)
params = {"filter[name][operator]": "CONTAINS", "filter[name][value]": "P1"}

# Filter by date
params = {"filter[timestamp][operator]": ">=", "filter[timestamp][value]": "2026-01-01"}

# Include related resources
params = {"include": "asset,location,category"}

# iterate() handles pagination automatically
```

## References

- farmOS API documentation: https://farmos.org/development/api/
- farmOS.py library: https://github.com/farmOS/farmOS.py
- JSON:API specification: https://jsonapi.org/
