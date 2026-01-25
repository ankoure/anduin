import pytest
from pathlib import Path

from anduin.gtfs.stops import Stop, TripStopSequence, load_stops


class TestStop:
    """Tests for Stop dataclass."""

    def test_create_stop(self):
        """Should create Stop with all fields."""
        stop = Stop(
            stop_id="place-harvard",
            stop_name="Harvard",
            lat=42.3734,
            lon=-71.1189,
        )
        assert stop.stop_id == "place-harvard"
        assert stop.stop_name == "Harvard"
        assert stop.lat == 42.3734
        assert stop.lon == -71.1189

    def test_stop_equality(self):
        """Stops with same values should be equal."""
        stop1 = Stop(stop_id="1", stop_name="Test", lat=42.0, lon=-71.0)
        stop2 = Stop(stop_id="1", stop_name="Test", lat=42.0, lon=-71.0)
        assert stop1 == stop2

    def test_stop_inequality(self):
        """Stops with different values should not be equal."""
        stop1 = Stop(stop_id="1", stop_name="Test", lat=42.0, lon=-71.0)
        stop2 = Stop(stop_id="2", stop_name="Test", lat=42.0, lon=-71.0)
        assert stop1 != stop2


class TestTripStopSequence:
    """Tests for TripStopSequence dataclass."""

    def test_create_with_required_fields(self):
        """Should create TripStopSequence with required fields."""
        seq = TripStopSequence(
            trip_id="trip_001",
            route_id="Red",
            shape_id="shape_red_1",
        )
        assert seq.trip_id == "trip_001"
        assert seq.route_id == "Red"
        assert seq.shape_id == "shape_red_1"

    def test_default_empty_stops(self):
        """Should have empty stops list by default."""
        seq = TripStopSequence(
            trip_id="trip_001",
            route_id="Red",
            shape_id="shape_red_1",
        )
        assert seq.stops == []

    def test_with_stops(self):
        """Should accept stops list."""
        stop1 = Stop(stop_id="1", stop_name="Stop 1", lat=42.0, lon=-71.0)
        stop2 = Stop(stop_id="2", stop_name="Stop 2", lat=42.1, lon=-71.1)

        seq = TripStopSequence(
            trip_id="trip_001",
            route_id="Red",
            shape_id="shape_red_1",
            stops=[(1, stop1), (2, stop2)],
        )

        assert len(seq.stops) == 2
        assert seq.stops[0] == (1, stop1)
        assert seq.stops[1] == (2, stop2)


@pytest.fixture
def gtfs_dir(tmp_path):
    """Create a temporary GTFS directory with stops.txt."""
    stops_content = """stop_id,stop_name,stop_lat,stop_lon
place-harvard,Harvard,42.3734,-71.1189
place-central,Central,42.3653,-71.1037
place-kendall,Kendall/MIT,42.3625,-71.0862
place-charles,Charles/MGH,42.3613,-71.0707"""
    (tmp_path / "stops.txt").write_text(stops_content)
    return tmp_path


@pytest.fixture
def gtfs_dir_minimal(tmp_path):
    """Create a minimal GTFS directory for edge case testing."""
    stops_content = """stop_id,stop_name,stop_lat,stop_lon
1,,42.0,-71.0"""
    (tmp_path / "stops.txt").write_text(stops_content)
    return tmp_path


@pytest.fixture
def gtfs_dir_with_bom(tmp_path):
    """Create GTFS directory with UTF-8 BOM in stops.txt."""
    stops_content = """stop_id,stop_name,stop_lat,stop_lon
1,Test Stop,42.0,-71.0"""
    # Write with UTF-8 BOM
    (tmp_path / "stops.txt").write_bytes(
        b"\xef\xbb\xbf" + stops_content.encode("utf-8")
    )
    return tmp_path


class TestLoadStops:
    """Tests for load_stops function."""

    def test_loads_all_stops(self, gtfs_dir):
        """Should load all stops from stops.txt."""
        stops = load_stops(gtfs_dir)

        assert len(stops) == 4
        assert "place-harvard" in stops
        assert "place-central" in stops
        assert "place-kendall" in stops
        assert "place-charles" in stops

    def test_stop_fields_populated(self, gtfs_dir):
        """Should populate all stop fields correctly."""
        stops = load_stops(gtfs_dir)

        harvard = stops["place-harvard"]
        assert harvard.stop_id == "place-harvard"
        assert harvard.stop_name == "Harvard"
        assert harvard.lat == 42.3734
        assert harvard.lon == -71.1189

    def test_returns_dict_keyed_by_stop_id(self, gtfs_dir):
        """Should return dict with stop_id as keys."""
        stops = load_stops(gtfs_dir)

        assert isinstance(stops, dict)
        for stop_id, stop in stops.items():
            assert stop_id == stop.stop_id

    def test_accepts_string_path(self, gtfs_dir):
        """Should accept string path."""
        stops = load_stops(str(gtfs_dir))
        assert len(stops) == 4

    def test_accepts_path_object(self, gtfs_dir):
        """Should accept Path object."""
        stops = load_stops(Path(gtfs_dir))
        assert len(stops) == 4

    def test_missing_stop_name(self, gtfs_dir_minimal):
        """Should handle missing stop_name with empty string."""
        stops = load_stops(gtfs_dir_minimal)

        stop = stops["1"]
        assert stop.stop_name == ""

    def test_handles_utf8_bom(self, gtfs_dir_with_bom):
        """Should handle UTF-8 BOM in file."""
        stops = load_stops(gtfs_dir_with_bom)

        assert "1" in stops
        assert stops["1"].stop_name == "Test Stop"

    def test_coordinate_precision(self, gtfs_dir):
        """Should preserve coordinate precision."""
        stops = load_stops(gtfs_dir)

        kendall = stops["place-kendall"]
        assert kendall.lat == 42.3625
        assert kendall.lon == -71.0862

    def test_empty_file(self, tmp_path):
        """Should return empty dict for file with only headers."""
        (tmp_path / "stops.txt").write_text("stop_id,stop_name,stop_lat,stop_lon\n")

        stops = load_stops(tmp_path)
        assert stops == {}

    def test_file_not_found(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_stops(tmp_path)


class TestLoadStopsIntegration:
    """Integration tests for stop loading."""

    def test_large_dataset(self, tmp_path):
        """Should handle larger datasets efficiently."""
        # Generate a larger stops file
        lines = ["stop_id,stop_name,stop_lat,stop_lon"]
        for i in range(1000):
            lines.append(f"stop_{i},Stop {i},{42.0 + i * 0.001},{-71.0 - i * 0.001}")

        (tmp_path / "stops.txt").write_text("\n".join(lines))

        stops = load_stops(tmp_path)

        assert len(stops) == 1000
        assert "stop_0" in stops
        assert "stop_999" in stops

    def test_special_characters_in_name(self, tmp_path):
        """Should handle special characters in stop names."""
        stops_content = """stop_id,stop_name,stop_lat,stop_lon
1,"Stop with, comma",42.0,-71.0
2,Stop with "quotes",42.1,-71.1
3,Café & Station,42.2,-71.2"""
        (tmp_path / "stops.txt").write_text(stops_content)

        stops = load_stops(tmp_path)

        assert stops["1"].stop_name == "Stop with, comma"
        assert stops["3"].stop_name == "Café & Station"
