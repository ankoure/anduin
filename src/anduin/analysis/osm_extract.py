"""OSM way geometry extraction and route mapping."""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import osmium

logger = logging.getLogger(__name__)


@dataclass
class WayGeometry:
    """Represents an OSM way with its geometry and associated routes.

    :ivar way_id: The OSM way ID.
    :ivar routes: List of route IDs that use this way.
    :ivar coordinates: List of (lon, lat) tuples representing the way geometry.
    :ivar tags: Dictionary of OSM tags (name, highway type, etc.).
    """

    way_id: int
    routes: list[str] = field(default_factory=list)
    coordinates: list[tuple[float, float]] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


class _WayHandler(osmium.SimpleHandler):
    """Custom osmium handler to extract ways with their geometries."""

    def __init__(self, way_ids_to_extract: set[int], ways_dict: dict[int, WayGeometry]):
        """Initialize the handler.

        :param way_ids_to_extract: Set of way IDs to extract from the OSM file.
        :param ways_dict: Dictionary to store extracted WayGeometry objects.
        """
        super().__init__()
        self.way_ids_to_extract = way_ids_to_extract
        self.ways_dict = ways_dict
        self.missing_ways: set[int] = set()
        self.skipped_ways: set[int] = set()

    def way(self, w) -> None:
        """Process a way from the OSM file.

        :param w: The osmium Way object.
        """
        if w.id not in self.way_ids_to_extract:
            return

        # Skip ways with insufficient nodes for a LineString
        if len(w.nodes) < 2:
            self.skipped_ways.add(w.id)
            logger.warning(f"Skipping way {w.id}: insufficient nodes ({len(w.nodes)})")
            return

        try:
            # Extract coordinates from nodes
            coordinates = []
            for node in w.nodes:
                if node.lat is None or node.lon is None:
                    # This shouldn't happen with locations=True, but handle gracefully
                    logger.warning(f"Way {w.id}: node {node.ref} has missing location")
                    self.skipped_ways.add(w.id)
                    return
                coordinates.append((node.lon, node.lat))

            # Extract OSM tags
            tags = dict(w.tags)

            # Create WayGeometry object
            way_geometry = WayGeometry(
                way_id=w.id,
                coordinates=coordinates,
                tags=tags,
            )
            self.ways_dict[w.id] = way_geometry

        except Exception as e:
            logger.error(f"Error processing way {w.id}: {e}")
            self.skipped_ways.add(w.id)


