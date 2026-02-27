"""Tests for configuration loading."""

import tempfile
import pytest
from pathlib import Path
from build_readme import load_config, Config, DEFAULT_CONFIG


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_file_not_found(self):
        """Test loading when config file doesn't exist."""
        config = load_config(Path("/nonexistent/config.yaml"))
        assert config == DEFAULT_CONFIG

    def test_load_config_valid(self):
        """Test loading valid configuration file."""
        config_content = """
github:
  username: "testuser"
  token_env_var: "TEST_TOKEN"

readme:
  file: "README.md"
  max_repositories: 5
  max_blog_entries: 3

blogs:
  "Test Blog":
    feed_url: "https://test.com/feed.xml"
    display_url: "https://test.com"

mastodon:
  username: "testuser"
  server: "mastodon.example.com"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)

            assert isinstance(config, Config)
            assert config.github_username == "testuser"
            assert config.token_env_var == "TEST_TOKEN"
            assert config.readme_file == "README.md"
            assert config.max_repositories == 5
            assert config.max_blog_entries == 3
            assert "Test Blog" in config.blogs
            assert config.blogs["Test Blog"].feed_url == "https://test.com/feed.xml"
            assert config.mastodon is not None
            assert config.mastodon.username == "testuser"
            assert config.mastodon.server == "mastodon.example.com"
        finally:
            config_path.unlink()

    def test_load_config_empty_file(self):
        """Test loading empty configuration file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config == DEFAULT_CONFIG
        finally:
            config_path.unlink()

    def test_load_config_invalid_yaml(self):
        """Test loading invalid YAML file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("invalid: yaml: content: [")
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config == DEFAULT_CONFIG
        finally:
            config_path.unlink()

    def test_load_config_partial(self):
        """Test loading partial configuration (missing sections)."""
        config_content = """
github:
  username: "partialuser"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)

            assert config.github_username == "partialuser"
            # Other values should fall back to defaults
            assert config.token_env_var == DEFAULT_CONFIG.token_env_var
            assert config.blogs == DEFAULT_CONFIG.blogs
        finally:
            config_path.unlink()

    def test_load_config_no_mastodon(self):
        """Test loading configuration without Mastodon."""
        config_content = """
github:
  username: "testuser"

blogs:
  "Test Blog":
    feed_url: "https://test.com/feed.xml"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)

            # Should use default Mastodon config
            assert config.mastodon == DEFAULT_CONFIG.mastodon
        finally:
            config_path.unlink()
