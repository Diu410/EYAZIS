"""Import path for the laboratory package stored in ``lab 5-7``."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().with_name("lab 5-7"))]
__package__ = __name__
__spec__.submodule_search_locations = __path__
