"""Entry point for running anduin as a module: python -m anduin"""

import argparse
import logging
from collections import Counter

from anduin.gtfs import GTFSBundleManager, GTFSShapeLoader
from anduin.gtfs.constants import ROUTE_TYPE_NAMES
from anduin.matching import ValhallaMapMatcher, StopEdgeLookup
from anduin.analysis import SharedSegmentAnalyzer, OSMWayExtractor

logger = logging.getLogger(__name__)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="GTFS route matching and analysis tool"
    )
    parser.add_argument(
        "--route-types",
        type=str,
        default="3",
        help="Comma-separated list of GTFS route types to process (default: 3 for buses). "
        "Valid types: 0=Tram, 1=Subway, 2=Rail, 3=Bus, 4=Ferry",
    )
    args = parser.parse_args()

    # Parse route types
    try:
        route_types = [int(t.strip()) for t in args.route_types.split(",")]
        # Validate route types
        for rt in route_types:
            if rt not in [0, 1, 2, 3, 4]:
                print(f"Error: Invalid route type {rt}. Valid types are 0-4.")
                return
    except ValueError:
        print(f"Error: Could not parse route types from '{args.route_types}'")
        return

    # 1. Download and extract GTFS data
    print("Downloading GTFS bundle...")
    manager = GTFSBundleManager()
    manager.download_and_extract()
    print(f"Extracted to: {manager.extract_dir}")

    # 2. Load shapes with route information
    print(f"\nLoading shapes for route types: {route_types}")
    print(
        f"  Route type names: {', '.join(ROUTE_TYPE_NAMES.get(rt, 'Unknown') for rt in route_types)}"
    )
    print("  Excluding shuttle routes by default")
    loader = GTFSShapeLoader(manager.extract_dir)
    shapes = loader.load(route_types=route_types)
    print(f"Loaded {len(shapes)} shapes")

    # Show route type distribution
    route_type_counts = Counter(
        route.route_type for shape in shapes.values() for route in shape.routes
    )
    if route_type_counts:
        print("Route type distribution:")
        for route_type in sorted(route_type_counts.keys()):
            count = route_type_counts[route_type]
            name = ROUTE_TYPE_NAMES.get(route_type, "Unknown")
            print(f"  {name}: {count} routes")

    # 3. Set up Valhalla map matcher
    print("\nInitializing map matcher...")
    matcher = ValhallaMapMatcher.from_pyvalhalla(
        tile_extract="data/valhalla_tiles.tar",
        costing="bus",
    )

    # 4. Analyze shared segments across routes
    print("\nAnalyzing shared segments...")
    analyzer = SharedSegmentAnalyzer(matcher)
    analyzer.add_shapes(list(shapes.values()))

    summary = analyzer.summary()
    print(f"  Total segments: {summary['total_segments']}")
    print(f"  Total routes: {summary['total_routes']}")
    print(f"  Segments shared by 2+ routes: {summary['segments_shared_by_2+_routes']}")
    print(f"  Segments shared by 5+ routes: {summary['segments_shared_by_5+_routes']}")

    # Show busiest segments
    print("\nTop 10 busiest segments:")
    for seg in analyzer.get_busiest_segments(10):
        street = ", ".join(seg.names) or "Unnamed"
        routes = ", ".join(seg.route_names[:5])
        if len(seg.route_names) > 5:
            routes += f" (+{len(seg.route_names) - 5} more)"
        print(f"  {street}: {routes}")

    # 5. Build stop-to-stop edge lookup
    print("\nBuilding stop edge lookup...")
    lookup = StopEdgeLookup(manager.extract_dir, matcher)
    lookup.build()

    lookup_summary = lookup.summary()
    print(f"  Total stops: {lookup_summary['total_stops']}")
    print(f"  Total stop pairs: {lookup_summary['total_stop_pairs']}")
    print(f"  Routes with pairs: {lookup_summary['routes_with_pairs']}")

    # 6. Export all routes to GeoJSON
    route_ids = list(analyzer._route_segments.keys())
    if route_ids:
        print(f"\nExporting {len(route_ids)} routes to GeoJSON...")
        for route_id in route_ids:
            geojson = lookup.export_route_geojson(route_id)
            output_path = f"data/route_indexes/route_{route_id}.geojson"
            lookup.save_geojson(geojson, output_path)
            print(f"  Saved: {output_path}")

    # 7. Extract OSM way geometries for all routes
    print("\nExtracting OSM way geometries...")
    osm_extractor = OSMWayExtractor(
        route_indexes_dir="data/route_indexes",
        osm_pbf_path="data/osm/massachusetts-latest.osm.pbf",
    )
    osm_extractor.build()

    osm_summary = osm_extractor.summary()
    print(f"  Total ways extracted: {osm_summary['total_ways']}")
    print(
        f"  Total unique ways referenced: {osm_summary['total_unique_ways_referenced']}"
    )
    print(f"  Total routes: {osm_summary['total_routes']}")
    print(f"  Ways with multiple routes: {osm_summary['ways_with_multiple_routes']}")
    if osm_summary["missing_ways"] > 0:
        print(f"  Warning: {osm_summary['missing_ways']} ways not found in OSM")
    if osm_summary["skipped_ways"] > 0:
        print(
            f"  Warning: {osm_summary['skipped_ways']} ways skipped due to insufficient data"
        )

    # Save OSM ways to GeoJSON
    osm_output_path = "data/osm_ways.geojson"
    osm_extractor.save_geojson(osm_output_path)
    print(f"  Saved: {osm_output_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
