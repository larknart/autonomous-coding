"""
Feature API Server
==================

Manages the lifecycle of the FastAPI server running in a background thread.
"""

import socket
import threading
import time
from pathlib import Path
from typing import Optional

import uvicorn

from api.database import create_database, set_session_maker
from api.migration import migrate_json_to_sqlite
from api.routes import create_app


class FeatureAPIServer:
    """
    Manages the FastAPI server lifecycle.

    The server runs in a daemon thread and can be started/stopped
    programmatically.
    """

    def __init__(
        self,
        project_dir: Path,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        """
        Initialize the server.

        Args:
            project_dir: Directory containing the project
            host: Host to bind to (default: localhost only)
            port: Port to bind to (default: 8765)
        """
        self.project_dir = Path(project_dir)
        self.host = host
        self.port = port
        self.server: Optional[uvicorn.Server] = None
        self.thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    def start(self) -> None:
        """
        Start the API server in a background thread.

        This method:
        1. Runs migration if feature_list.json exists
        2. Creates the database and tables
        3. Starts uvicorn in a daemon thread
        4. Waits for the server to be ready
        """
        # Create project directory if it doesn't exist
        self.project_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        engine, session_maker = create_database(self.project_dir)
        set_session_maker(session_maker)

        # Run migration if needed
        migrate_json_to_sqlite(self.project_dir, session_maker)

        # Create FastAPI app
        app = create_app(self.project_dir)

        # Configure uvicorn with minimal logging
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)

        # Start in daemon thread
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

        # Wait for server to be ready
        if not self._wait_for_ready(timeout=10.0):
            raise RuntimeError(
                f"Server failed to start on {self.host}:{self.port}"
            )

        print(f"Feature API server running at http://{self.host}:{self.port}")

    def _run_server(self) -> None:
        """Run the uvicorn server (called in thread)."""
        if self.server:
            self.server.run()

    def _wait_for_ready(self, timeout: float = 5.0) -> bool:
        """
        Wait for the server to be ready to accept connections.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=0.5
                ):
                    return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                time.sleep(0.1)
        return False

    def stop(self) -> None:
        """Stop the API server gracefully."""
        if self.server:
            self.server.should_exit = True
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5.0)
            print("Feature API server stopped")

    def is_running(self) -> bool:
        """Check if the server is currently running."""
        if self.thread is None:
            return False
        return self.thread.is_alive()

    @property
    def base_url(self) -> str:
        """Get the base URL of the running server."""
        return f"http://{self.host}:{self.port}"
