import pytest

from anduin.gtfs.shapes import (
    RouteInfo,
    ShapePoint,
    Shape,
    GTFSShapeLoader,
)


class TestRouteInfo:
    """Tests for RouteInfo dataclass."""

    def test_required_fields(self):
        """Should create RouteInfo with required fields."""
        route = RouteInfo(
            route_id="Red",
            route_short_name="Red",
            route_long_name="Red Line",
            route_type=1,
        )
        assert route.route_id == "Red"
        assert route.route_short_name == "Red"
        assert route.route_long_name == "Red Line"
        assert route.route_type == 1

    def test_optional_fields_default(self):
        """Should have empty string defaults for optional fields."""
        route = RouteInfo(
            route_id="1",
            route_short_name="1",
            route_long_name="Route 1",
            route_type=3,
        )
        assert route.route_color == ""
        assert route.route_text_color == ""

    def test_optional_fields_set(self):
        """Should accept optional color fields."""
        route = RouteInfo(
            route_id="Red",
            route_short_name="Red",
            route_long_name="Red Line",
            route_type=1,
            route_color="DA291C",
            route_text_color="FFFFFF",
        )
        assert route.route_color == "DA291C"
        assert route.route_text_color == "FFFFFF"


class TestShapePoint:
    """Tests for ShapePoint dataclass."""

    def test_required_fields(self):
        """Should create ShapePoint with required fields."""
        point = ShapePoint(lat=42.3601, lon=-71.0589, sequence=1)
        assert point.lat == 42.3601
        assert point.lon == -71.0589
        assert point.sequence == 1

    def test_dist_traveled_default(self):
        """Should have None as default for dist_traveled."""
        point = ShapePoint(lat=42.3601, lon=-71.0589, sequence=1)
        assert point.dist_traveled is None

    def test_dist_traveled_set(self):
        """Should accept dist_traveled value."""
        point = ShapePoint(lat=42.3601, lon=-71.0589, sequence=1, dist_traveled=150.5)
        assert point.dist_traveled == 150.5


class TestShape:
    """Tests for Shape dataclass."""

    def test_required_fields(self):
        """Should create Shape with shape_id."""
        shape = Shape(shape_id="shape_001")
        assert shape.shape_id == "shape_001"

    def test_default_empty_lists(self):
        """Should have empty lists as defaults."""
        shape = Shape(shape_id="shape_001")
        assert shape.points == []
        assert shape.routes == []

    def test_with_points_and_routes(self):
        """Should accept points and routes."""
        points = [
            ShapePoint(lat=42.36, lon=-71.06, sequence=1),
            ShapePoint(lat=42.37, lon=-71.07, sequence=2),
        ]
        routes = [
            RouteInfo(
                route_id="Red",
                route_short_name="Red",
                route_long_name="Red Line",
                route_type=1,
            )
        ]
        shape = Shape(shape_id="shape_001", points=points, routes=routes)

        assert len(shape.points) == 2
        assert len(shape.routes) == 1


@pytest.fixture
def gtfs_dir(tmp_path):
    """Create a temporary GTFS directory with sample files."""
    # routes.txt
    routes_content = """route_id,route_short_name,route_long_name,route_type,route_color,route_text_color
Red,Red,Red Line,1,DA291C,FFFFFF
Blue,Blue,Blue Line,1,003DA5,FFFFFF
Bus1,1,Route 1,3,,"""
    (tmp_path / "routes.txt").write_text(routes_content)

    # trips.txt
    trips_content = """trip_id,route_id,shape_id,service_id
trip_001,Red,shape_red_1,weekday
trip_002,Red,shape_red_1,weekend
trip_003,Red,shape_red_2,weekday
trip_004,Blue,shape_blue_1,weekday
trip_005,Bus1,shape_bus_1,weekday"""
    (tmp_path / "trips.txt").write_text(trips_content)

    # shapes.txt
    shapes_content = """shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled
shape_red_1,42.3601,-71.0589,1,0
shape_red_1,42.3650,-71.0620,2,500
shape_red_1,42.3700,-71.0650,3,1000
shape_red_2,42.3800,-71.0700,1,0
shape_red_2,42.3850,-71.0750,2,600
shape_blue_1,42.3500,-71.0500,1,
shape_blue_1,42.3550,-71.0550,2,
shape_bus_1,42.3400,-71.0400,1,0"""
    (tmp_path / "shapes.txt").write_text(shapes_content)

    return tmp_path


