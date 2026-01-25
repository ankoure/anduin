"""GTFS constants and enumerations."""


class GTFSRouteType:
    """GTFS route type values from the official GTFS specification."""

    TRAM = 0  # Tram, Streetcar, Light rail
    SUBWAY = 1  # Subway, Metro
    RAIL = 2  # Rail, Commuter rail, Intercity rail
    BUS = 3  # Bus
    FERRY = 4  # Ferry


DEFAULT_ROUTE_TYPES = [GTFSRouteType.BUS]
"""Default route types to process (buses only)."""

EXCLUDED_ROUTE_NAME_PREFIXES = ["Shuttle-"]
"""Route name prefixes to exclude by default (e.g., shuttle routes)."""

ROUTE_TYPE_NAMES = {
    GTFSRouteType.TRAM: "Tram/Light Rail",
    GTFSRouteType.SUBWAY: "Subway/Metro",
    GTFSRouteType.RAIL: "Rail",
    GTFSRouteType.BUS: "Bus",
    GTFSRouteType.FERRY: "Ferry",
}
"""Friendly names for GTFS route types."""
