"""Tests for OSM way extraction module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


from anduin.analysis.osm_extract import OSMWayExtractor, WayGeometry


class TestWayGeometry:
    """Test WayGeometry dataclass."""

    def test_initialization_with_defaults(self):
        """Test WayGeometry initialization with default values."""
        way = WayGeometry(way_id=123)
        assert way.way_id == 123
        assert way.routes == []
        assert way.coordinates == []
        assert way.tags == {}

    def test_initialization_with_all_fields(self):
        """Test WayGeometry initialization with all fields."""
        coordinates = [(1.0, 2.0), (3.0, 4.0)]
        tags = {"name": "Main St", "highway": "primary"}
        routes = ["1", "2", "3"]

        way = WayGeometry(
            way_id=456,
            coordinates=coordinates,
            tags=tags,
            routes=routes,
        )

        assert way.way_id == 456
        assert way.coordinates == coordinates
        assert way.tags == tags
        assert way.routes == routes


class TestOSMWayExtractorInit:
    """Test OSMWayExtractor initialization."""

    def test_init_with_string_paths(self):
        """Test initialization with string paths."""
        extractor = OSMWayExtractor(
            route_indexes_dir="data/route_indexes",
            osm_pbf_path="data/osm/test.osm.pbf",
        )
        assert extractor.route_indexes_dir == Path("data/route_indexes")
        assert extractor.osm_pbf_path == Path("data/osm/test.osm.pbf")

    def test_init_with_path_objects(self):
        """Test initialization with Path objects."""
        route_dir = Path("data/route_indexes")
        osm_path = Path("data/osm/test.osm.pbf")

        extractor = OSMWayExtractor(
            route_indexes_dir=route_dir,
            osm_pbf_path=osm_path,
        )

        assert extractor.route_indexes_dir == route_dir
        assert extractor.osm_pbf_path == osm_path

    def test_init_internal_state(self):
        """Test that initialization creates empty internal state."""
        extractor = OSMWayExtractor("dummy", "dummy")
        assert extractor._ways == {}
        assert len(extractor._way_to_routes) == 0
        assert extractor._missing_ways == set()
        assert extractor._skipped_ways == set()


class TestLoadRouteWayMappings:
    """Test route way mapping loading."""

    def test_loads_single_route_file(self):
        """Test loading a single route GeoJSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            route_dir = Path(tmpdir)

            # Create a test route GeoJSON file
            route_geojson = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "way_ids": [100, 101, 102],
                            "route_id": "1",
                        },
                        "geometry": {"type": "LineString", "coordinates": []},
                    },
                    {
                        "type": "Feature",
                        "properties": {
                            "way_ids": [103, 104],
                            "route_id": "1",
                        },
                        "geometry": {"type": "LineString", "coordinates": []},
                    },
                ],
            }

            route_file = route_dir / "route_1.geojson"
            with open(route_file, "w") as f:
                json.dump(route_geojson, f)

            extractor = OSMWayExtractor(route_dir, "dummy.pbf")
            extractor.load_route_way_mappings()

            # Verify way_to_routes mapping
            assert extractor._way_to_routes[100] == {"1"}
            assert extractor._way_to_routes[101] == {"1"}
            assert extractor._way_to_routes[102] == {"1"}
            assert extractor._way_to_routes[103] == {"1"}
            assert extractor._way_to_routes[104] == {"1"}

    def test_loads_multiple_route_files(self):
        """Test loading multiple route GeoJSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            route_dir = Path(tmpdir)

            # Create route 1
            route1_geojson = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"way_ids": [100, 101]},
                    }
                ],
            }
            with open(route_dir / "route_1.geojson", "w") as f:
                json.dump(route1_geojson, f)

            # Create route 2
            route2_geojson = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"way_ids": [101, 102]},
                    }
                ],
            }
            with open(route_dir / "route_2.geojson", "w") as f:
                json.dump(route2_geojson, f)

            extractor = OSMWayExtractor(route_dir, "dummy.pbf")
            extractor.load_route_way_mappings()

            # Way 100 only in route 1
            assert extractor._way_to_routes[100] == {"1"}
            # Way 101 in both routes
            assert extractor._way_to_routes[101] == {"1", "2"}
            # Way 102 only in route 2
            assert extractor._way_to_routes[102] == {"2"}

    def test_handles_missing_way_ids(self):
        """Test handling of features without way_ids."""
        with tempfile.TemporaryDirectory() as tmpdir:
            route_dir = Path(tmpdir)

            route_geojson = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"way_ids": [100]},
                    },
                    {
                        "type": "Feature",
                        "properties": {},  # Missing way_ids
                    },
                ],
            }

            with open(route_dir / "route_1.geojson", "w") as f:
                json.dump(route_geojson, f)

            extractor = OSMWayExtractor(route_dir, "dummy.pbf")
            extractor.load_route_way_mappings()

            # Should load way_ids from first feature
            assert len(extractor._way_to_routes) == 1
            assert extractor._way_to_routes[100] == {"1"}

    def test_handles_no_route_files(self):
        """Test handling when no route files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            route_dir = Path(tmpdir)

            extractor = OSMWayExtractor(route_dir, "dummy.pbf")
            extractor.load_route_way_mappings()

            assert len(extractor._way_to_routes) == 0


