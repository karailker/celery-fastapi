"""Command-line interface for Celery FastAPI."""

from __future__ import annotations

import os
import sys
from enum import Enum
from typing import Annotated, Any

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print(
        "CLI dependencies not installed. "
        "Install with: pip install celery-fastapi[cli]"
    )
    sys.exit(1)


class LogLevel(str, Enum):
    """Log level options."""

    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"
    trace = "trace"


class LoopType(str, Enum):
    """Event loop implementation options."""

    auto = "auto"
    asyncio = "asyncio"
    uvloop = "uvloop"


class HttpProtocol(str, Enum):
    """HTTP protocol implementation options."""

    auto = "auto"
    h11 = "h11"
    httptools = "httptools"


class WsProtocol(str, Enum):
    """WebSocket protocol implementation options."""

    auto = "auto"
    none = "none"
    websockets = "websockets"
    wsproto = "wsproto"


class InterfaceType(str, Enum):
    """ASGI interface version."""

    auto = "auto"
    asgi3 = "asgi3"
    asgi2 = "asgi2"
    wsgi = "wsgi"


app = typer.Typer(
    name="celery-fastapi",
    help="Automatic REST API generation for Celery tasks with FastAPI.",
    add_completion=False,
)
console = Console()


def _create_app_from_env() -> Any:
    """
    Factory function to create FastAPI app from environment variables.

    This is used when running with multiple workers or reload enabled,
    as uvicorn requires an import string in these cases.
    """
    from celery_fastapi.app import create_app

    celery_app = os.environ.get("CELERY_FASTAPI_CELERY_APP")
    prefix = os.environ.get("CELERY_FASTAPI_PREFIX", "")
    root_path = os.environ.get("CELERY_FASTAPI_ROOT_PATH", "")

    if not celery_app:
        raise ValueError("CELERY_FASTAPI_CELERY_APP environment variable not set")

    return create_app(
        celery_app,
        title="Celery FastAPI",
        prefix=prefix,
        fastapi_kwargs={"root_path": root_path} if root_path else None,
    )


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        from celery_fastapi import __version__

        console.print(f"celery-fastapi version: [bold green]{__version__}[/]")
        raise typer.Exit()


