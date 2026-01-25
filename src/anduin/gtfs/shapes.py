import csv
from dataclasses import dataclass, field
from pathlib import Path

from anduin.gtfs.constants import DEFAULT_ROUTE_TYPES, EXCLUDED_ROUTE_NAME_PREFIXES


@dataclass
class RouteInfo:
    """Route metadata from routes.txt."""

    route_id: str
    route_short_name: str
    route_long_name: str
    route_type: int
    route_color: str = ""
    route_text_color: str = ""


@dataclass
class ShapePoint:
    """A single point in a shape."""

    lat: float
    lon: float
    sequence: int
    dist_traveled: float | None = None


@dataclass
class Shape:
    """A complete shape with its points and associated route info."""

    shape_id: str
    points: list[ShapePoint] = field(default_factory=list)
    routes: list[RouteInfo] = field(default_factory=list)


class GTFSShapeLoader:
    """Loads GTFS shapes with associated route information."""

    def __init__(self, gtfs_dir: str | Path):
        """
        Initialize the shape loader.

        :param gtfs_dir: Path to the directory containing extracted GTFS files.
        """
        self.gtfs_dir = Path(gtfs_dir)

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

    def _load_shape_to_routes(self) -> dict[str, set[str]]:
        """Load trips.txt to map shape_id -> set of route_ids."""
        shape_to_routes: dict[str, set[str]] = {}
        trips_file = self.gtfs_dir / "trips.txt"

        with open(trips_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                shape_id = row.get("shape_id")
                route_id = row.get("route_id")
                if shape_id and route_id:
                    if shape_id not in shape_to_routes:
                        shape_to_routes[shape_id] = set()
                    shape_to_routes[shape_id].add(route_id)

        return shape_to_routes

    def _load_shapes(self) -> dict[str, list[ShapePoint]]:
        """Load shapes.txt into a dict of shape_id -> list of points."""
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

        # Sort points by sequence
        for shape_id in shapes:
            shapes[shape_id].sort(key=lambda p: p.sequence)

        return shapes

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

    def load(self, route_types: list[int] | None = None) -> dict[str, Shape]:
        """
        Load all shapes with their associated route information.

        :param route_types: Optional list of GTFS route types to filter by (e.g., [3] for buses).
            If None, defaults to DEFAULT_ROUTE_TYPES (buses).
            Valid types: 0=Tram, 1=Subway, 2=Rail, 3=Bus, 4=Ferry
        :returns: Dict mapping shape_id to Shape objects with points and route info,
            filtered to only include shapes with routes of the specified types and
            excluding routes with excluded name prefixes (e.g., shuttle routes).
        """
        if route_types is None:
            route_types = DEFAULT_ROUTE_TYPES

        routes = self._load_routes()
        shape_to_routes = self._load_shape_to_routes()
        shape_points = self._load_shapes()

        shapes: dict[str, Shape] = {}
        for shape_id, points in shape_points.items():
            route_ids = shape_to_routes.get(shape_id, set())
            route_infos = [routes[rid] for rid in route_ids if rid in routes]

            # Filter routes by type and exclude based on name prefixes
            filtered_routes = [
                r
                for r in route_infos
                if r.route_type in route_types and not self._should_exclude_route(r)
            ]

            # Only include shapes that have at least one route of the specified types
            if filtered_routes:
                shapes[shape_id] = Shape(
                    shape_id=shape_id,
                    points=points,
                    routes=filtered_routes,
                )

        return shapes

    def load_for_route(self, route_id: str) -> list[Shape]:
        """
        Load shapes for a specific route.

        :param route_id: The route ID to filter by.
        :returns: List of Shape objects associated with the route.
        """
        # Load all route types to search all routes
        all_shapes = self.load(route_types=[0, 1, 2, 3, 4])
        return [
            shape
            for shape in all_shapes.values()
            if any(r.route_id == route_id for r in shape.routes)
        ]

    def load_for_route_type(self, route_type: int) -> list[Shape]:
        """
        Load shapes for a specific route type.

        Route types (GTFS standard):
            0 - Tram/Light rail
            1 - Subway/Metro
            2 - Rail
            3 - Bus
            4 - Ferry

        :param route_type: The GTFS route type to filter by.
        :returns: List of Shape objects for routes of that type.
        """
        shapes = self.load(route_types=[route_type])
        return list(shapes.values())
