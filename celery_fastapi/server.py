"""Server utilities for Celery FastAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gunicorn.app.base import BaseApplication


def create_gunicorn_app(
    app: Any, options: dict[str, Any] | None = None
) -> BaseApplication:
    """Create a Gunicorn application instance.

    Args:
        app: The ASGI application to serve.
        options: Gunicorn configuration options.

    Returns:
        A Gunicorn BaseApplication instance.

    Raises:
        ImportError: If gunicorn is not installed.
    """
    try:
        from gunicorn.app.base import BaseApplication
    except ImportError as exc:
        raise ImportError(
            "gunicorn is not installed. "
            "Install with: pip install celery-fastapi[gunicorn]"
        ) from exc

    class _GunicornApp(BaseApplication):
        """Internal Gunicorn application wrapper."""

        def __init__(
            self, application: Any, gunicorn_options: dict[str, Any] | None = None
        ) -> None:
            self._app = application
            self._options = gunicorn_options or {}
            super().__init__()

        def init(self, parser: Any, opts: Any, args: Any) -> None:
            """Initialize the application (required by BaseApplication)."""

        def load_config(self) -> None:
            """Load configuration from options."""
            config = {
                key: value
                for key, value in self._options.items()
                if key in self.cfg.settings and value is not None
            }
            for key, value in config.items():
                self.cfg.set(key.lower(), value)

        def load(self) -> Any:
            """Return the application."""
            return self._app

    return _GunicornApp(app, options)


class GunicornApplication:
    """Helper class for running FastAPI apps with Gunicorn.

    This class provides a simple interface for running ASGI applications
    with Gunicorn and uvicorn workers.

    Example:
        >>> from celery_fastapi.server import GunicornApplication
        >>> app = create_my_fastapi_app()
        >>> GunicornApplication(app, {"bind": "0.0.0.0:8000", "workers": 4}).run()
    """

    def __init__(self, app: Any, options: dict[str, Any] | None = None) -> None:
        """Initialize the Gunicorn application.

        Args:
            app: The ASGI application to serve.
            options: Gunicorn configuration options. Common options include:
                - bind: Address to bind (e.g., "0.0.0.0:8000")
                - workers: Number of worker processes
                - worker_class: Worker implementation (e.g., "uvicorn.workers.UvicornWorker")
                - timeout: Worker timeout in seconds
                - loglevel: Logging level
        """
        self.application = app
        self.options = options or {}

    def run(self) -> None:
        """Run the Gunicorn server.

        Raises:
            ImportError: If gunicorn is not installed.
        """
        gunicorn_app = create_gunicorn_app(self.application, self.options)
        gunicorn_app.run()
