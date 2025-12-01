"""Tests for the CLI module."""

from typer.testing import CliRunner

from celery_fastapi.cli import app

runner = CliRunner()


class TestCLI:
    """Tests for CLI commands."""

    def test_version_flag(self) -> None:
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "celery-fastapi version:" in result.stdout

    def test_help_command(self) -> None:
        """Test --help command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Celery tasks" in result.stdout or "celery-fastapi" in result.stdout

    def test_serve_help(self) -> None:
        """Test serve --help command."""
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "Start the FastAPI server" in result.stdout

    def test_routes_help(self) -> None:
        """Test routes --help command."""
        result = runner.invoke(app, ["routes", "--help"])
        assert result.exit_code == 0
        assert "List all routes" in result.stdout

    def test_tasks_help(self) -> None:
        """Test tasks --help command."""
        result = runner.invoke(app, ["tasks", "--help"])
        assert result.exit_code == 0
        assert "List all registered Celery tasks" in result.stdout

    def test_serve_gunicorn_help(self) -> None:
        """Test serve-gunicorn --help command."""
        result = runner.invoke(app, ["serve-gunicorn", "--help"])
        assert result.exit_code == 0
        assert "Gunicorn" in result.stdout

    def test_workers_help(self) -> None:
        """Test workers --help command."""
        result = runner.invoke(app, ["workers", "--help"])
        assert result.exit_code == 0
        assert "active Celery workers" in result.stdout

    def test_serve_invalid_celery_app(self) -> None:
        """Test serve with invalid Celery app path."""
        result = runner.invoke(app, ["serve", "nonexistent.module:app"])
        assert result.exit_code == 1
        assert "Error loading Celery app" in result.stdout

    def test_routes_invalid_celery_app(self) -> None:
        """Test routes with invalid Celery app path."""
        result = runner.invoke(app, ["routes", "nonexistent.module:app"])
        assert result.exit_code == 1
        assert "Error loading Celery app" in result.stdout

    def test_tasks_invalid_celery_app(self) -> None:
        """Test tasks with invalid Celery app path."""
        result = runner.invoke(app, ["tasks", "nonexistent.module:app"])
        assert result.exit_code == 1
        assert "Error loading Celery app" in result.stdout
