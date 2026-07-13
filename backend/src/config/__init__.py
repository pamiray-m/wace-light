"""
src.config — AOS configuration package.

Public API
----------
get_settings()          Build a Settings object from the current environment.
validate_settings(s)    Assert required fields; raise ConfigurationError on failure.
ConfigurationError      Raised by validate_settings() on invalid config.
Settings                Top-level config aggregate (frozen Pydantic model).
"""

from src.config.loader import ConfigurationError, get_settings, validate_settings
from src.config.models import Settings

__all__ = [
    "ConfigurationError",
    "get_settings",
    "Settings",
    "validate_settings",
]
