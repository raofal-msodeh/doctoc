"""
DocToc error hierarchy.

DocToc distinguishes three failure classes, each mapping to a distinct
CLI exit code so scripts and CI pipelines can react appropriately:

* ``TocInputError``   -- the caller's problem (bad path, bad options,
                         unsupported file). Exit code 2.
* ``TocEngineError``  -- internal processing failure that is not caused
                         by caller input. Exit code 3.
"""

from __future__ import annotations


class DocTocError(Exception):
    """Base class for all DocToc errors."""


class TocInputError(DocTocError):
    """Raised when the caller provides bad input (paths, options, file)."""


class TocEngineError(DocTocError):
    """Raised when internal processing fails for reasons outside caller input."""
