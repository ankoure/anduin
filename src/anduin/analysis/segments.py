from dataclasses import dataclass, field
from collections import defaultdict

from anduin.gtfs.shapes import Shape, RouteInfo
from anduin.matching.valhalla import ValhallaMapMatcher, MapMatchResult


@dataclass
class SegmentRoutes:
    """Routes that share a particular segment."""

    way_id: int
    edge_id: int
    names: list[str] = field(default_factory=list)
    road_class: str = ""
    length: float = 0.0
    routes: list[RouteInfo] = field(default_factory=list)

    @property
    def route_names(self) -> list[str]:
        """Get short names of all routes using this segment."""
        return sorted(
            set(r.route_short_name for r in self.routes if r.route_short_name)
        )


@dataclass
class RouteSegments:
    """All segments used by a particular route."""

    route: RouteInfo
    way_ids: list[int] = field(default_factory=list)
    edge_ids: list[int] = field(default_factory=list)
    total_length: float = 0.0


class SharedSegmentAnalyzer:
    """Analyzes which routes share which road/rail segments."""

    def __init__(self, matcher: ValhallaMapMatcher):
        """
        Initialize the analyzer.

        :param matcher: A configured ValhallaMapMatcher instance.
        """
        self.matcher = matcher

        # way_id -> SegmentRoutes
        self._segments: dict[int, SegmentRoutes] = {}
        # route_id -> RouteSegments
        self._route_segments: dict[str, RouteSegments] = {}
        # way_id -> set of route_ids
        self._way_to_routes: dict[int, set[str]] = defaultdict(set)

    def add_shape(
        self, shape: Shape, match_result: MapMatchResult | None = None
    ) -> None:
        """
        Add a shape and its routes to the analysis.

        :param shape: The GTFS shape with route information.
        :param match_result: Pre-computed match result, or None to compute it.
        """
        if match_result is None:
            match_result = self.matcher.match_shape(shape)

        for route in shape.routes:
            if route.route_id not in self._route_segments:
                self._route_segments[route.route_id] = RouteSegments(route=route)

            route_seg = self._route_segments[route.route_id]

            for edge in match_result.edges:
                # Track segment info
                if edge.way_id not in self._segments:
                    self._segments[edge.way_id] = SegmentRoutes(
                        way_id=edge.way_id,
                        edge_id=edge.edge_id,
                        names=edge.names,
                        road_class=edge.road_class,
                        length=edge.length,
                    )

                segment = self._segments[edge.way_id]

                # Add route to segment if not already present
                if not any(r.route_id == route.route_id for r in segment.routes):
                    segment.routes.append(route)

                # Track way_id -> routes mapping
                self._way_to_routes[edge.way_id].add(route.route_id)

                # Track route's segments
                if edge.way_id not in route_seg.way_ids:
                    route_seg.way_ids.append(edge.way_id)
                    route_seg.total_length += edge.length
                if edge.edge_id not in route_seg.edge_ids:
                    route_seg.edge_ids.append(edge.edge_id)

    def add_shapes(
        self,
        shapes: list[Shape],
        match_results: dict[str, MapMatchResult] | None = None,
    ) -> None:
        """
        Add multiple shapes to the analysis.

        :param shapes: List of GTFS shapes with route information.
        :param match_results: Pre-computed match results keyed by shape_id, or None.
        """
        if match_results is None:
            match_results = self.matcher.match_shapes(shapes)

        for shape in shapes:
            result = match_results.get(shape.shape_id)
            self.add_shape(shape, result)

    def get_segment(self, way_id: int) -> SegmentRoutes | None:
        """Get segment info and routes for a specific OSM way."""
        return self._segments.get(way_id)

    def get_routes_for_segment(self, way_id: int) -> list[RouteInfo]:
        """Get all routes that use a specific segment."""
        segment = self._segments.get(way_id)
        return segment.routes if segment else []

    def get_segments_for_route(self, route_id: str) -> RouteSegments | None:
        """Get all segments used by a specific route."""
        return self._route_segments.get(route_id)

    def get_shared_segments(self, min_routes: int = 2) -> list[SegmentRoutes]:
        """
        Get segments shared by at least N routes.

        :param min_routes: Minimum number of routes sharing the segment.
        :returns: List of SegmentRoutes with at least min_routes routes.
        """
        return [seg for seg in self._segments.values() if len(seg.routes) >= min_routes]

    def get_segments_shared_by(self, route_ids: list[str]) -> list[SegmentRoutes]:
        """
        Get segments shared by all specified routes.

        :param route_ids: List of route IDs that must all share the segment.
        :returns: List of SegmentRoutes used by all specified routes.
        """
        route_set = set(route_ids)
        result = []

        for segment in self._segments.values():
            segment_route_ids = {r.route_id for r in segment.routes}
            if route_set.issubset(segment_route_ids):
                result.append(segment)

        return result

    def get_busiest_segments(self, limit: int = 10) -> list[SegmentRoutes]:
        """
        Get segments with the most routes.

        :param limit: Maximum number of segments to return.
        :returns: List of SegmentRoutes sorted by route count descending.
        """
        sorted_segments = sorted(
            self._segments.values(),
            key=lambda s: len(s.routes),
            reverse=True,
        )
        return sorted_segments[:limit]

    def get_overlap_matrix(
        self, route_ids: list[str] | None = None
    ) -> dict[str, dict[str, float]]:
        """
        Compute pairwise route overlap as percentage of shared segments.

        :param route_ids: Specific routes to analyze, or None for all routes.
        :returns: Nested dict where result[route_a][route_b] = percentage of route_a
            segments that are also used by route_b.
        """
        if route_ids is None:
            route_ids = list(self._route_segments.keys())

        matrix: dict[str, dict[str, float]] = {}

        for route_a in route_ids:
            matrix[route_a] = {}
            seg_a = self._route_segments.get(route_a)
            if not seg_a or not seg_a.way_ids:
                continue

            ways_a = set(seg_a.way_ids)

            for route_b in route_ids:
                seg_b = self._route_segments.get(route_b)
                if not seg_b:
                    matrix[route_a][route_b] = 0.0
                    continue

                ways_b = set(seg_b.way_ids)
                shared = ways_a & ways_b
                matrix[route_a][route_b] = len(shared) / len(ways_a) * 100

        return matrix

    def summary(self) -> dict:
        """Get a summary of the analysis."""
        shared_2plus = len(self.get_shared_segments(min_routes=2))
        shared_3plus = len(self.get_shared_segments(min_routes=3))
        shared_5plus = len(self.get_shared_segments(min_routes=5))

        return {
            "total_segments": len(self._segments),
            "total_routes": len(self._route_segments),
            "segments_shared_by_2+_routes": shared_2plus,
            "segments_shared_by_3+_routes": shared_3plus,
            "segments_shared_by_5+_routes": shared_5plus,
            "busiest_segment_route_count": max(
                (len(s.routes) for s in self._segments.values()), default=0
            ),
        }

    def to_geojson_features(self) -> list[dict]:
        """
        Export shared segments as GeoJSON features.

        Note: This returns feature properties only since we don't have
        the actual geometries. Use with OSM data to get full features.

        :returns: List of GeoJSON feature property dicts.
        """
        features = []
        for segment in self._segments.values():
            if len(segment.routes) < 2:
                continue

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "way_id": segment.way_id,
                        "names": segment.names,
                        "road_class": segment.road_class,
                        "length": segment.length,
                        "route_count": len(segment.routes),
                        "routes": segment.route_names,
                    },
                    "geometry": None,  # Would need OSM lookup for actual geometry
                }
            )

        return features