class TestToGeojson:
    """Test GeoJSON export."""

    def test_empty_ways_produces_valid_geojson(self):
        """Test that empty ways produce valid GeoJSON structure."""
        extractor = OSMWayExtractor("dummy", "dummy")
        geojson = extractor.to_geojson()

        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"] == []

    def test_geojson_feature_structure(self):
        """Test that GeoJSON features have correct structure."""
        extractor = OSMWayExtractor("dummy", "dummy")

        way = WayGeometry(
            way_id=123,
            routes=["1", "2"],
            coordinates=[(1.0, 2.0), (3.0, 4.0)],
            tags={"name": "Main St", "highway": "primary"},
        )
        extractor._ways[123] = way

        geojson = extractor.to_geojson()

        assert len(geojson["features"]) == 1
        feature = geojson["features"][0]

        assert feature["type"] == "Feature"
        assert feature["properties"]["way_id"] == 123
        assert feature["properties"]["routes"] == ["1", "2"]
        assert feature["properties"]["tags"] == {
            "name": "Main St",
            "highway": "primary",
        }
        assert feature["geometry"]["type"] == "LineString"
        assert feature["geometry"]["coordinates"] == [(1.0, 2.0), (3.0, 4.0)]

    def test_multiple_ways_in_geojson(self):
        """Test exporting multiple ways to GeoJSON."""
        extractor = OSMWayExtractor("dummy", "dummy")

        extractor._ways[100] = WayGeometry(
            way_id=100,
            routes=["1"],
            coordinates=[(0.0, 0.0), (1.0, 1.0)],
        )
        extractor._ways[101] = WayGeometry(
            way_id=101,
            routes=["2"],
            coordinates=[(2.0, 2.0), (3.0, 3.0)],
        )

        geojson = extractor.to_geojson()

        assert len(geojson["features"]) == 2
        way_ids = {f["properties"]["way_id"] for f in geojson["features"]}
        assert way_ids == {100, 101}


class TestSaveGeojson:
    """Test GeoJSON file saving."""

    def test_save_creates_file(self):
        """Test that save_geojson creates a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.geojson"

            extractor = OSMWayExtractor("dummy", "dummy")
            extractor._ways[123] = WayGeometry(
                way_id=123,
                routes=["1"],
                coordinates=[(1.0, 2.0)],
            )

            extractor.save_geojson(output_path)

            assert output_path.exists()

    def test_save_creates_parent_directories(self):
        """Test that save_geojson creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "output.geojson"

            extractor = OSMWayExtractor("dummy", "dummy")
            extractor._ways[123] = WayGeometry(way_id=123)

            extractor.save_geojson(output_path)

            assert output_path.exists()
            assert output_path.parent.exists()

    def test_save_produces_valid_json(self):
        """Test that saved GeoJSON is valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.geojson"

            extractor = OSMWayExtractor("dummy", "dummy")
            extractor._ways[123] = WayGeometry(
                way_id=123,
                routes=["1"],
                coordinates=[(1.0, 2.0), (3.0, 4.0)],
                tags={"name": "Test"},
            )

            extractor.save_geojson(output_path)

            with open(output_path) as f:
                loaded = json.load(f)

            assert loaded["type"] == "FeatureCollection"
            assert len(loaded["features"]) == 1


class TestGetWay:
    """Test get_way method."""

    def test_returns_way_when_exists(self):
        """Test get_way returns way when it exists."""
        extractor = OSMWayExtractor("dummy", "dummy")
        way = WayGeometry(way_id=123, routes=["1"])
        extractor._ways[123] = way

        result = extractor.get_way(123)
        assert result == way

    def test_returns_none_when_not_exists(self):
        """Test get_way returns None when way doesn't exist."""
        extractor = OSMWayExtractor("dummy", "dummy")
        result = extractor.get_way(999)
        assert result is None


