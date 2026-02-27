"""Tests for CLI argument parsing."""

import pytest
import sys
from io import StringIO
from build_readme import create_parser, main


class TestCreateParser:
    """Tests for create_parser function."""

    def test_parser_creation(self):
        """Test parser is created correctly."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "build_readme"

    def test_parser_no_args(self):
        """Test parsing with no arguments."""
        parser = create_parser()
        args = parser.parse_args([])
        assert args.dry_run is False
        assert args.verbose is False
        assert args.clear_cache is False
        assert args.config is None
        assert args.stats is False

    def test_parser_dry_run(self):
        """Test --dry-run flag."""
        parser = create_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_parser_verbose(self):
        """Test --verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

    def test_parser_verbose_short(self):
        """Test -v short flag."""
        parser = create_parser()
        args = parser.parse_args(["-v"])
        assert args.verbose is True

    def test_parser_clear_cache(self):
        """Test --clear-cache flag."""
        parser = create_parser()
        args = parser.parse_args(["--clear-cache"])
        assert args.clear_cache is True

    def test_parser_config(self):
        """Test --config flag."""
        parser = create_parser()
        args = parser.parse_args(["--config", "custom.yaml"])
        assert args.config.name == "custom.yaml"

    def test_parser_config_short(self):
        """Test -c short flag."""
        parser = create_parser()
        args = parser.parse_args(["-c", "other.yaml"])
        assert args.config.name == "other.yaml"

    def test_parser_stats(self):
        """Test --stats flag."""
        parser = create_parser()
        args = parser.parse_args(["--stats"])
        assert args.stats is True

    def test_parser_multiple_flags(self):
        """Test multiple flags together."""
        parser = create_parser()
        args = parser.parse_args(["--dry-run", "--verbose", "--stats"])
        assert args.dry_run is True
        assert args.verbose is True
        assert args.stats is True


class TestMainCLI:
    """Tests for main() with CLI arguments."""

    def test_main_clear_cache(self, capsys):
        """Test --clear-cache exits cleanly."""
        sys.argv = ["build_readme", "--clear-cache"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Cleared" in captured.out

    def test_main_stats(self, capsys):
        """Test --stats exits cleanly."""
        sys.argv = ["build_readme", "--stats"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Cache statistics" in captured.out
