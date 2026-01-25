import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Stop:
    """A GTFS stop."""

    stop_id: str
    stop_name: str
    lat: float
    lon: float


@dataclass
class TripStopSequence:
    """Ordered stops for a trip with shape points."""

    trip_id: str
    route_id: str
    shape_id: str
    stops: list[tuple[int, Stop]] = field(default_factory=list)  # (sequence, Stop)


def load_stops(gtfs_dir: str | Path) -> dict[str, Stop]:
    """Load stops.txt into a dict keyed by stop_id."""
    stops: dict[str, Stop] = {}
    stops_file = Path(gtfs_dir) / "stops.txt"

    with open(stops_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip stops without coordinates (e.g., parent stations)
            if not row.get("stop_lat") or not row.get("stop_lon"):
                continue
            stop = Stop(
                stop_id=row["stop_id"],
                stop_name=row.get("stop_name", ""),
                lat=float(row["stop_lat"]),
                lon=float(row["stop_lon"]),
            )
            stops[stop.stop_id] = stop

    return stops
