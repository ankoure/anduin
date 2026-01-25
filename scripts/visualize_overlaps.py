#!/usr/bin/env python3
"""Visualize overlaps in route index GeoJSON files."""

import json
from pathlib import Path
from collections import defaultdict
import folium


def load_ways(ways_file: Path) -> list[dict]:
    """Load OSM ways GeoJSON file."""
    if not ways_file.exists():
        print(f"OSM ways file not found: {ways_file}")
        return []

    with open(ways_file) as f:
        data = json.load(f)
        return data.get("features", [])


def create_folium_map(ways: list[dict], output_path: Path) -> None:
    """Create an interactive Folium map showing route overlaps."""

    # Find center point from all coordinates
    all_coords = []
    for feature in ways:
        coords = feature.get("geometry", {}).get("coordinates", [])
        # Coordinates are [lon, lat] pairs
        for coord in coords:
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                all_coords.append(coord)

    if not all_coords:
        print("No coordinates found")
        return

    center_lon = sum(c[0] for c in all_coords) / len(all_coords)
    center_lat = sum(c[1] for c in all_coords) / len(all_coords)

    # Create map
    m = folium.Map(
        location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB positron"
    )

    # Track ways by overlap count for visualization
    overlap_features = defaultdict(list)

    for feature in ways:
        coords = feature.get("geometry", {}).get("coordinates", [])
        way_id = feature.get("properties", {}).get("way_id", "")
        routes = feature.get("properties", {}).get("routes", [])
        overlap_count = len(routes)

        if coords:
            # Convert to lat/lon format for folium, filtering valid coords
            latlon_coords = [
                [c[1], c[0]]
                for c in coords
                if isinstance(c, (list, tuple)) and len(c) >= 2
            ]
            if not latlon_coords:
                continue
            overlap_features[overlap_count].append(
                {
                    "coords": latlon_coords,
                    "way_id": way_id,
                    "routes": routes,
                }
            )

    # Add ways to map, with higher overlaps on top
    for overlap_count in sorted(overlap_features.keys()):
        for way in overlap_features[overlap_count]:
            # Color based on overlap: green (1) -> yellow (2-3) -> red (4+)
            if overlap_count == 1:
                color = "#22cc22"  # Green - no overlap
                weight = 2
            elif overlap_count <= 3:
                color = "#ffcc00"  # Yellow - some overlap
                weight = 3
            else:
                color = "#ff3333"  # Red - high overlap
                weight = 4

            popup_text = (
                f"<b>Way ID:</b> {way['way_id']}<br>"
                f"<b>Routes:</b> {', '.join(sorted(way['routes']))}<br>"
                f"<b>Overlap count:</b> {overlap_count}"
            )

            folium.PolyLine(
                way["coords"],
                color=color,
                weight=weight,
                opacity=0.7,
                popup=folium.Popup(popup_text, max_width=300),
            ).add_to(m)

    # Add legend
    legend_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000;
                background-color: white; padding: 10px; border-radius: 5px;
                border: 2px solid gray; font-family: Arial;">
        <p style="margin: 0 0 5px 0;"><b>Overlap Legend</b></p>
        <p style="margin: 2px 0;"><span style="color: #22cc22;">&#9632;</span> No overlap (1 route)</p>
        <p style="margin: 2px 0;"><span style="color: #ffcc00;">&#9632;</span> Some overlap (2-3 routes)</p>
        <p style="margin: 2px 0;"><span style="color: #ff3333;">&#9632;</span> High overlap (4+ routes)</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save map
    m.save(str(output_path))
    print(f"Map saved to: {output_path}")


def print_overlap_stats(ways: list[dict]) -> None:
    """Print statistics about route overlaps."""
    # Count overlaps
    overlap_counts = defaultdict(int)
    highly_overlapped = []

    for feature in ways:
        routes = feature.get("properties", {}).get("routes", [])
        way_id = feature.get("properties", {}).get("way_id", "")
        overlap_count = len(routes)
        overlap_counts[overlap_count] += 1

        if overlap_count >= 5:
            highly_overlapped.append((way_id, routes))

    highly_overlapped.sort(key=lambda x: len(x[1]), reverse=True)

    print("\n=== Way ID Overlap Statistics ===")
    print(f"Total unique ways: {len(ways)}")
    print("\nOverlap distribution:")
    for count in sorted(overlap_counts.keys()):
        print(f"  {count} route(s): {overlap_counts[count]} ways")

    # Find most overlapped ways
    print("\nMost overlapped ways (shared by 5+ routes):")
    for way_id, routes in highly_overlapped[:20]:
        print(f"  Way {way_id}: {len(routes)} routes - {', '.join(sorted(routes))}")


def main():
    ways_file = Path(__file__).parent.parent / "data" / "osm_ways.geojson"

    print(f"Loading ways from: {ways_file}")
    ways = load_ways(ways_file)

    if not ways:
        print("No ways loaded")
        return

    print(f"Loaded {len(ways)} ways")

    # Print statistics
    print_overlap_stats(ways)

    # Create interactive map
    output_path = Path(__file__).parent.parent / "route_overlaps.html"
    create_folium_map(ways, output_path)

    print(f"\nOpen {output_path} in a browser to view the interactive map!")


if __name__ == "__main__":
    main()
