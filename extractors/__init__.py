"""AM4 data extraction into SQLite."""

from extractors.aircraft import extract_all_aircraft
from extractors.airports import extract_all_airports
from extractors.routes import run_bulk_extraction

__all__ = ["extract_all_aircraft", "extract_all_airports", "run_bulk_extraction"]
