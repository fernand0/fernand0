"""Tests for markdown formatting functions."""

import pytest
from build_readme import (
    replace_chunk,
    format_repository,
    format_blog_entry,
    format_repositories_md,
    format_blog_entries_md,
    format_mastodon_posts_md,
    RepositoryEntry,
    BlogEntry,
    BlogConfig,
    MastodonConfig,
)


class TestReplaceChunk:
    """Tests for replace_chunk function."""

    def test_replace_existing_chunk(self):
        """Test replacing content in existing marker."""
        content = """<!-- test starts -->
old content
<!-- test ends -->"""
        result = replace_chunk(content, "test", "new content")
        assert "<!-- test starts -->" in result
        assert "<!-- test ends -->" in result
        assert "new content" in result
        assert "old content" not in result

    def test_replace_multiline_chunk(self):
        """Test replacing multiline content."""
        content = """<!-- test starts -->
line 1
line 2
<!-- test ends -->"""
        result = replace_chunk(content, "test", "single line")
        assert "single line" in result
        assert "line 1" not in result

    def test_no_marker_present(self):
        """Test when marker doesn't exist."""
        content = "No markers here"
        result = replace_chunk(content, "test", "content")
        # Should return content unchanged when no markers exist
        assert result == content


class TestFormatRepository:
    """Tests for format_repository function."""

    def test_format_repository_with_description(self):
        """Test formatting repository with description."""
        repo_node = {
            "name": "test-repo",
            "description": "A test repository",
            "url": "https://github.com/user/test-repo",
            "pushedAt": "2024-01-15T10:30:00Z",
        }
        result = format_repository(repo_node)
        assert isinstance(result, RepositoryEntry)
        assert result.repo == "test-repo"
        assert result.description == "A test repository"
        assert result.pushed_at == "2024-01-15"
        assert result.url == "https://github.com/user/test-repo"

    def test_format_repository_no_description(self):
        """Test formatting repository without description."""
        repo_node = {
            "name": "test-repo",
            "description": None,
            "url": "https://github.com/user/test-repo",
            "pushedAt": "2024-01-15T10:30:00Z",
        }
        result = format_repository(repo_node)
        assert result.description == "No description"

    def test_format_repository_date_only(self):
        """Test date extraction from pushedAt."""
        repo_node = {
            "name": "test-repo",
            "description": "Test",
            "url": "https://github.com/user/test-repo",
            "pushedAt": "2024-06-20T23:59:59Z",
        }
        result = format_repository(repo_node)
        assert result.pushed_at == "2024-06-20"


class TestFormatBlogEntry:
    """Tests for format_blog_entry function."""

    def test_format_blog_entry_with_updated(self):
        """Test formatting entry with updated field."""
        entry = {
            "title": "Test Post",
            "link": "https://example.com/post",
            "updated": "2024-01-15T10:30:00Z",
        }
        result = format_blog_entry(entry)
        assert isinstance(result, BlogEntry)
        assert result.title == "Test Post"
        assert result.published == "2024-01-15"

    def test_format_blog_entry_with_published(self):
        """Test formatting entry with published field."""
        entry = {
            "title": "Test Post",
            "link": "https://example.com/post",
            "published": "2024-02-20T08:00:00Z",
        }
        result = format_blog_entry(entry)
        assert result.published == "2024-02-20"

    def test_format_blog_entry_no_date(self):
        """Test entry without date returns None."""
        entry = {"title": "Test Post", "link": "https://example.com/post"}
        result = format_blog_entry(entry)
        assert result is None

    def test_format_blog_entry_url_with_anchor(self):
        """Test URL anchor removal."""
        entry = {
            "title": "Test Post",
            "link": "https://example.com/post#comments",
            "updated": "2024-01-15T10:30:00Z",
        }
        result = format_blog_entry(entry)
        assert result.url == "https://example.com/post"

    def test_format_blog_entry_fallback_to_description(self):
        """Test title fallback to description."""
        entry = {
            "description": "Fallback Title",
            "link": "https://example.com/post",
            "updated": "2024-01-15T10:30:00Z",
        }
        result = format_blog_entry(entry)
        assert result.title == "Fallback Title"