@pytest.fixture
def gtfs_dir_minimal(tmp_path):
    """Create a minimal GTFS directory for edge case testing."""
    # routes.txt with minimal data
    routes_content = """route_id,route_short_name,route_long_name,route_type
R1,,,0"""
    (tmp_path / "routes.txt").write_text(routes_content)

    # trips.txt
    trips_content = """trip_id,route_id,shape_id
t1,R1,s1"""
    (tmp_path / "trips.txt").write_text(trips_content)

    # shapes.txt
    shapes_content = """shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
s1,42.0,-71.0,1"""
    (tmp_path / "shapes.txt").write_text(shapes_content)

    return tmp_path


class TestGTFSShapeLoaderInit:
    """Tests for GTFSShapeLoader initialization."""

    def test_init_with_string_path(self, tmp_path):
        """Should accept string path."""
        loader = GTFSShapeLoader(str(tmp_path))
        assert loader.gtfs_dir == tmp_path

    def test_init_with_path_object(self, tmp_path):
        """Should accept Path object."""
        loader = GTFSShapeLoader(tmp_path)
        assert loader.gtfs_dir == tmp_path


class TestGTFSShapeLoaderLoadRoutes:
    """Tests for GTFSShapeLoader._load_routes()."""

    def test_loads_all_routes(self, gtfs_dir):
        """Should load all routes from routes.txt."""
        loader = GTFSShapeLoader(gtfs_dir)
        routes = loader._load_routes()

        assert len(routes) == 3
        assert "Red" in routes
        assert "Blue" in routes
        assert "Bus1" in routes

    def test_route_fields_populated(self, gtfs_dir):
        """Should populate all route fields correctly."""
        loader = GTFSShapeLoader(gtfs_dir)
        routes = loader._load_routes()

        red = routes["Red"]
        assert red.route_id == "Red"
        assert red.route_short_name == "Red"
        assert red.route_long_name == "Red Line"
        assert red.route_type == 1
        assert red.route_color == "DA291C"
        assert red.route_text_color == "FFFFFF"

    def test_missing_optional_fields(self, gtfs_dir):
        """Should handle missing optional fields."""
        loader = GTFSShapeLoader(gtfs_dir)
        routes = loader._load_routes()

        bus = routes["Bus1"]
        assert bus.route_color == ""
        assert bus.route_text_color == ""

    def test_minimal_route_data(self, gtfs_dir_minimal):
        """Should handle minimal route data with defaults."""
        loader = GTFSShapeLoader(gtfs_dir_minimal)
        routes = loader._load_routes()

        assert len(routes) == 1
        route = routes["R1"]
        assert route.route_short_name == ""
        assert route.route_long_name == ""


class TestGTFSShapeLoaderLoadShapeToRoutes:
    """Tests for GTFSShapeLoader._load_shape_to_routes()."""

    def test_maps_shapes_to_routes(self, gtfs_dir):
        """Should map shape_ids to their route_ids."""
        loader = GTFSShapeLoader(gtfs_dir)
        mapping = loader._load_shape_to_routes()

        assert "shape_red_1" in mapping
        assert "Red" in mapping["shape_red_1"]

    def test_multiple_trips_same_shape(self, gtfs_dir):
        """Should handle multiple trips with same shape."""
        loader = GTFSShapeLoader(gtfs_dir)
        mapping = loader._load_shape_to_routes()

        # shape_red_1 has two trips but same route
        assert mapping["shape_red_1"] == {"Red"}

    def test_returns_set_of_route_ids(self, gtfs_dir):
        """Should return set of route_ids for each shape."""
        loader = GTFSShapeLoader(gtfs_dir)
        mapping = loader._load_shape_to_routes()

        for route_ids in mapping.values():
            assert isinstance(route_ids, set)


