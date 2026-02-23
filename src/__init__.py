"""Agent Analytics Dashboard - A comprehensive analytics system for AI agents."""

__version__ = "1.0.0"
__author__ = "Agent Analytics Team"
__description__ = "Track AI agent activity across Discord servers and GitHub repositories"

from .config import get_config, load_config
from .database import get_db, Database
from .scoring import get_scoring_engine, ScoringEngine

__all__ = [
    "get_config",
    "load_config", 
    "get_db",
    "Database",
    "get_scoring_engine",
    "ScoringEngine"
]