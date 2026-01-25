import json
from dataclasses import dataclass, field
from typing import Protocol

from anduin.gtfs.shapes import Shape, ShapePoint


@dataclass
class MatchedEdge:
    """A matched edge from Valhalla."""

    edge_id: int
    way_id: int
    names: list[str] = field(default_factory=list)
    length: float = 0.0
    speed: float = 0.0
    road_class: str = ""
    use: str = ""
    begin_shape_index: int = 0
    end_shape_index: int = 0


@dataclass
class MatchedPoint:
    """A matched point snapped to the road network."""

    lat: float
    lon: float
    original_index: int
    edge_index: int
    distance_from_edge: float = 0.0


@dataclass
class MapMatchResult:
    """Result of a map matching operation."""

    shape_id: str
    matched_points: list[MatchedPoint] = field(default_factory=list)
    edges: list[MatchedEdge] = field(default_factory=list)
    confidence: float = 0.0
    raw_response: dict = field(default_factory=dict)


class ValhallaBackend(Protocol):
    """Protocol for Valhalla backends."""

    def trace_attributes(self, request: dict) -> dict:
        """Execute a trace_attributes request."""
        ...


class PyValhallaBackend:
    """Backend using pyvalhalla for direct C++ bindings (much faster)."""

    def __init__(
        self,
        config_path: str | None = None,
        tile_extract: str | None = None,
    ):
        """
        Initialize pyvalhalla backend.

        :param config_path: Path to valhalla.json config file.
        :param tile_extract: Path to valhalla_tiles.tar file.
            Either config_path or tile_extract must be provided.
        """
        try:
            from valhalla import Actor, get_config
        except ImportError:
            raise ImportError(
                "pyvalhalla is not installed. Install with: pip install pyvalhalla"
            )

        # Get base config from tile_extract (has all required fields)
        if tile_extract:
            config = get_config(tile_extract=tile_extract, tile_dir="")
        elif config_path:
            # If only config_path is provided, generate base config with defaults
            # and merge in custom settings
            config = get_config(tile_dir="")
            with open(config_path) as f:
                custom_config = json.load(f)
            # Deep merge custom config into base config
            self._merge_dicts(config, custom_config)
        else:
            raise ValueError("Either config_path or tile_extract must be provided")

        self._actor = Actor(config)

    @staticmethod
    def _merge_dicts(base: dict, custom: dict) -> None:
        """Recursively merge custom config into base config (in-place)."""
        for key, value in custom.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                PyValhallaBackend._merge_dicts(base[key], value)
            else:
                base[key] = value

    def trace_attributes(self, request: dict) -> dict:
        response = self._actor.trace_attributes(request)
        # pyvalhalla returns a JSON string
        if isinstance(response, str):
            return json.loads(response)
        return response


