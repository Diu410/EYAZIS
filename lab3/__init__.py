"""Laboratory 3: extractive and local generative document summarization."""

from .summarizer import summarize as summarize_extractive
from .generative import GenerativeError, summarize_generative


def summarize(document, language="ru", reference_documents=None,
              max_sentences=10, max_keywords=20, subject_area=None,
              method="extractive"):
    """Select a method; existing calls continue to use sentence extraction."""
    if method not in ("extractive", "generative"):
        raise ValueError("Выберите экстрактивный или генеративный метод")
    implementation = (summarize_generative if method == "generative"
                      else summarize_extractive)
    return implementation(document, language, reference_documents,
                          max_sentences, max_keywords, subject_area)


__all__ = ["summarize", "summarize_extractive", "summarize_generative", "GenerativeError"]
