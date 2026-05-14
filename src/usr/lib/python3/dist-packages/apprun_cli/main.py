"""Command-suite entry point for AppRun.

This module is intentionally tiny.  It gives the executable a stable import
target while the implementation can continue splitting into focused command
modules behind this boundary.
"""

from .command import main

__all__ = ["main"]

