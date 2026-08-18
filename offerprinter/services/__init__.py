"""Service layer: parsing inputs, generating artifacts, and writing outputs."""

from offerprinter.services.cv_parser import extract_cv, extract_cv_from_bytes
from offerprinter.services.generator import Generator
from offerprinter.services.jd_fetcher import load_job_description
from offerprinter.services.writer import write_package

__all__ = [
    "extract_cv",
    "extract_cv_from_bytes",
    "load_job_description",
    "Generator",
    "write_package",
]
