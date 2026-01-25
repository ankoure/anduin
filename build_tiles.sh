#!/bin/bash
set -e

REGION_URL="https://download.geofabrik.de/north-america/us/massachusetts-latest.osm.pbf"
DATA_DIR="data"
OSM_FILE="$DATA_DIR/osm/massachusetts-latest.osm.pbf"
TILE_DIR="$DATA_DIR/valhalla_tiles"
TILE_EXTRACT="$DATA_DIR/valhalla_tiles.tar"
CONFIG_FILE="$DATA_DIR/valhalla.json"

echo "=== Valhalla Tile Builder ==="

# Ensure data directories exist
mkdir -p "$DATA_DIR/osm"

# Download OSM data if not present
if [ -f "$OSM_FILE" ]; then
    echo "OSM file already exists, skipping download"
else
    echo "Downloading OSM data..."
    wget -q --show-progress -O "$OSM_FILE" "$REGION_URL"
fi

# Generate config
echo "Generating Valhalla config..."
docker run --rm -v "$PWD:/data" valhalla/valhalla:run-latest \
    valhalla_build_config \
    --mjolnir-tile-dir /data/$TILE_DIR \
    --mjolnir-tile-extract /data/$TILE_EXTRACT > "$CONFIG_FILE"

# Build tiles
echo "Building tiles (this may take a while)..."
docker run --rm -v "$PWD:/data" valhalla/valhalla:run-latest \
    valhalla_build_tiles -c /data/$CONFIG_FILE /data/$OSM_FILE

# Create tar extract
echo "Creating tile extract..."
docker run --rm -v "$PWD:/data" valhalla/valhalla:run-latest \
    valhalla_build_extract -c /data/$CONFIG_FILE -v

echo "=== Done! ==="
echo "Tile extract created: $TILE_EXTRACT"
echo "You can now run: uv run anduin"
