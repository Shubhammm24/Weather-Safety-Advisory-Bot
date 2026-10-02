"""
Session-level stores for user coordinates and facts.

Kept in a separate module to avoid circular imports between
build.py and nodes.py.
"""

from __future__ import annotations

from typing import Optional


# Module-level user coords store (browser geolocation)
_user_coords_store: dict[str, dict] = {}


def set_user_coords(session_id: str, coords: dict) -> None:
    """Store user coords for a session."""
    _user_coords_store[session_id] = coords


def get_user_coords(session_id: str) -> Optional[dict]:
    """Get stored user coords for a session."""
    return _user_coords_store.get(session_id)


def clear_user_coords(session_id: str) -> None:
    """Clear stored user coords for a session."""
    _user_coords_store.pop(session_id, None)