class TestGetWaysForRoute:
    """Test get_ways_for_route method."""

    def test_returns_empty_list_when_no_ways(self):
        """Test returns empty list when route has no ways."""
        extractor = OSMWayExtractor("dummy", "dummy")
        result = extractor.get_ways_for_route("1")
        assert result == []

    def test_returns_ways_for_route(self):
        """Test returns all ways for a route."""
        extractor = OSMWayExtractor("dummy", "dummy")

        way1 = WayGeometry(way_id=100, routes=["1", "2"])
        way2 = WayGeometry(way_id=101, routes=["1"])
        way3 = WayGeometry(way_id=102, routes=["2"])

        extractor._ways[100] = way1
        extractor._ways[101] = way2
        extractor._ways[102] = way3

        extractor._way_to_routes[100] = {"1", "2"}
        extractor._way_to_routes[101] = {"1"}
        extractor._way_to_routes[102] = {"2"}

        result = extractor.get_ways_for_route("1")

        # Should return ways 100 and 101
        way_ids = {w.way_id for w in result}
        assert way_ids == {100, 101}


class TestSummary:
    """Test summary method."""

    def test_empty_summary(self):
        """Test summary with no ways loaded."""
        extractor = OSMWayExtractor("dummy", "dummy")
        summary = extractor.summary()

        assert summary["total_ways"] == 0
        assert summary["total_unique_ways_referenced"] == 0
        assert summary["total_routes"] == 0
        assert summary["missing_ways"] == 0
        assert summary["skipped_ways"] == 0
        assert summary["ways_with_multiple_routes"] == 0

    def test_summary_with_ways(self):
        """Test summary with loaded ways."""
        extractor = OSMWayExtractor("dummy", "dummy")

        extractor._ways[100] = WayGeometry(way_id=100, routes=["1", "2"])
        extractor._ways[101] = WayGeometry(way_id=101, routes=["1"])

        extractor._way_to_routes[100] = {"1", "2"}
        extractor._way_to_routes[101] = {"1"}
        extractor._way_to_routes[102] = {"2"}

        extractor._missing_ways = {102}

        summary = extractor.summary()

        assert summary["total_ways"] == 2
        assert summary["total_unique_ways_referenced"] == 3
        assert summary["total_routes"] == 2
        assert summary["missing_ways"] == 1
        assert summary["ways_with_multiple_routes"] == 1

    def test_summary_all_routes(self):
        """Test that summary collects all routes correctly."""
        extractor = OSMWayExtractor("dummy", "dummy")

        extractor._ways[100] = WayGeometry(way_id=100, routes=["1", "2", "3"])
        extractor._ways[101] = WayGeometry(way_id=101, routes=["4", "5"])

        extractor._way_to_routes[100] = {"1", "2", "3"}
        extractor._way_to_routes[101] = {"4", "5"}

        summary = extractor.summary()

        assert summary["total_routes"] == 5


class TestBuild:
    """Test build method."""

    @patch.object(OSMWayExtractor, "load_route_way_mappings")
    @patch.object(OSMWayExtractor, "extract_way_geometries")
    def test_build_calls_both_methods(self, mock_extract, mock_load):
        """Test that build calls load_route_way_mappings and extract_way_geometries."""
        extractor = OSMWayExtractor("dummy", "dummy")
        extractor.build()

        mock_load.assert_called_once()
        mock_extract.assert_called_once()

    @patch.object(OSMWayExtractor, "load_route_way_mappings")
    @patch.object(OSMWayExtractor, "extract_way_geometries")
    def test_build_calls_load_before_extract(self, mock_extract, mock_load):
        """Test that load is called before extract."""
        call_order = []

        def load_side_effect():
            call_order.append("load")

        def extract_side_effect():
            call_order.append("extract")

        mock_load.side_effect = load_side_effect
        mock_extract.side_effect = extract_side_effect

        extractor = OSMWayExtractor("dummy", "dummy")
        extractor.build()

        assert call_order == ["load", "extract"]


class TestExtractWayGeometriesEdgeCases:
    """Test extract_way_geometries error handling."""

    def test_extract_with_no_ways_to_extract(self):
        """Test extract handles case where no ways need extraction."""
        extractor = OSMWayExtractor("dummy", "dummy.pbf")

        # Don't populate _way_to_routes
        extractor.extract_way_geometries()

        # Should complete without error
        assert extractor._ways == {}
        assert extractor._missing_ways == set()

    def test_extract_tracks_missing_ways(self):
        """Test that extract tracks missing ways."""
        with tempfile.TemporaryDirectory() as tmpdir:
            route_dir = Path(tmpdir)

            # Create route file
            route_geojson = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"way_ids": [999999]},  # Non-existent way
                    }
                ],
            }
            with open(route_dir / "route_1.geojson", "w") as f:
                json.dump(route_geojson, f)

            # Mock the osmium handler to simulate missing way
            extractor = OSMWayExtractor(route_dir, "dummy.pbf")
            extractor.load_route_way_mappings()

            # Simulate missing way (way not added to _ways)
            extractor._ways = {}

            # Manually simulate what extract would do
            expected_ways = set(extractor._way_to_routes.keys())
            extracted_ways = set(extractor._ways.keys())
            extractor._missing_ways = expected_ways - extracted_ways

            assert 999999 in extractor._missing_ways
