import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict

from anduin.gtfs.shapes import Shape, ShapePoint, RouteInfo
from anduin.gtfs.stops import Stop, TripStopSequence, load_stops
from anduin.gtfs.constants import EXCLUDED_ROUTE_NAME_PREFIXES
from anduin.matching.valhalla import ValhallaMapMatcher, MapMatchResult, MatchedEdge


@dataclass
class StopPairEdges:
    """Edges connecting a pair of stops."""

    from_stop_id: str
    to_stop_id: str
    edges: list[MatchedEdge] = field(default_factory=list)
    way_ids: list[int] = field(default_factory=list)
    total_length: float = 0.0
    geometry: list[tuple[float, float]] = field(
        default_factory=list
    )  # [(lat, lon), ...]

    @property
    def edge_ids(self) -> list[int]:
        return [e.edge_id for e in self.edges]


class StopEdgeLookup:
    """Builds a lookup of edges between stop pairs along routes."""

    def __init__(self, gtfs_dir: str | Path, matcher: ValhallaMapMatcher):
        """
        Initialize the lookup builder.

        :param gtfs_dir: Path to extracted GTFS directory.
        :param matcher: A configured ValhallaMapMatcher instance.
        """
        self.gtfs_dir = Path(gtfs_dir)
        self.matcher = matcher

        self._stops: dict[str, Stop] = {}
        self._routes: dict[str, RouteInfo] = {}
        # (from_stop_id, to_stop_id, route_id) -> StopPairEdges
        self._stop_pair_edges: dict[tuple[str, str, str], StopPairEdges] = {}
        # route_id -> list of (from_stop_id, to_stop_id) in order
        self._route_stop_pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def _load_routes(self) -> dict[str, RouteInfo]:
        """Load routes.txt into a dict keyed by route_id."""
        routes: dict[str, RouteInfo] = {}
        routes_file = self.gtfs_dir / "routes.txt"

        with open(routes_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route = RouteInfo(
                    route_id=row["route_id"],
                    route_short_name=row.get("route_short_name", ""),
                    route_long_name=row.get("route_long_name", ""),
                    route_type=int(row.get("route_type", 0)),
                    route_color=row.get("route_color", ""),
                    route_text_color=row.get("route_text_color", ""),
                )
                routes[route.route_id] = route

        return routes

    def _should_exclude_route(self, route: RouteInfo) -> bool:
        """
        Check if a route should be excluded based on name or ID prefixes.

        :param route: RouteInfo object to check.
        :returns: True if the route should be excluded, False otherwise.
        """
        for prefix in EXCLUDED_ROUTE_NAME_PREFIXES:
            if (
                route.route_id.startswith(prefix)
                or route.route_short_name.startswith(prefix)
                or route.route_long_name.startswith(prefix)
            ):
                return True
        return False

    def _load_shapes(self) -> dict[str, list[ShapePoint]]:
        """Load shapes.txt."""
        shapes: dict[str, list[ShapePoint]] = {}
        shapes_file = self.gtfs_dir / "shapes.txt"

        with open(shapes_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                shape_id = row["shape_id"]
                point = ShapePoint(
                    lat=float(row["shape_pt_lat"]),
                    lon=float(row["shape_pt_lon"]),
                    sequence=int(row["shape_pt_sequence"]),
                    dist_traveled=float(row["shape_dist_traveled"])
                    if row.get("shape_dist_traveled")
                    else None,
                )
                if shape_id not in shapes:
                    shapes[shape_id] = []
                shapes[shape_id].append(point)

        for shape_id in shapes:
            shapes[shape_id].sort(key=lambda p: p.sequence)

        return shapes

    def _load_trip_stop_sequences(self) -> dict[str, TripStopSequence]:
        """Load trips and stop_times to build stop sequences per trip."""
        # First load trips to get route_id and shape_id
        trips: dict[str, TripStopSequence] = {}
        trips_file = self.gtfs_dir / "trips.txt"

        with open(trips_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip_id = row["trip_id"]
                trips[trip_id] = TripStopSequence(
                    trip_id=trip_id,
                    route_id=row["route_id"],
                    shape_id=row.get("shape_id", ""),
                )

        # Load stop_times to get ordered stops per trip
        stop_times_file = self.gtfs_dir / "stop_times.txt"

        with open(stop_times_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip_id = row["trip_id"]
                if trip_id not in trips:
                    continue

                stop_id = row["stop_id"]
                sequence = int(row["stop_sequence"])
                stop = self._stops.get(stop_id)

                if stop:
                    trips[trip_id].stops.append((sequence, stop))

        # Sort stops by sequence
        for trip in trips.values():
            trip.stops.sort(key=lambda x: x[0])

        return trips

    def _find_shape_segment(
        self,
        shape_points: list[ShapePoint],
        from_stop: Stop,
        to_stop: Stop,
    ) -> list[ShapePoint]:
        """Extract shape points between two stops."""

        def distance_sq(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2

        # Find closest shape point to from_stop
        from_idx = min(
            range(len(shape_points)),
            key=lambda i: distance_sq(
                shape_points[i].lat, shape_points[i].lon, from_stop.lat, from_stop.lon
            ),
        )

        # Find closest shape point to to_stop (must be after from_idx)
        to_idx = min(
            range(from_idx, len(shape_points)),
            key=lambda i: distance_sq(
                shape_points[i].lat, shape_points[i].lon, to_stop.lat, to_stop.lon
            ),
        )

        # Include the stop locations at start and end for better matching
        segment = [ShapePoint(lat=from_stop.lat, lon=from_stop.lon, sequence=-1)]
        segment.extend(shape_points[from_idx : to_idx + 1])
        segment.append(ShapePoint(lat=to_stop.lat, lon=to_stop.lon, sequence=999999))

        return segment

    def _match_segment(self, points: list[ShapePoint]) -> MapMatchResult:
        """Map match a segment of shape points."""
        shape = Shape(shape_id="segment", points=points)
        return self.matcher.match_shape(shape)

    def build(self) -> None:
        """Build the stop pair edge lookup from GTFS data."""
        self._stops = load_stops(self.gtfs_dir)
        self._routes = self._load_routes()
        shapes = self._load_shapes()
        trip_sequences = self._load_trip_stop_sequences()

        # Group trips by (route_id, shape_id) to avoid redundant matching
        route_shape_trips: dict[tuple[str, str], TripStopSequence] = {}
        for trip in trip_sequences.values():
            key = (trip.route_id, trip.shape_id)
            if key not in route_shape_trips and trip.shape_id:
                route_shape_trips[key] = trip

        # Process each unique route/shape combination
        for (route_id, shape_id), trip in route_shape_trips.items():
            # Skip excluded routes (e.g., shuttle routes)
            route = self._routes.get(route_id)
            if route and self._should_exclude_route(route):
                continue
            if shape_id not in shapes:
                continue

            shape_points = shapes[shape_id]
            stops = [stop for _, stop in trip.stops]

            # Process consecutive stop pairs
            for i in range(len(stops) - 1):
                from_stop = stops[i]
                to_stop = stops[i + 1]

                key = (from_stop.stop_id, to_stop.stop_id, route_id)
                if key in self._stop_pair_edges:
                    continue

                # Extract and match the segment
                segment_points = self._find_shape_segment(
                    shape_points, from_stop, to_stop
                )

                if len(segment_points) < 2:
                    continue

                try:
                    result = self._match_segment(segment_points)
                except RuntimeError:
                    continue

                # Build the stop pair edges
                way_ids = []
                seen_ways = set()
                for edge in result.edges:
                    if edge.way_id not in seen_ways:
                        seen_ways.add(edge.way_id)
                        way_ids.append(edge.way_id)

                total_length = sum(e.length for e in result.edges)

                # Extract matched geometry
                geometry = [(mp.lat, mp.lon) for mp in result.matched_points]

                self._stop_pair_edges[key] = StopPairEdges(
                    from_stop_id=from_stop.stop_id,
                    to_stop_id=to_stop.stop_id,
                    edges=result.edges,
                    way_ids=way_ids,
                    total_length=total_length,
                    geometry=geometry,
                )

                # Track route stop pairs
                pair = (from_stop.stop_id, to_stop.stop_id)
                if pair not in self._route_stop_pairs[route_id]:
                    self._route_stop_pairs[route_id].append(pair)

    def get_edges_between_stops(
        self,
        from_stop_id: str,
        to_stop_id: str,
        route_id: str | None = None,
    ) -> StopPairEdges | None:
        """
        Get the edges between two stops.

        :param from_stop_id: Origin stop ID.
        :param to_stop_id: Destination stop ID.
        :param route_id: Specific route, or None to find any route.
        :returns: StopPairEdges or None if not found.
        """
        if route_id:
            return self._stop_pair_edges.get((from_stop_id, to_stop_id, route_id))

        # Search all routes
        for key, edges in self._stop_pair_edges.items():
            if key[0] == from_stop_id and key[1] == to_stop_id:
                return edges

        return None

    def get_edges_for_stop_sequence(
        self,
        stop_ids: list[str],
        route_id: str,
    ) -> list[StopPairEdges]:
        """
        Get edges for a sequence of stops (e.g., a trip segment).

        :param stop_ids: Ordered list of stop IDs.
        :param route_id: The route ID.
        :returns: List of StopPairEdges for each consecutive pair.
        """
        result = []
        for i in range(len(stop_ids) - 1):
            edges = self.get_edges_between_stops(stop_ids[i], stop_ids[i + 1], route_id)
            if edges:
                result.append(edges)
        return result

    def get_way_ids_between_stops(
        self,
        from_stop_id: str,
        to_stop_id: str,
        route_id: str | None = None,
    ) -> list[int]:
        """Get just the OSM way IDs between two stops."""
        edges = self.get_edges_between_stops(from_stop_id, to_stop_id, route_id)
        return edges.way_ids if edges else []

    def get_stop(self, stop_id: str) -> Stop | None:
        """Get a stop by ID."""
        return self._stops.get(stop_id)

    def get_route_stop_pairs(self, route_id: str) -> list[tuple[str, str]]:
        """Get all consecutive stop pairs for a route."""
        return self._route_stop_pairs.get(route_id, [])

    def get_all_edges_for_route(self, route_id: str) -> list[MatchedEdge]:
        """Get all unique edges used by a route in order."""
        edges = []
        seen_edge_ids = set()

        for from_stop, to_stop in self._route_stop_pairs.get(route_id, []):
            pair_edges = self.get_edges_between_stops(from_stop, to_stop, route_id)
            if pair_edges:
                for edge in pair_edges.edges:
                    if edge.edge_id not in seen_edge_ids:
                        seen_edge_ids.add(edge.edge_id)
                        edges.append(edge)

        return edges

    def summary(self) -> dict:
        """Get summary statistics."""
        return {
            "total_stops": len(self._stops),
            "total_stop_pairs": len(self._stop_pair_edges),
            "routes_with_pairs": len(self._route_stop_pairs),
        }

    def stop_pair_to_geojson_feature(
        self,
        stop_pair: StopPairEdges,
        route_id: str | None = None,
    ) -> dict:
        """
        Convert a stop pair to a GeoJSON Feature.

        :param stop_pair: The StopPairEdges to convert.
        :param route_id: Optional route ID to include in properties.
        :returns: GeoJSON Feature dict with LineString geometry.
        """
        from_stop = self._stops.get(stop_pair.from_stop_id)
        to_stop = self._stops.get(stop_pair.to_stop_id)

        # GeoJSON uses [lon, lat] order
        coordinates = [[lon, lat] for lat, lon in stop_pair.geometry]

        return {
            "type": "Feature",
            "properties": {
                "from_stop_id": stop_pair.from_stop_id,
                "to_stop_id": stop_pair.to_stop_id,
                "from_stop_name": from_stop.stop_name if from_stop else "",
                "to_stop_name": to_stop.stop_name if to_stop else "",
                "route_id": route_id,
                "way_ids": stop_pair.way_ids,
                "edge_count": len(stop_pair.edges),
                "length_meters": stop_pair.total_length,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            }
            if coordinates
            else None,
        }

    def stop_to_geojson_feature(self, stop: Stop) -> dict:
        """
        Convert a stop to a GeoJSON Feature.

        :param stop: The Stop to convert.
        :returns: GeoJSON Feature dict with Point geometry.
        """
        return {
            "type": "Feature",
            "properties": {
                "stop_id": stop.stop_id,
                "stop_name": stop.stop_name,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [stop.lon, stop.lat],
            },
        }

    def export_stop_pair_geojson(
        self,
        from_stop_id: str,
        to_stop_id: str,
        route_id: str,
        include_stops: bool = True,
    ) -> dict:
        """
        Export a single stop pair as a GeoJSON FeatureCollection.

        :param from_stop_id: Origin stop ID.
        :param to_stop_id: Destination stop ID.
        :param route_id: The route ID.
        :param include_stops: Whether to include stop points.
        :returns: GeoJSON FeatureCollection dict.
        """
        features = []

        stop_pair = self.get_edges_between_stops(from_stop_id, to_stop_id, route_id)
        if stop_pair:
            features.append(self.stop_pair_to_geojson_feature(stop_pair, route_id))

        if include_stops:
            from_stop = self._stops.get(from_stop_id)
            to_stop = self._stops.get(to_stop_id)
            if from_stop:
                features.append(self.stop_to_geojson_feature(from_stop))
            if to_stop:
                features.append(self.stop_to_geojson_feature(to_stop))

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def export_route_geojson(
        self,
        route_id: str,
        include_stops: bool = True,
    ) -> dict:
        """
        Export an entire route as a GeoJSON FeatureCollection.

        :param route_id: The route ID to export.
        :param include_stops: Whether to include stop points.
        :returns: GeoJSON FeatureCollection dict.
        """
        features = []
        seen_stops = set()

        for from_stop_id, to_stop_id in self._route_stop_pairs.get(route_id, []):
            stop_pair = self.get_edges_between_stops(from_stop_id, to_stop_id, route_id)
            if stop_pair:
                features.append(self.stop_pair_to_geojson_feature(stop_pair, route_id))

            if include_stops:
                if from_stop_id not in seen_stops:
                    from_stop = self._stops.get(from_stop_id)
                    if from_stop:
                        features.append(self.stop_to_geojson_feature(from_stop))
                    seen_stops.add(from_stop_id)

                if to_stop_id not in seen_stops:
                    to_stop = self._stops.get(to_stop_id)
                    if to_stop:
                        features.append(self.stop_to_geojson_feature(to_stop))
                    seen_stops.add(to_stop_id)

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def export_stop_sequence_geojson(
        self,
        stop_ids: list[str],
        route_id: str,
        include_stops: bool = True,
    ) -> dict:
        """
        Export a sequence of stops as a GeoJSON FeatureCollection.

        :param stop_ids: Ordered list of stop IDs.
        :param route_id: The route ID.
        :param include_stops: Whether to include stop points.
        :returns: GeoJSON FeatureCollection dict.
        """
        features = []

        for i in range(len(stop_ids) - 1):
            stop_pair = self.get_edges_between_stops(
                stop_ids[i], stop_ids[i + 1], route_id
            )
            if stop_pair:
                features.append(self.stop_pair_to_geojson_feature(stop_pair, route_id))

        if include_stops:
            for stop_id in stop_ids:
                stop = self._stops.get(stop_id)
                if stop:
                    features.append(self.stop_to_geojson_feature(stop))

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def save_geojson(self, geojson: dict, path: str | Path) -> None:
        """
        Save a GeoJSON dict to a file.

        :param geojson: The GeoJSON dict to save.
        :param path: Output file path.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, indent=2)