class TestGTFSShapeLoaderLoadShapes:
    """Tests for GTFSShapeLoader._load_shapes()."""

    def test_loads_all_shapes(self, gtfs_dir):
        """Should load all shapes from shapes.txt."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader._load_shapes()

        assert len(shapes) == 4
        assert "shape_red_1" in shapes
        assert "shape_red_2" in shapes
        assert "shape_blue_1" in shapes
        assert "shape_bus_1" in shapes

    def test_points_sorted_by_sequence(self, gtfs_dir):
        """Should sort points by sequence number."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader._load_shapes()

        points = shapes["shape_red_1"]
        sequences = [p.sequence for p in points]
        assert sequences == [1, 2, 3]

    def test_point_coordinates(self, gtfs_dir):
        """Should load point coordinates correctly."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader._load_shapes()

        point = shapes["shape_red_1"][0]
        assert point.lat == 42.3601
        assert point.lon == -71.0589

    def test_dist_traveled_present(self, gtfs_dir):
        """Should load dist_traveled when present."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader._load_shapes()

        point = shapes["shape_red_1"][1]
        assert point.dist_traveled == 500

    def test_dist_traveled_missing(self, gtfs_dir):
        """Should set dist_traveled to None when missing."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader._load_shapes()

        # shape_blue_1 has no dist_traveled values
        point = shapes["shape_blue_1"][0]
        assert point.dist_traveled is None


class TestGTFSShapeLoaderLoad:
    """Tests for GTFSShapeLoader.load()."""

    def test_returns_dict_of_shapes(self, gtfs_dir):
        """Should return dict mapping shape_id to Shape."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load()

        assert isinstance(shapes, dict)
        assert all(isinstance(s, Shape) for s in shapes.values())

    def test_shapes_have_points(self, gtfs_dir):
        """Should include points in each shape."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[0, 1, 2, 3, 4])  # Load all route types

        shape = shapes["shape_red_1"]
        assert len(shape.points) == 3

    def test_shapes_have_route_info(self, gtfs_dir):
        """Should include route info in shapes."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[0, 1, 2, 3, 4])  # Load all route types

        shape = shapes["shape_red_1"]
        assert len(shape.routes) == 1
        assert shape.routes[0].route_id == "Red"

    def test_shape_without_route_mapping(self, tmp_path):
        """Should handle shapes without route mappings."""
        # Create files where a shape has no trips
        (tmp_path / "routes.txt").write_text(
            "route_id,route_short_name,route_long_name,route_type\nR1,R1,Route 1,3"
        )
        (tmp_path / "trips.txt").write_text("trip_id,route_id,shape_id\n")
        (tmp_path / "shapes.txt").write_text(
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\ns1,42.0,-71.0,1"
        )

        loader = GTFSShapeLoader(tmp_path)
        shapes = loader.load(route_types=[0, 1, 2, 3, 4])  # Load all route types

        # Shape without route mapping is excluded (filtered out during filtering)
        assert "s1" not in shapes  # Shape has no routes, so it's not included


class TestGTFSShapeLoaderLoadForRoute:
    """Tests for GTFSShapeLoader.load_for_route()."""

    def test_returns_shapes_for_route(self, gtfs_dir):
        """Should return only shapes for the specified route."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route("Red")

        assert len(shapes) == 2
        shape_ids = {s.shape_id for s in shapes}
        assert shape_ids == {"shape_red_1", "shape_red_2"}

    def test_returns_list_of_shapes(self, gtfs_dir):
        """Should return a list of Shape objects."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route("Blue")

        assert isinstance(shapes, list)
        assert all(isinstance(s, Shape) for s in shapes)

    def test_empty_for_nonexistent_route(self, gtfs_dir):
        """Should return empty list for nonexistent route."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route("NonExistent")

        assert shapes == []

    def test_single_shape_route(self, gtfs_dir):
        """Should return single shape when route has one."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route("Blue")

        assert len(shapes) == 1
        assert shapes[0].shape_id == "shape_blue_1"


