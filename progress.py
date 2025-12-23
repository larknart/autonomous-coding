"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Now uses the Feature API instead of reading feature_list.json directly.
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path


API_BASE_URL = "http://localhost:8765"
WEBHOOK_URL = os.environ.get("PROGRESS_N8N_WEBHOOK_URL")
PROGRESS_CACHE_FILE = ".progress_cache"


def _api_get(endpoint: str) -> dict:
    """
    Make a GET request to the Feature API.

    Args:
        endpoint: API endpoint (e.g., "/features/stats")

    Returns:
        Parsed JSON response

    Raises:
        Exception if request fails
    """
    url = f"{API_BASE_URL}{endpoint}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def count_passing_tests(project_dir: Path) -> tuple[int, int]:
    """
    Count passing and total tests via the Feature API.

    Args:
        project_dir: Directory containing the project (unused, kept for compatibility)

    Returns:
        (passing_count, total_count)
    """
    try:
        stats = _api_get("/features/stats")
        return stats["passing"], stats["total"]
    except Exception as e:
        # API not available - might be first run before server starts
        # Fall back to checking if database exists
        print(f"[API unavailable in count_passing_tests: {e}]")
        return 0, 0


def send_progress_webhook(passing: int, total: int, project_dir: Path) -> None:
    """Send webhook notification when progress increases."""
    if not WEBHOOK_URL:
        return  # Webhook not configured

    cache_file = project_dir / PROGRESS_CACHE_FILE
    previous = 0
    previous_passing_ids = set()

    # Read previous progress and passing feature IDs
    if cache_file.exists():
        try:
            cache_data = json.loads(cache_file.read_text())
            previous = cache_data.get("count", 0)
            previous_passing_ids = set(cache_data.get("passing_ids", []))
        except Exception:
            previous = 0

    # Only notify if progress increased
    if passing > previous:
        # Find which features are now passing via API
        completed_tests = []
        current_passing_ids = []

        try:
            # Get all passing features
            data = _api_get("/features?passes=true&limit=1000")
            for feature in data.get("features", []):
                feature_id = feature.get("id")
                current_passing_ids.append(feature_id)
                if feature_id not in previous_passing_ids:
                    # This feature is newly passing
                    desc = feature.get("description", f"Feature #{feature_id}")
                    category = feature.get("category", "")
                    if category:
                        completed_tests.append(f"[{category}] {desc}")
                    else:
                        completed_tests.append(desc)
        except Exception as e:
            print(f"[API error getting features: {e}]")

        payload = {
            "event": "test_progress",
            "passing": passing,
            "total": total,
            "percentage": round((passing / total) * 100, 1) if total > 0 else 0,
            "previous_passing": previous,
            "tests_completed_this_session": passing - previous,
            "completed_tests": completed_tests,
            "project": project_dir.name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        try:
            req = urllib.request.Request(
                WEBHOOK_URL,
                data=json.dumps([payload]).encode("utf-8"),  # n8n expects array
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[Webhook notification failed: {e}]")

        # Update cache with count and passing IDs
        cache_file.write_text(
            json.dumps({"count": passing, "passing_ids": current_passing_ids})
        )
    else:
        # Update cache even if no change (for initial state)
        if not cache_file.exists():
            current_passing_ids = []
            try:
                data = _api_get("/features?passes=true&limit=1000")
                for feature in data.get("features", []):
                    current_passing_ids.append(feature.get("id"))
            except Exception:
                pass
            cache_file.write_text(
                json.dumps({"count": passing, "passing_ids": current_passing_ids})
            )


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "INITIALIZER" if is_initializer else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path) -> None:
    """Print a summary of current progress."""
    passing, total = count_passing_tests(project_dir)

    if total > 0:
        percentage = (passing / total) * 100
        print(f"\nProgress: {passing}/{total} tests passing ({percentage:.1f}%)")
        send_progress_webhook(passing, total, project_dir)
    else:
        print("\nProgress: No features in database yet")