@app.command()
def serve(
    celery_app: Annotated[
        str,
        typer.Argument(
            help="Path to Celery app (e.g., 'myapp.celery:app' or 'celery_app:celery_app')"
        ),
    ],
    # Server binding options
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Host to bind the server to"),
    ] = "0.0.0.0",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to bind the server to"),
    ] = 8000,
    uds: Annotated[
        str | None,
        typer.Option("--uds", help="Unix domain socket path to bind to"),
    ] = None,
    fd: Annotated[
        int | None,
        typer.Option("--fd", help="File descriptor to bind to"),
    ] = None,
    # Development options
    reload: Annotated[
        bool,
        typer.Option("--reload", "-r", help="Enable auto-reload for development"),
    ] = False,
    reload_dir: Annotated[
        list[str] | None,
        typer.Option("--reload-dir", help="Directories to watch for reload"),
    ] = None,
    reload_include: Annotated[
        list[str] | None,
        typer.Option("--reload-include", help="Glob patterns to include for reload"),
    ] = None,
    reload_exclude: Annotated[
        list[str] | None,
        typer.Option("--reload-exclude", help="Glob patterns to exclude for reload"),
    ] = None,
    reload_delay: Annotated[
        float,
        typer.Option("--reload-delay", help="Delay between reload checks"),
    ] = 0.25,
    # Worker options
    workers: Annotated[
        int,
        typer.Option("--workers", "-w", help="Number of worker processes"),
    ] = 1,
    # Logging options
    log_level: Annotated[
        LogLevel,
        typer.Option("--log-level", "-l", help="Logging level"),
    ] = LogLevel.info,
    access_log: Annotated[
        bool,
        typer.Option("--access-log/--no-access-log", help="Enable/disable access log"),
    ] = True,
    log_config: Annotated[
        str | None,
        typer.Option("--log-config", help="Path to logging config file"),
    ] = None,
    # Protocol options
    loop: Annotated[
        LoopType,
        typer.Option("--loop", help="Event loop implementation"),
    ] = LoopType.auto,
    http: Annotated[
        HttpProtocol,
        typer.Option("--http", help="HTTP protocol implementation"),
    ] = HttpProtocol.auto,
    ws: Annotated[
        WsProtocol,
        typer.Option("--ws", help="WebSocket protocol implementation"),
    ] = WsProtocol.auto,
    interface: Annotated[
        InterfaceType,
        typer.Option("--interface", help="ASGI interface version"),
    ] = InterfaceType.auto,
    # Connection options
    limit_concurrency: Annotated[
        int | None,
        typer.Option("--limit-concurrency", help="Max concurrent connections"),
    ] = None,
    limit_max_requests: Annotated[
        int | None,
        typer.Option("--limit-max-requests", help="Max requests before worker restart"),
    ] = None,
    backlog: Annotated[
        int,
        typer.Option("--backlog", help="Max queued connections"),
    ] = 2048,
    # Timeout options
    timeout_keep_alive: Annotated[
        int,
        typer.Option("--timeout-keep-alive", help="Keep-alive timeout in seconds"),
    ] = 5,
    timeout_graceful_shutdown: Annotated[
        int | None,
        typer.Option("--timeout-graceful-shutdown", help="Graceful shutdown timeout"),
    ] = None,
    # SSL options
    ssl_keyfile: Annotated[
        str | None,
        typer.Option("--ssl-keyfile", help="SSL key file path"),
    ] = None,
    ssl_certfile: Annotated[
        str | None,
        typer.Option("--ssl-certfile", help="SSL certificate file path"),
    ] = None,
    ssl_keyfile_password: Annotated[
        str | None,
        typer.Option("--ssl-keyfile-password", help="SSL key file password"),
    ] = None,
    ssl_ca_certs: Annotated[
        str | None,
        typer.Option("--ssl-ca-certs", help="SSL CA certificates file"),
    ] = None,
    # Header options
    server_header: Annotated[
        bool,
        typer.Option(
            "--server-header/--no-server-header", help="Include server header"
        ),
    ] = True,
    date_header: Annotated[
        bool,
        typer.Option("--date-header/--no-date-header", help="Include date header"),
    ] = True,
    forwarded_allow_ips: Annotated[
        str | None,
        typer.Option(
            "--forwarded-allow-ips",
            help="Comma-separated IPs to trust for X-Forwarded headers",
        ),
    ] = None,
    # Proxy headers
    proxy_headers: Annotated[
        bool,
        typer.Option("--proxy-headers/--no-proxy-headers", help="Enable proxy headers"),
    ] = True,
    # FastAPI prefix option
    prefix: Annotated[
        str,
        typer.Option("--prefix", help="URL prefix for all endpoints"),
    ] = "",
    # Root path for proxied setups
    root_path: Annotated[
        str,
        typer.Option("--root-path", help="ASGI root_path for apps behind proxies"),
    ] = "",
    # H11 max incomplete event size
    h11_max_incomplete_event_size: Annotated[
        int | None,
        typer.Option(
            "--h11-max-incomplete-event-size", help="H11 max incomplete event size"
        ),
    ] = None,
) -> None:
    """
    Start the FastAPI server with auto-generated Celery task endpoints.

    Supports all uvicorn options for production deployment including:
    - SSL/TLS configuration
    - Worker process management
    - Protocol customization (HTTP/WebSocket implementations)
    - Proxy header handling
    - Connection limits and timeouts

    Examples:
        # Development with auto-reload
        celery-fastapi serve myapp.celery:app --reload

        # Production with multiple workers
        celery-fastapi serve myapp.celery:app -w 4 --host 0.0.0.0

        # With SSL
        celery-fastapi serve myapp.celery:app --ssl-keyfile key.pem --ssl-certfile cert.pem

        # Behind a proxy
        celery-fastapi serve myapp.celery:app --proxy-headers --forwarded-allow-ips '*'
    """
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]Error:[/] uvicorn not installed. "
            "Install with: pip install celery-fastapi[server]"
        )
        raise typer.Exit(1)

    from celery_fastapi.app import create_app, load_celery_app

    console.print(f"[bold blue]Loading Celery app from:[/] {celery_app}")

    try:
        celery_instance = load_celery_app(celery_app)
    except Exception as e:
        console.print(f"[red]Error loading Celery app:[/] {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/] Loaded Celery app: [bold]{celery_instance.main}[/]")

    # Create the FastAPI app
    fastapi_app = create_app(
        celery_instance,
        title=f"Celery FastAPI - {celery_instance.main}",
        prefix=prefix,
        fastapi_kwargs={"root_path": root_path} if root_path else None,
    )

    # Show registered routes
    bridge = fastapi_app.state.celery_bridge
    routes = bridge.get_registered_routes()

    if routes:
        table = Table(title="Registered Endpoints")
        table.add_column("Method", style="cyan")
        table.add_column("Path", style="green")

        for route in routes:
            table.add_row(route["method"], route["path"])

        console.print(table)
    else:
        console.print("[yellow]Warning:[/] No task endpoints registered")

    # Build uvicorn config
    uvicorn_config: dict[str, Any] = {
        "host": host,
        "port": port,
        "reload": reload,
        "workers": workers if not reload else 1,
        "log_level": log_level.value,
        "access_log": access_log,
        "proxy_headers": proxy_headers,
        "server_header": server_header,
        "date_header": date_header,
        "timeout_keep_alive": timeout_keep_alive,
        "backlog": backlog,
        "reload_delay": reload_delay,
    }

    # Add optional parameters
    if uds:
        uvicorn_config["uds"] = uds
    if fd is not None:
        uvicorn_config["fd"] = fd
    if reload_dir:
        uvicorn_config["reload_dirs"] = reload_dir
    if reload_include:
        uvicorn_config["reload_includes"] = reload_include
    if reload_exclude:
        uvicorn_config["reload_excludes"] = reload_exclude
    if log_config:
        uvicorn_config["log_config"] = log_config
    if limit_concurrency:
        uvicorn_config["limit_concurrency"] = limit_concurrency
    if limit_max_requests:
        uvicorn_config["limit_max_requests"] = limit_max_requests
    if timeout_graceful_shutdown:
        uvicorn_config["timeout_graceful_shutdown"] = timeout_graceful_shutdown
    if ssl_keyfile:
        uvicorn_config["ssl_keyfile"] = ssl_keyfile
    if ssl_certfile:
        uvicorn_config["ssl_certfile"] = ssl_certfile
    if ssl_keyfile_password:
        uvicorn_config["ssl_keyfile_password"] = ssl_keyfile_password
    if ssl_ca_certs:
        uvicorn_config["ssl_ca_certs"] = ssl_ca_certs
    if forwarded_allow_ips:
        uvicorn_config["forwarded_allow_ips"] = forwarded_allow_ips
    if h11_max_incomplete_event_size:
        uvicorn_config["h11_max_incomplete_event_size"] = h11_max_incomplete_event_size

    # Protocol options (only if not auto)
    if loop != LoopType.auto:
        uvicorn_config["loop"] = loop.value
    if http != HttpProtocol.auto:
        uvicorn_config["http"] = http.value
    if ws != WsProtocol.auto:
        uvicorn_config["ws"] = ws.value if ws != WsProtocol.none else None
    if interface != InterfaceType.auto:
        uvicorn_config["interface"] = interface.value

    console.print(
        f"\n[bold green]Starting server at http://{host}:{port}[/]" f"{prefix or ''}"
    )
    console.print("[dim]Press CTRL+C to stop[/]\n")

    # Run the server
    # When using workers > 1 or reload, we need to use an import string
    if workers > 1 or reload:
        # Set environment variables for the factory to use
        os.environ["CELERY_FASTAPI_CELERY_APP"] = celery_app
        os.environ["CELERY_FASTAPI_PREFIX"] = prefix
        if root_path:
            os.environ["CELERY_FASTAPI_ROOT_PATH"] = root_path

        # Use the factory function as an import string
        uvicorn.run("celery_fastapi.cli:_create_app_from_env", **uvicorn_config)
    else:
        # Single worker, can use app instance directly
        uvicorn.run(fastapi_app, **uvicorn_config)


