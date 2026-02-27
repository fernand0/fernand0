"""Tests for data fetching functions."""

from unittest.mock import patch, MagicMock
import pytest
from build_readme import (
    fetch_repos,
    fetch_blog_entries,
    fetch_mastodon_posts,
    BlogConfig,
    MastodonConfig,
)
from cache import clear_cache


@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    """Clear cache before each test to ensure clean state."""
    clear_cache()
    yield
    clear_cache()


class TestFetchRepos:
    """Tests for fetch_repos function."""

    def test_fetch_repos_no_token(self):
        """Test fetch with no token returns empty."""
        result = fetch_repos("", "testuser")
        assert result == {"repositories": [], "repositoriesContributedTo": []}

    @patch("build_readme.GraphqlClient")
    def test_fetch_repos_success(self, mock_client_class):
        """Test successful repository fetch."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "data": {
                "user": {
                    "repositories": {
                        "edges": [
                            {
                                "node": {
                                    "name": "test-repo",
                                    "description": "Test",
                                    "url": "https://github.com/user/test-repo",
                                    "pushedAt": "2024-01-15T10:00:00Z",
                                }
                            }
                        ]
                    },
                    "repositoriesContributedTo": {
                        "edges": []
                    },
                }
            }
        }
        mock_client_class.return_value = mock_client

        result = fetch_repos("ghp_" + "a" * 36, "testuser")
        assert len(result["repositories"]) == 1
        assert result["repositories"][0].repo == "test-repo"

    @patch("build_readme.GraphqlClient")
    def test_fetch_repos_api_error(self, mock_client_class):
        """Test API error returns empty."""
        mock_client = MagicMock()
        mock_client.execute.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        result = fetch_repos("ghp_" + "a" * 36, "testuser")
        assert result == {"repositories": [], "repositoriesContributedTo": []}

    @patch("build_readme.GraphqlClient")
    def test_fetch_repos_invalid_response(self, mock_client_class):
        """Test invalid API response returns empty."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {"data": None}
        mock_client_class.return_value = mock_client

        result = fetch_repos("ghp_" + "a" * 36, "testuser")
        assert result == {"repositories": [], "repositoriesContributedTo": []}

    @patch("build_readme.GraphqlClient")
    def test_fetch_repos_deduplication(self, mock_client_class):
        """Test duplicate repositories are filtered."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "data": {
                "user": {
                    "repositories": {
                        "edges": [
                            {
                                "node": {
                                    "name": "same-repo",
                                    "description": "Test",
                                    "url": "https://github.com/user/same-repo",
                                    "pushedAt": "2024-01-15T10:00:00Z",
                                }
                            },
                            {
                                "node": {
                                    "name": "same-repo",
                                    "description": "Test 2",
                                    "url": "https://github.com/user/same-repo",
                                    "pushedAt": "2024-01-16T10:00:00Z",
                                }
                            },
                        ]
                    },
                    "repositoriesContributedTo": {"edges": []},
                }
            }
        }
        mock_client_class.return_value = mock_client

        result = fetch_repos("ghp_" + "a" * 36, "testuser")
        assert len(result["repositories"]) == 1


class TestFetchBlogEntries:
    """Tests for fetch_blog_entries function."""

    @patch("build_readme.feedparser.parse")
    def test_fetch_blog_entries_success(self, mock_parse):
        """Test successful blog fetch."""
        mock_parse.return_value = {
            "entries": [
                {
                    "title": "Test Post",
                    "link": "https://example.com/post",
                    "updated": "2024-01-15T10:00:00Z",
                }
            ]
        }

        blogs = {"Test Blog": BlogConfig(feed_url="https://example.com/feed.xml")}
        result = fetch_blog_entries(blogs)

        assert "Test Blog" in result
        assert len(result["Test Blog"]) == 1
        assert result["Test Blog"][0].title == "Test Post"

    @patch("build_readme.feedparser.parse")
    def test_fetch_blog_entries_empty_feed(self, mock_parse):
        """Test empty feed returns empty list."""
        mock_parse.return_value = {"entries": []}

        blogs = {"Test Blog": BlogConfig(feed_url="https://example.com/feed.xml")}
        result = fetch_blog_entries(blogs)

        assert result["Test Blog"] == []

    @patch("build_readme.feedparser.parse")
    def test_fetch_blog_entries_parse_error(self, mock_parse):
        """Test parse error returns empty list."""
        mock_parse.side_effect = Exception("Parse error")

        blogs = {"Test Blog": BlogConfig(feed_url="https://example.com/feed.xml")}
        result = fetch_blog_entries(blogs)

        assert result["Test Blog"] == []

    def test_fetch_blog_entries_invalid_url(self):
        """Test invalid URL returns empty list."""
        blogs = {"Test Blog": BlogConfig(feed_url="not-a-valid-url")}
        result = fetch_blog_entries(blogs)

        assert result["Test Blog"] == []


class TestFetchMastodonPosts:
    """Tests for fetch_mastodon_posts function."""

    @patch("build_readme.fetch_blog_entries")
    def test_fetch_mastodon_posts(self, mock_fetch_blog):
        """Test Mastodon post fetch."""
        from build_readme import BlogEntry

        mock_fetch_blog.return_value = {
            "mastodon": [
                BlogEntry("Test post", "https://mastodon.social/@user/1", "2024-01-15")
            ]
        }

        config = MastodonConfig(username="user", server="mastodon.social")
        result = fetch_mastodon_posts(config)

        assert len(result) == 1
        assert result[0].title == "Test post"
