# Anduin

A GTFS transit data processing and map matching tool for analyzing public transit routes and infrastructure. Anduin matches transit route shapes to OpenStreetMap road networks using the Valhalla routing engine, enabling analysis of route overlaps, shared segments, and infrastructure utilization.

## Features

- **GTFS Data Processing**: Download, extract, and parse GTFS feeds (default: MBTA)
- **Map Matching**: Match transit route shapes to OSM road networks using Valhalla
- **Shared Segment Analysis**: Identify road segments used by multiple transit routes
- **OSM Validation**: Cross-reference matched routes against OSM bus route relations
- **Stop-to-Stop Analysis**: Compute edges between consecutive stops with validation
- **GeoJSON Export**: Export route and way geometries for visualization

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager (recommended)
- Docker (for building Valhalla tiles)

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/ankoure/anduin.git
   cd anduin
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Build Valhalla routing tiles (one-time setup):

   ```bash
   bash build_tiles.sh
   ```

   This downloads Massachusetts OSM data and builds routing tiles using Docker.

## Usage

Run the main pipeline:

```bash
uv run anduin
```

### Options

Filter by route type using `--route-types`:

| Code | Type            |
| ---- | --------------- |
| 0    | Tram/Light Rail |
| 1    | Subway/Metro    |
| 2    | Rail            |
| 3    | Bus             |
| 4    | Ferry           |

```bash
# Process bus routes only (default)
uv run anduin --route-types 3

# Process subway and bus routes
uv run anduin --route-types 1,3

# Process all route types
uv run anduin --route-types 0,1,2,3,4
```

### Output

The pipeline generates:

- `data/route_indexes/route_*.geojson` - Individual route geometries
- `data/osm_ways.geojson` - OSM way geometries with route metadata

## Project Structure

```text
src/anduin/
├── gtfs/           # GTFS data loading and parsing
│   ├── bundle.py   # Download and extract GTFS bundles
│   ├── shapes.py   # Shape and route parsing
│   ├── stops.py    # Stop and trip sequence loading
│   └── constants.py
├── matching/       # Map matching
│   ├── valhalla.py # Valhalla map matcher
│   └── edges.py    # Stop-to-stop edge lookup
└── analysis/       # Route analysis
    ├── segments.py     # Shared segment analysis
    ├── osm_routes.py   # OSM bus route indexing
    └── osm_extract.py  # OSM way geometry extraction
```

## Development

Install development dependencies:

```bash
uv sync --all-extras
```

Run tests:

```bash
pytest
```

Run linter:

```bash
ruff check src/
```

Build documentation:

```bash
cd docs && make html
```

## License

[Add license information]

## Contributing

[Add contribution guidelines]