class TestGTFSShapeLoaderLoadForRouteType:
    """Tests for GTFSShapeLoader.load_for_route_type()."""

    def test_returns_shapes_for_subway(self, gtfs_dir):
        """Should return shapes for subway routes (type 1)."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route_type(1)

        shape_ids = {s.shape_id for s in shapes}
        assert "shape_red_1" in shape_ids
        assert "shape_red_2" in shape_ids
        assert "shape_blue_1" in shape_ids
        assert "shape_bus_1" not in shape_ids

    def test_returns_shapes_for_bus(self, gtfs_dir):
        """Should return shapes for bus routes (type 3)."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route_type(3)

        assert len(shapes) == 1
        assert shapes[0].shape_id == "shape_bus_1"

    def test_empty_for_unused_type(self, gtfs_dir):
        """Should return empty list for route type with no shapes."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route_type(4)  # Ferry

        assert shapes == []

    def test_returns_list(self, gtfs_dir):
        """Should return a list of Shape objects."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load_for_route_type(1)

        assert isinstance(shapes, list)
        assert all(isinstance(s, Shape) for s in shapes)


class TestGTFSShapeLoaderLoadWithRouteTypes:
    """Tests for GTFSShapeLoader.load() with route_types parameter."""

    def test_load_with_default_route_types(self, gtfs_dir):
        """Should default to bus routes (type 3) when no route_types specified."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load()

        # Default should be bus only
        shape_ids = {s.shape_id for s in shapes.values()}
        assert shape_ids == {"shape_bus_1"}

    def test_load_with_single_route_type(self, gtfs_dir):
        """Should filter to single route type."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[1])

        # Should get subway shapes
        shape_ids = {s.shape_id for s in shapes.values()}
        assert shape_ids == {"shape_red_1", "shape_red_2", "shape_blue_1"}

    def test_load_with_multiple_route_types(self, gtfs_dir):
        """Should filter to multiple route types."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[1, 3])

        # Should get both subway and bus shapes
        shape_ids = {s.shape_id for s in shapes.values()}
        assert shape_ids == {
            "shape_red_1",
            "shape_red_2",
            "shape_blue_1",
            "shape_bus_1",
        }

    def test_load_with_no_filter_none(self, gtfs_dir):
        """Should load all routes when route_types is None."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=None)

        # None should default to DEFAULT_ROUTE_TYPES (bus only)
        shape_ids = {s.shape_id for s in shapes.values()}
        assert shape_ids == {"shape_bus_1"}

    def test_load_filtered_shapes_have_correct_routes(self, gtfs_dir):
        """Should only include filtered route types in shape.routes."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[1])

        # All routes in returned shapes should be type 1
        for shape in shapes.values():
            for route in shape.routes:
                assert route.route_type == 1

    def test_load_with_no_matching_routes(self, gtfs_dir):
        """Should return empty dict when no routes match."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[4])  # Ferry - none exist

        assert shapes == {}

    def test_load_with_unused_type(self, gtfs_dir):
        """Should return empty dict for unused route type."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[2])  # Rail - none exist

        assert shapes == {}

    def test_load_preserves_points(self, gtfs_dir):
        """Should preserve shape points when filtering."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[1])

        shape = shapes["shape_red_1"]
        assert len(shape.points) == 3

    def test_returns_dict_of_shapes(self, gtfs_dir):
        """Should return dict mapping shape_id to Shape."""
        loader = GTFSShapeLoader(gtfs_dir)
        shapes = loader.load(route_types=[3])

        assert isinstance(shapes, dict)
        assert all(isinstance(s, Shape) for s in shapes.values())

    def test_mixed_shape_with_multiple_route_types(self, tmp_path):
        """Should include shape if ANY route matches filter."""
        # Create GTFS with a shape used by both bus and subway
        routes_content = """route_id,route_short_name,route_long_name,route_type
SubwayRoute,Sub,Subway Route,1
BusRoute,Bus,Bus Route,3"""
        (tmp_path / "routes.txt").write_text(routes_content)

        trips_content = """trip_id,route_id,shape_id
trip1,SubwayRoute,shared_shape
trip2,BusRoute,shared_shape"""
        (tmp_path / "trips.txt").write_text(trips_content)

        shapes_content = """shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shared_shape,42.0,-71.0,1"""
        (tmp_path / "shapes.txt").write_text(shapes_content)

        loader = GTFSShapeLoader(tmp_path)

        # Filter to subway only - should still return shape with both routes
        shapes = loader.load(route_types=[1])
        assert "shared_shape" in shapes
        # But only subway route should be in shape.routes
        assert len(shapes["shared_shape"].routes) == 1
        assert shapes["shared_shape"].routes[0].route_type == 1

        # Filter to bus only
        shapes = loader.load(route_types=[3])
        assert "shared_shape" in shapes
        assert len(shapes["shared_shape"].routes) == 1
        assert shapes["shared_shape"].routes[0].route_type == 3


