"""
Feature API Package
====================

FastAPI server for managing features in SQLite database.
Replaces the JSON file-based feature_list.json approach.
"""

from api.database import Feature, create_database, get_database_path
from api.server import FeatureAPIServer

__all__ = ["Feature", "create_database", "get_database_path", "FeatureAPIServer"]