class ValhallaMapMatcher:
    """Map matches GTFS shapes to road network edges using Valhalla."""

    def __init__(
        self,
        costing: str = "auto",
        backend: ValhallaBackend | None = None,
        tile_extract: str | None = None,
        config_path: str | None = None,
    ):
        """
        Initialize the map matcher.

        :param costing: Costing model to use. Options:
            - "auto" for roads
            - "bus" for bus routes
            - "bicycle" for bike paths
            - "pedestrian" for walking paths
            - "multimodal" for transit
        :param backend: Custom backend instance. If provided, other backend args ignored.
        :param tile_extract: Path to valhalla_tiles.tar for pyvalhalla backend.
        :param config_path: Path to valhalla.json for pyvalhalla backend.
        """
        self.costing = costing

        if backend:
            self._backend = backend
        elif tile_extract or config_path:
            self._backend = PyValhallaBackend(
                config_path=config_path,
                tile_extract=tile_extract,
            )
        else:
            raise ValueError(
                "Either backend, tile_extract, or config_path must be provided"
            )

    @classmethod
    def from_pyvalhalla(
        cls,
        tile_extract: str | None = None,
        config_path: str | None = None,
        costing: str = "auto",
    ) -> "ValhallaMapMatcher":
        """
        Create a matcher using pyvalhalla backend.

        :param tile_extract: Path to valhalla_tiles.tar file.
        :param config_path: Path to valhalla.json config file.
        :param costing: Costing model to use.
        :returns: ValhallaMapMatcher configured with pyvalhalla backend.
        """
        backend = PyValhallaBackend(config_path=config_path, tile_extract=tile_extract)
        return cls(backend=backend, costing=costing)

    def _build_trace_request(
        self,
        points: list[ShapePoint],
        costing: str | None = None,
    ) -> dict:
        """Build the trace_attributes request body."""
        shape = [{"lat": p.lat, "lon": p.lon} for p in points]

        return {
            "shape": shape,
            "costing": costing or self.costing,
            "shape_match": "map_snap",
            "filters": {
                "attributes": [
                    "edge.id",
                    "edge.way_id",
                    "edge.names",
                    "edge.length",
                    "edge.speed",
                    "edge.road_class",
                    "edge.use",
                    "edge.begin_shape_index",
                    "edge.end_shape_index",
                    "matched.point",
                    "matched.edge_index",
                    "matched.distance_from_trace_point",
                ],
                "action": "include",
            },
        }

    def _parse_response(self, shape_id: str, response: dict) -> MapMatchResult:
        """Parse Valhalla trace_attributes response."""
        edges = []
        for edge_data in response.get("edges", []):
            edge = MatchedEdge(
                edge_id=edge_data.get("id", 0),
                way_id=edge_data.get("way_id", 0),
                names=edge_data.get("names", []),
                length=edge_data.get("length", 0.0),
                speed=edge_data.get("speed", 0.0),
                road_class=edge_data.get("road_class", ""),
                use=edge_data.get("use", ""),
                begin_shape_index=edge_data.get("begin_shape_index", 0),
                end_shape_index=edge_data.get("end_shape_index", 0),
            )
            edges.append(edge)

        matched_points = []
        for i, point_data in enumerate(response.get("matched_points", [])):
            point = MatchedPoint(
                lat=point_data.get("lat", 0.0),
                lon=point_data.get("lon", 0.0),
                original_index=i,
                edge_index=point_data.get("edge_index", -1),
                distance_from_edge=point_data.get("distance_from_trace_point", 0.0),
            )
            matched_points.append(point)

        confidence_scores = response.get("confidence_scores", [])
        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 0.0
        )

        return MapMatchResult(
            shape_id=shape_id,
            matched_points=matched_points,
            edges=edges,
            confidence=avg_confidence,
            raw_response=response,
        )

    def match_shape(
        self,
        shape: Shape,
        costing: str | None = None,
    ) -> MapMatchResult:
        """
        Map match a GTFS shape to road network edges.

        :param shape: The Shape object to match.
        :param costing: Override the default costing model.
        :returns: MapMatchResult with matched edges and points.
        """
        if not shape.points:
            return MapMatchResult(shape_id=shape.shape_id)

        request_body = self._build_trace_request(shape.points, costing)
        response = self._backend.trace_attributes(request_body)
        return self._parse_response(shape.shape_id, response)

    def match_points(
        self,
        points: list[tuple[float, float]],
        shape_id: str = "custom",
        costing: str | None = None,
    ) -> MapMatchResult:
        """
        Map match a list of lat/lon points.

        :param points: List of (lat, lon) tuples.
        :param shape_id: Identifier for the result.
        :param costing: Override the default costing model.
        :returns: MapMatchResult with matched edges and points.
        """
        shape_points = [
            ShapePoint(lat=lat, lon=lon, sequence=i)
            for i, (lat, lon) in enumerate(points)
        ]
        shape = Shape(shape_id=shape_id, points=shape_points)
        return self.match_shape(shape, costing)

    def match_shapes(
        self,
        shapes: list[Shape],
        costing: str | None = None,
    ) -> dict[str, MapMatchResult]:
        """
        Map match multiple shapes.

        :param shapes: List of Shape objects to match.
        :param costing: Override the default costing model.
        :returns: Dict mapping shape_id to MapMatchResult.
        """
        results = {}
        for shape in shapes:
            try:
                results[shape.shape_id] = self.match_shape(shape, costing)
            except RuntimeError as e:
                # Store error result but continue processing
                results[shape.shape_id] = MapMatchResult(
                    shape_id=shape.shape_id,
                    raw_response={"error": str(e)},
                )
        return results

    def get_matched_geometry(self, result: MapMatchResult) -> list[tuple[float, float]]:
        """
        Extract the matched geometry as a list of coordinates.

        :param result: A MapMatchResult from a matching operation.
        :returns: List of (lat, lon) tuples representing the matched path.
        """
        return [(p.lat, p.lon) for p in result.matched_points]

    def get_edge_way_ids(self, result: MapMatchResult) -> list[int]:
        """
        Extract unique OSM way IDs from the matched result.

        :param result: A MapMatchResult from a matching operation.
        :returns: List of unique OSM way IDs in order of traversal.
        """
        seen = set()
        way_ids = []
        for edge in result.edges:
            if edge.way_id not in seen:
                seen.add(edge.way_id)
                way_ids.append(edge.way_id)
        return way_ids