@app.command()
def serve_gunicorn(
    celery_app: Annotated[
        str,
        typer.Argument(help="Path to Celery app (e.g., 'myapp.celery:app')"),
    ],
    # Binding options
    bind: Annotated[
        str,
        typer.Option(
            "--bind", "-b", help="Address to bind to (host:port or unix socket)"
        ),
    ] = "0.0.0.0:8000",
    # Worker options
    workers: Annotated[
        int,
        typer.Option("--workers", "-w", help="Number of worker processes"),
    ] = 1,
    worker_class: Annotated[
        str,
        typer.Option(
            "--worker-class",
            "-k",
            help="Worker class (uvicorn.workers.UvicornWorker, gevent, eventlet, etc.)",
        ),
    ] = "uvicorn.workers.UvicornWorker",
    threads: Annotated[
        int,
        typer.Option(
            "--threads", help="Number of threads per worker (for sync workers)"
        ),
    ] = 1,
    worker_connections: Annotated[
        int,
        typer.Option(
            "--worker-connections", help="Max simultaneous clients per worker"
        ),
    ] = 1000,
    max_requests: Annotated[
        int,
        typer.Option(
            "--max-requests", help="Max requests before worker restart (0=disabled)"
        ),
    ] = 0,
    max_requests_jitter: Annotated[
        int,
        typer.Option("--max-requests-jitter", help="Max jitter to add to max-requests"),
    ] = 0,
    # Timeout options
    timeout: Annotated[
        int,
        typer.Option("--timeout", "-t", help="Worker timeout in seconds"),
    ] = 30,
    graceful_timeout: Annotated[
        int,
        typer.Option("--graceful-timeout", help="Graceful worker timeout"),
    ] = 30,
    keepalive: Annotated[
        int,
        typer.Option("--keep-alive", help="Keep-alive timeout in seconds"),
    ] = 2,
    # Logging options
    log_level: Annotated[
        LogLevel,
        typer.Option("--log-level", "-l", help="Logging level"),
    ] = LogLevel.info,
    access_log: Annotated[
        str | None,
        typer.Option("--access-logfile", help="Access log file path (- for stdout)"),
    ] = "-",
    error_log: Annotated[
        str | None,
        typer.Option("--error-logfile", help="Error log file path (- for stderr)"),
    ] = "-",
    capture_output: Annotated[
        bool,
        typer.Option(
            "--capture-output/--no-capture-output", help="Capture stdout/stderr"
        ),
    ] = False,
    # Process options
    daemon: Annotated[
        bool,
        typer.Option("--daemon", "-D", help="Daemonize the process"),
    ] = False,
    pidfile: Annotated[
        str | None,
        typer.Option("--pid", help="PID file path"),
    ] = None,
    user: Annotated[
        str | None,
        typer.Option(
            "--user", "-u", help="Switch worker processes to run as this user"
        ),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option(
            "--group", "-g", help="Switch worker processes to run as this group"
        ),
    ] = None,
    umask: Annotated[
        int,
        typer.Option("--umask", help="File mode creation mask"),
    ] = 0,
    # SSL options
    keyfile: Annotated[
        str | None,
        typer.Option("--keyfile", help="SSL key file path"),
    ] = None,
    certfile: Annotated[
        str | None,
        typer.Option("--certfile", help="SSL certificate file path"),
    ] = None,
    ca_certs: Annotated[
        str | None,
        typer.Option("--ca-certs", help="CA certificates file"),
    ] = None,
    # Misc options
    preload: Annotated[
        bool,
        typer.Option("--preload/--no-preload", help="Preload application code"),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option("--reload", "-r", help="Enable auto-reload for development"),
    ] = False,
    chdir: Annotated[
        str | None,
        typer.Option("--chdir", help="Change to this directory before loading app"),
    ] = None,
    # FastAPI options
    prefix: Annotated[
        str,
        typer.Option("--prefix", help="URL prefix for all endpoints"),
    ] = "",
) -> None:
    """
    Start the FastAPI server using Gunicorn with uvicorn workers.

    This is recommended for production deployments. Supports all Gunicorn options
    including worker management, SSL, logging, and process control.

    Examples:
        # Basic production setup
        celery-fastapi serve-gunicorn myapp.celery:app -w 4

        # With gevent workers
        celery-fastapi serve-gunicorn myapp.celery:app -w 4 -k gevent

        # As a daemon
        celery-fastapi serve-gunicorn myapp.celery:app -w 4 -D --pid /var/run/celery-fastapi.pid
    """
    try:
        import gunicorn.app.base  # noqa: F401
    except ImportError:
        console.print(
            "[red]Error:[/] gunicorn not installed. "
            "Install with: pip install celery-fastapi[gunicorn]"
        )
        raise typer.Exit(1)

    from celery_fastapi.app import create_app, load_celery_app
    from celery_fastapi.server import GunicornApplication

    console.print(f"[bold blue]Loading Celery app from:[/] {celery_app}")

    try:
        celery_instance = load_celery_app(celery_app)
    except Exception as e:
        console.print(f"[red]Error loading Celery app:[/] {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/] Loaded Celery app: [bold]{celery_instance.main}[/]")

    # Create the FastAPI app
    fastapi_app = create_app(
        celery_instance,
        title=f"Celery FastAPI - {celery_instance.main}",
        prefix=prefix,
    )

    # Show registered routes
    bridge = fastapi_app.state.celery_bridge
    routes = bridge.get_registered_routes()

    if routes:
        table = Table(title="Registered Endpoints")
        table.add_column("Method", style="cyan")
        table.add_column("Path", style="green")

        for route in routes:
            table.add_row(route["method"], route["path"])

        console.print(table)

    # Build gunicorn options
    options: dict[str, Any] = {
        "bind": bind,
        "workers": workers,
        "worker_class": worker_class,
        "threads": threads,
        "worker_connections": worker_connections,
        "max_requests": max_requests,
        "max_requests_jitter": max_requests_jitter,
        "timeout": timeout,
        "graceful_timeout": graceful_timeout,
        "keepalive": keepalive,
        "loglevel": log_level.value,
        "capture_output": capture_output,
        "daemon": daemon,
        "umask": umask,
        "preload_app": preload,
        "reload": reload,
    }

    if access_log:
        options["accesslog"] = access_log
    if error_log:
        options["errorlog"] = error_log
    if pidfile:
        options["pidfile"] = pidfile
    if user:
        options["user"] = user
    if group:
        options["group"] = group
    if keyfile:
        options["keyfile"] = keyfile
    if certfile:
        options["certfile"] = certfile
    if ca_certs:
        options["ca_certs"] = ca_certs
    if chdir:
        options["chdir"] = chdir

    console.print(f"\n[bold green]Starting Gunicorn server at {bind}[/]")
    console.print("[dim]Press CTRL+C to stop[/]\n")

    # Run with gunicorn
    GunicornApplication(fastapi_app, options).run()


