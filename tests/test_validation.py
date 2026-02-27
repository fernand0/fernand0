"""Tests for validation functions."""

import pytest
from unittest.mock import MagicMock, patch
from build_readme import (
    validate_token_format,
    validate_url,
    validate_token,
    TokenValidationError,
)


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        assert validate_url("https://example.com") is True
        assert validate_url("https://dev.to/feed/fernand0") is True

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        assert validate_url("http://example.com") is True

    def test_invalid_url_no_scheme(self):
        """Test URL without scheme."""
        assert validate_url("example.com") is False

    def test_invalid_url_no_netloc(self):
        """Test URL without network location."""
        assert validate_url("https://") is False

    def test_empty_url(self):
        """Test empty URL."""
        assert validate_url("") is False

    def test_malformed_url(self):
        """Test malformed URL."""
        assert validate_url("not a url") is False


class TestValidateTokenFormat:
    """Tests for validate_token_format function."""

    def test_valid_classic_token(self):
        """Test valid classic GitHub token (ghp_)."""
        token = "ghp_" + "a" * 36
        assert validate_token_format(token) is True

    def test_valid_fine_grained_token(self):
        """Test valid fine-grained GitHub token (github_pat_)."""
        token = "github_pat_abc123_xyz789"
        assert validate_token_format(token) is True

    def test_invalid_token_no_prefix(self):
        """Test token without valid prefix."""
        assert validate_token_format("invalid_token") is False
        assert validate_token_format("abc123") is False

    def test_invalid_classic_token_wrong_length(self):
        """Test classic token with wrong length."""
        assert validate_token_format("ghp_" + "a" * 30) is False
        assert validate_token_format("ghp_" + "a" * 40) is False

    def test_invalid_token_empty(self):
        """Test empty token."""
        assert validate_token_format("") is False
        assert validate_token_format(None) is False

    def test_invalid_token_similar_prefix(self):
        """Test token with similar but invalid prefix."""
        assert validate_token_format("ghp_wrong") is False
        assert validate_token_format("github_pat") is False


class TestValidateToken:
    """Tests for validate_token function."""

    def test_validate_token_missing(self):
        """Test missing token raises error."""
        with pytest.raises(TokenValidationError) as exc_info:
            validate_token("", "testuser")
        assert "GitHub token is missing" in str(exc_info.value)

    def test_validate_token_invalid_format(self):
        """Test invalid format raises error."""
        with pytest.raises(TokenValidationError) as exc_info:
            validate_token("invalid_token", "testuser")
        assert "format is invalid" in str(exc_info.value)

    @patch("build_readme.GraphqlClient")
    def test_validate_token_success(self, mock_client_class):
        """Test successful token validation."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "data": {"viewer": {"login": "testuser", "name": "Test User"}}
        }
        mock_client_class.return_value = mock_client

        # Should not raise
        validate_token("ghp_" + "a" * 36, "testuser")

    @patch("build_readme.GraphqlClient")
    def test_validate_token_api_error(self, mock_client_class):
        """Test API error raises TokenValidationError."""
        mock_client = MagicMock()
        mock_client.execute.side_effect = Exception("Connection failed")
        mock_client_class.return_value = mock_client

        with pytest.raises(TokenValidationError) as exc_info:
            validate_token("ghp_" + "a" * 36, "testuser")
        assert "Failed to connect" in str(exc_info.value)

    @patch("build_readme.GraphqlClient")
    def test_validate_token_invalid_response(self, mock_client_class):
        """Test invalid API response raises error."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {"data": None}
        mock_client_class.return_value = mock_client

        with pytest.raises(TokenValidationError) as exc_info:
            validate_token("ghp_" + "a" * 36, "testuser")
        assert "invalid or expired" in str(exc_info.value)

    @patch("build_readme.GraphqlClient")
    def test_validate_token_username_mismatch(self, mock_client_class, caplog):
        """Test username mismatch logs warning."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "data": {"viewer": {"login": "otheruser", "name": "Other"}}
        }
        mock_client_class.return_value = mock_client

        import logging
        caplog.set_level(logging.WARNING)
        validate_token("ghp_" + "a" * 36, "testuser")

        assert "Token belongs to user 'otheruser'" in caplog.text
