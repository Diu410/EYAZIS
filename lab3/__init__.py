"""Laboratory 3: extractive document summarization."""

from .summarizer import summarize
from .ostis_client import save_to_ostis

__all__ = ["summarize", "save_to_ostis"]