class TestGTFSShapeLoaderShuttleRouteExclusion:
    """Tests for GTFSShapeLoader shuttle route exclusion."""

    def test_should_exclude_route_with_shuttle_prefix(self):
        """Should identify routes with Shuttle- prefix as excluded."""
        loader = GTFSShapeLoader("/tmp")

        shuttle_route = RouteInfo(
            route_id="shuttle_1",
            route_short_name="Shuttle-TFGreenWickfordJunction",
            route_long_name="Shuttle to Green Wickford Junction",
            route_type=3,
        )
        assert loader._should_exclude_route(shuttle_route) is True

    def test_should_exclude_route_with_shuttle_prefix_in_long_name(self):
        """Should identify routes with Shuttle- prefix in long name as excluded."""
        loader = GTFSShapeLoader("/tmp")

        shuttle_route = RouteInfo(
            route_id="shuttle_1",
            route_short_name="S1",
            route_long_name="Shuttle-Airport",
            route_type=3,
        )
        assert loader._should_exclude_route(shuttle_route) is True

    def test_should_exclude_route_with_shuttle_prefix_in_id(self):
        """Should identify routes with Shuttle- prefix in route_id as excluded."""
        loader = GTFSShapeLoader("/tmp")

        shuttle_route = RouteInfo(
            route_id="Shuttle-BackBayForestHills",
            route_short_name="SBF",
            route_long_name="Back Bay to Forest Hills",
            route_type=3,
        )
        assert loader._should_exclude_route(shuttle_route) is True

    def test_should_not_exclude_regular_bus_route(self):
        """Should not exclude regular bus routes."""
        loader = GTFSShapeLoader("/tmp")

        regular_route = RouteInfo(
            route_id="1",
            route_short_name="1",
            route_long_name="Main Street Bus",
            route_type=3,
        )
        assert loader._should_exclude_route(regular_route) is False

    def test_load_excludes_shuttle_routes_by_default(self, tmp_path):
        """Should exclude shuttle routes from loaded shapes."""
        routes_content = """route_id,route_short_name,route_long_name,route_type
RegularBus,1,Regular Bus Route,3
Shuttle-TFGreenWickfordJunction,TF,Shuttle Service,3"""
        (tmp_path / "routes.txt").write_text(routes_content)

        trips_content = """trip_id,route_id,shape_id
trip1,RegularBus,shape_bus_1
trip2,Shuttle-TFGreenWickfordJunction,shape_shuttle_1"""
        (tmp_path / "trips.txt").write_text(trips_content)

        shapes_content = """shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shape_bus_1,42.0,-71.0,1
shape_shuttle_1,42.1,-71.1,1"""
        (tmp_path / "shapes.txt").write_text(shapes_content)

        loader = GTFSShapeLoader(tmp_path)
        shapes = loader.load()

        # Should only have the regular bus shape, not the shuttle shape
        assert len(shapes) == 1
        assert "shape_bus_1" in shapes
        assert "shape_shuttle_1" not in shapes

    def test_load_excludes_shuttle_when_mixed_with_regular(self, tmp_path):
        """Should exclude shuttle route from mixed shape."""
        routes_content = """route_id,route_short_name,route_long_name,route_type
RegularBus,1,Regular Bus Route,3
Shuttle-Airport,SA,Airport Shuttle,3"""
        (tmp_path / "routes.txt").write_text(routes_content)

        trips_content = """trip_id,route_id,shape_id
trip1,RegularBus,shared_shape
trip2,Shuttle-Airport,shared_shape"""
        (tmp_path / "trips.txt").write_text(trips_content)

        shapes_content = """shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
shared_shape,42.0,-71.0,1"""
        (tmp_path / "shapes.txt").write_text(shapes_content)

        loader = GTFSShapeLoader(tmp_path)
        shapes = loader.load()

        # Shape should be included but only with regular route
        assert "shared_shape" in shapes
        assert len(shapes["shared_shape"].routes) == 1
        assert shapes["shared_shape"].routes[0].route_id == "RegularBus"