@app.command()
def routes(
    celery_app: Annotated[
        str,
        typer.Argument(help="Path to Celery app (e.g., 'myapp.celery:app')"),
    ],
    prefix: Annotated[
        str,
        typer.Option("--prefix", help="URL prefix for all endpoints"),
    ] = "",
) -> None:
    """
    List all routes that would be generated for the Celery app.

    Example:
        celery-fastapi routes myapp.celery:app
    """
    from celery_fastapi.app import create_app, load_celery_app

    try:
        celery_instance = load_celery_app(celery_app)
    except Exception as e:
        console.print(f"[red]Error loading Celery app:[/] {e}")
        raise typer.Exit(1)

    fastapi_app = create_app(celery_instance, prefix=prefix)
    bridge = fastapi_app.state.celery_bridge
    routes_list = bridge.get_registered_routes()

    if not routes_list:
        console.print("[yellow]No routes found.[/]")
        console.print(
            "[dim]Make sure your Celery tasks are registered before importing.[/]"
        )
        raise typer.Exit()

    table = Table(title=f"Routes for {celery_instance.main}")
    table.add_column("Method", style="cyan", width=8)
    table.add_column("Path", style="green")

    for route in routes_list:
        table.add_row(route["method"], route["path"])

    console.print(table)
    console.print(f"\n[dim]Total routes: {len(routes_list)}[/]")