class TestFormatRepositoriesMd:
    """Tests for format_repositories_md function."""

    def test_format_single_repository(self):
        """Test formatting single repository."""
        releases = {
            "repositories": [
                RepositoryEntry(
                    repo="test-repo",
                    description="A test",
                    pushed_at="2024-01-15",
                    url="https://github.com/user/test-repo",
                )
            ]
        }
        result = format_repositories_md(releases)
        assert "## repositories" in result
        assert "test-repo" in result
        assert "A test" in result

    def test_format_multiple_repositories_sorted(self):
        """Test repositories are sorted by date."""
        releases = {
            "repositories": [
                RepositoryEntry("repo1", "Desc 1", "2024-01-01", "url1"),
                RepositoryEntry("repo2", "Desc 2", "2024-03-01", "url2"),
                RepositoryEntry("repo3", "Desc 3", "2024-02-01", "url3"),
            ]
        }
        result = format_repositories_md(releases)
        lines = result.split("\n")
        # Most recent should appear first (repo2: March, repo3: Feb, repo1: Jan)
        # Find lines that contain repo entries (start with *)
        repo_lines = [line for line in lines if line.strip().startswith("*")]
        assert len(repo_lines) == 3
        assert "repo2" in repo_lines[0]  # Most recent
        assert "repo3" in repo_lines[1]
        assert "repo1" in repo_lines[2]  # Oldest

    def test_format_empty_repositories(self):
        """Test empty repository list."""
        releases = {"repositories": []}
        result = format_repositories_md(releases)
        assert result == ""


class TestFormatBlogEntriesMd:
    """Tests for format_blog_entries_md function."""

    def test_format_blog_entries(self):
        """Test formatting blog entries."""
        blogs = {
            "Test Blog": [
                BlogEntry("Post 1", "https://example.com/1", "2024-01-15"),
                BlogEntry("Post 2", "https://example.com/2", "2024-01-10"),
            ]
        }
        configs = {
            "Test Blog": BlogConfig(feed_url="https://example.com/feed.xml")
        }
        result = format_blog_entries_md(blogs, configs, max_entries=5)
        assert "[Test Blog]" in result
        assert "Post 1" in result
        assert "Post 2" in result

    def test_format_blog_entries_limited(self):
        """Test entry limit is respected."""
        blogs = {
            "Test Blog": [
                BlogEntry(f"Post {i}", f"https://example.com/{i}", f"2024-01-{i:02d}")
                for i in range(1, 10)
            ]
        }
        configs = {
            "Test Blog": BlogConfig(feed_url="https://example.com/feed.xml")
        }
        result = format_blog_entries_md(blogs, configs, max_entries=3)
        # Count entries (lines starting with *)
        entry_lines = [l for l in result.split("\n") if l.strip().startswith("*")]
        assert len(entry_lines) == 3

    def test_format_blog_custom_display_url(self):
        """Test custom display URL is used."""
        blogs = {"Test Blog": [BlogEntry("Post", "https://example.com/1", "2024-01-15")]}
        configs = {
            "Test Blog": BlogConfig(
                feed_url="https://feed.example.com/feed.xml",
                display_url="https://blog.example.com",
            )
        }
        result = format_blog_entries_md(blogs, configs)
        assert "[Test Blog](https://blog.example.com)" in result


class TestFormatMastodonPostsMd:
    """Tests for format_mastodon_posts_md function."""

    def test_format_mastodon_posts(self):
        """Test formatting Mastodon posts."""
        posts = [
            BlogEntry(
                "Test post content",
                "https://mastodon.social/@user/123",
                "2024-01-15",
            )
        ]
        config = MastodonConfig(username="user", server="mastodon.social")
        result = format_mastodon_posts_md(posts, config, max_posts=5)
        assert "user@mastodon.social" in result
        assert "Test post content" in result

    def test_format_mastodon_posts_empty(self):
        """Test empty posts list."""
        config = MastodonConfig(username="user", server="mastodon.social")
        result = format_mastodon_posts_md([], config)
        assert result == ""

    def test_format_mastodon_posts_limited(self):
        """Test post limit is respected."""
        posts = [
            BlogEntry(f"Post {i}", f"https://mastodon.social/@user/{i}", f"2024-01-{i:02d}")
            for i in range(1, 10)
        ]
        config = MastodonConfig(username="user", server="mastodon.social")
        result = format_mastodon_posts_md(posts, config, max_posts=3)
        entry_lines = [l for l in result.split("\n") if l.strip().startswith("*")]
        assert len(entry_lines) == 3

    def test_format_mastodon_custom_display_url(self):
        """Test custom display URL is used."""
        posts = [BlogEntry("Post", "https://mastodon.social/@user/1", "2024-01-15")]
        config = MastodonConfig(
            username="user",
            server="mastodon.social",
            display_url="https://custom.url",
        )
        result = format_mastodon_posts_md(posts, config)
        assert "(https://custom.url)" in result