class OSMWayExtractor:
    """Extracts OSM way geometries for transit routes.

    This class reads route index GeoJSON files to identify which OSM ways
    are used by each route, then extracts the geometries for those ways
    from an OSM PBF file. The result is a mapping of OSM ways to the
    routes that use them, with full LineString geometries.

    The output can be used for route overlap analysis, visualization,
    and understanding shared infrastructure across routes.

    Example:
        >>> extractor = OSMWayExtractor(
        ...     route_indexes_dir="data/route_indexes",
        ...     osm_pbf_path="data/osm/massachusetts-latest.osm.pbf"
        ... )
        >>> extractor.build()
        >>> geojson = extractor.to_geojson()
        >>> extractor.save_geojson("output.geojson")
    """

    def __init__(self, route_indexes_dir: str | Path, osm_pbf_path: str | Path):
        """Initialize the extractor.

        :param route_indexes_dir: Directory containing route_*.geojson files.
        :param osm_pbf_path: Path to OSM PBF file (e.g., massachusetts-latest.osm.pbf).
        """
        self.route_indexes_dir = Path(route_indexes_dir)
        self.osm_pbf_path = Path(osm_pbf_path)

        # way_id -> WayGeometry
        self._ways: dict[int, WayGeometry] = {}
        # way_id -> set of route_ids
        self._way_to_routes: dict[int, set[str]] = defaultdict(set)

        # Statistics
        self._missing_ways: set[int] = set()
        self._skipped_ways: set[int] = set()

    def load_route_way_mappings(self) -> None:
        """Load all route GeoJSON files and build way_id -> routes mapping.

        Iterates through all route_*.geojson files in the route_indexes_dir,
        extracts way_ids from feature properties, and builds a mapping of
        which routes use each way.
        """
        route_files = sorted(self.route_indexes_dir.glob("route_*.geojson"))

        if not route_files:
            logger.warning(f"No route GeoJSON files found in {self.route_indexes_dir}")
            return

        logger.info(f"Loading route way mappings from {len(route_files)} files")

        for route_file in route_files:
            try:
                # Extract route ID from filename: route_1.geojson -> "1"
                route_id = route_file.stem.replace("route_", "")

                with open(route_file) as f:
                    geojson = json.load(f)

                # Process each feature in the FeatureCollection
                for feature in geojson.get("features", []):
                    properties = feature.get("properties", {})
                    way_ids = properties.get("way_ids", [])

                    # Add this route to each way it uses
                    for way_id in way_ids:
                        self._way_to_routes[way_id].add(route_id)

            except Exception as e:
                logger.error(f"Error loading route file {route_file}: {e}")

        logger.info(f"Loaded {len(self._way_to_routes)} unique ways from routes")

    def extract_way_geometries(self) -> None:
        """Extract geometries from OSM PBF for needed way IDs using pyosmium.

        Uses a custom osmium handler to perform a single-pass extraction
        of way geometries from the OSM PBF file, only including ways that
        are referenced in the route index files.
        """
        if not self._way_to_routes:
            logger.warning(
                "No ways to extract (load_route_way_mappings not called or found no ways)"
            )
            return

        way_ids_to_extract = set(self._way_to_routes.keys())
        logger.info(
            f"Extracting geometries for {len(way_ids_to_extract)} ways from OSM PBF"
        )

        try:
            # Create handler and apply to PBF file
            handler = _WayHandler(way_ids_to_extract, self._ways)
            handler.apply_file(str(self.osm_pbf_path), locations=True)

            # Track missing and skipped ways
            self._missing_ways = way_ids_to_extract - set(self._ways.keys())
            self._skipped_ways = handler.skipped_ways

            if self._missing_ways:
                logger.warning(f"Missing {len(self._missing_ways)} ways from OSM PBF")

            if self._skipped_ways:
                logger.warning(
                    f"Skipped {len(self._skipped_ways)} ways due to insufficient data"
                )

            # Populate routes for each way
            for way_id, routes in self._way_to_routes.items():
                if way_id in self._ways:
                    self._ways[way_id].routes = sorted(list(routes))

            logger.info(f"Successfully extracted {len(self._ways)} ways")

        except Exception as e:
            logger.error(f"Error extracting ways from OSM PBF: {e}")
            raise

    def build(self) -> None:
        """Execute the full pipeline: load routes, then extract geometries."""
        self.load_route_way_mappings()
        self.extract_way_geometries()

    def get_way(self, way_id: int) -> WayGeometry | None:
        """Get geometry and route info for a specific way.

        :param way_id: The OSM way ID to retrieve.
        :returns: WayGeometry object if found, None otherwise.
        """
        return self._ways.get(way_id)

    def get_ways_for_route(self, route_id: str) -> list[WayGeometry]:
        """Get all ways used by a specific route.

        :param route_id: The route ID to query.
        :returns: List of WayGeometry objects for the given route.
        """
        return [
            self._ways[way_id]
            for way_id in self._way_to_routes
            if route_id in self._ways[way_id].routes
        ]

    def to_geojson(self) -> dict:
        """Export as GeoJSON FeatureCollection.

        Returns a GeoJSON FeatureCollection where each feature represents
        an OSM way with its geometry and the list of routes that use it.

        :returns: GeoJSON dict with the following structure::

            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "way_id": int,
                            "routes": [str, ...],
                            "tags": {str: str, ...}
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[lon, lat], ...]
                        }
                    },
                    ...
                ]
            }
        """
        features = []

        for way in self._ways.values():
            feature = {
                "type": "Feature",
                "properties": {
                    "way_id": way.way_id,
                    "routes": way.routes,
                    "tags": way.tags,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": way.coordinates,
                },
            }
            features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def save_geojson(self, output_path: str | Path) -> None:
        """Save GeoJSON to file.

        :param output_path: Path where the GeoJSON file should be written.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        geojson = self.to_geojson()

        with open(output_path, "w") as f:
            json.dump(geojson, f, indent=2)

        logger.info(
            f"Saved GeoJSON with {len(geojson['features'])} ways to {output_path}"
        )

    def summary(self) -> dict:
        """Get summary statistics about extracted ways and routes.

        :returns: Dictionary with statistics including total ways, routes, and
            information about missing or skipped ways.
        """
        all_routes = set()
        for routes in self._way_to_routes.values():
            all_routes.update(routes)

        ways_with_multiple_routes = sum(
            1 for routes in self._way_to_routes.values() if len(routes) > 1
        )

        return {
            "total_ways": len(self._ways),
            "total_unique_ways_referenced": len(self._way_to_routes),
            "total_routes": len(all_routes),
            "missing_ways": len(self._missing_ways),
            "skipped_ways": len(self._skipped_ways),
            "ways_with_multiple_routes": ways_with_multiple_routes,
        }