@app.command()
def tasks(
    celery_app: Annotated[
        str,
        typer.Argument(help="Path to Celery app (e.g., 'myapp.celery:app')"),
    ],
) -> None:
    """
    List all registered Celery tasks.

    Example:
        celery-fastapi tasks myapp.celery:app
    """
    from celery_fastapi.app import load_celery_app

    try:
        celery_instance = load_celery_app(celery_app)
    except Exception as e:
        console.print(f"[red]Error loading Celery app:[/] {e}")
        raise typer.Exit(1)

    table = Table(title=f"Tasks in {celery_instance.main}")
    table.add_column("Task Name", style="green")
    table.add_column("Queue", style="cyan")

    task_count = 0
    for name, task in celery_instance.tasks.items():
        if name.startswith("celery."):
            continue
        queue = getattr(task, "queue", None) or "default"
        table.add_row(name, queue)
        task_count += 1

    if task_count == 0:
        console.print("[yellow]No custom tasks found.[/]")
        console.print("[dim]Make sure your tasks are registered before importing.[/]")
    else:
        console.print(table)
        console.print(f"\n[dim]Total tasks: {task_count}[/]")


@app.command()
def workers(
    celery_app: Annotated[
        str,
        typer.Argument(help="Path to Celery app (e.g., 'myapp.celery:app')"),
    ],
) -> None:
    """
    Show information about active Celery workers.

    Example:
        celery-fastapi workers myapp.celery:app
    """
    from celery_fastapi.app import load_celery_app

    try:
        celery_instance = load_celery_app(celery_app)
    except Exception as e:
        console.print(f"[red]Error loading Celery app:[/] {e}")
        raise typer.Exit(1)

    inspector = celery_instance.control.inspect()

    # Ping workers
    ping_result = inspector.ping()
    if not ping_result:
        console.print("[yellow]No active workers found.[/]")
        raise typer.Exit()

    # Show workers
    table = Table(title="Active Workers")
    table.add_column("Worker", style="green")
    table.add_column("Status", style="cyan")

    for worker, status in ping_result.items():
        table.add_row(worker, str(status))

    console.print(table)

    # Show stats
    stats = inspector.stats()
    if stats:
        console.print("\n[bold]Worker Statistics:[/]")
        for worker, stat in stats.items():
            console.print(f"\n[cyan]{worker}[/]:")
            console.print(
                f"  Pool: {stat.get('pool', {}).get('implementation', 'N/A')}"
            )
            console.print(
                f"  Processes: {len(stat.get('pool', {}).get('processes', []))}"
            )
            console.print(f"  Total tasks: {stat.get('total', {})}")


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """
    Celery FastAPI - Automatic REST API for Celery tasks.

    Generate FastAPI endpoints for your Celery tasks automatically.
    Supports uvicorn and gunicorn for production deployment.
    """
    pass


if __name__ == "__main__":
    app()
