"""
Build README - Self-updating GitHub profile README generator.

Fetches recent GitHub repositories and blog posts to update README.md.
Inspired by https://simonwillison.net/2020/Jul/10/self-updating-profile-readme/
"""

import logging
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import feedparser
from dateutil.parser import parse
from python_graphql_client import GraphqlClient

# --- Configuration ---

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GITHUB_API_VERSION = "2023-12-28"

DEFAULT_CONFIG = {
    "github_username": "fernand0",
    "token_env_var": "FERNAND0_TOKEN",
    "username_env_var": "GITHUB_USERNAME",
    "readme_file": "README.md",
    "max_repositories": 10,
    "max_contributions": 20,
    "max_blog_entries": 5,
    "max_mastodon_posts": 5,
}


@dataclass
class BlogConfig:
    """Configuration for a blog source."""
    feed_url: str
    display_url: str | None = None  # Optional: override display URL


DEFAULT_BLOGS: dict[str, BlogConfig] = {
    "fernand0@dev.to (in English)": BlogConfig(
        feed_url="https://dev.to/feed/fernand0",
        display_url="https://dev.to/fernand0",
    ),
    "fernand0@GitHub (in Spanish)": BlogConfig(
        feed_url="https://fernand0.github.io/feed.xml",
    ),
    "Bitácora de fernand0 (in Spanish)": BlogConfig(
        feed_url="https://blog.elmundoesimperfecto.com/atom.xml",
    ),
}


@dataclass
class MastodonConfig:
    """Configuration for a Mastodon account."""
    username: str
    server: str = "mastodon.social"
    display_url: str | None = None  # Optional: override display URL

    @property
    def feed_url(self) -> str:
        """Generate RSS feed URL for Mastodon posts."""
        return f"https://{self.server}/@{self.username}.rss"

    @property
    def profile_url(self) -> str:
        """Generate profile URL."""
        return f"https://{self.server}/@{self.username}"


DEFAULT_MASTODON: MastodonConfig | None = MastodonConfig(
    username="fernand0",
    server="mastodon.social",
)

REPO_LIMITS = {
    "repositories": 10,
    "repositoriesContributedTo": 20,
}

# --- Logging setup ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- Data classes ---

@dataclass
class RepositoryEntry:
    """Represents a repository entry for the README."""

    repo: str
    description: str
    pushed_at: str
    url: str


@dataclass
class BlogEntry:
    """Represents a blog post entry for the README."""

    title: str
    url: str
    published: str


# --- Helper functions ---

def validate_url(url: str) -> bool:
    """Validate that a URL is well-formed.

    Args:
        url: The URL to validate.

    Returns:
        True if the URL is valid, False otherwise.
    """
    try:
        result = urlsplit(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def get_config() -> dict[str, Any]:
    """Load configuration from environment variables with defaults.

    Returns:
        Configuration dictionary with all required settings.
    """
    config = DEFAULT_CONFIG.copy()
    config["github_username"] = os.environ.get(
        config["username_env_var"],
        config["github_username"],
    )
    config["token"] = os.environ.get(config["token_env_var"], "")
    return config


def replace_chunk(content: str, marker: str, chunk: str) -> str:
    """Replace content between marker comments in the README.

    Args:
        content: The full README content.
        marker: The marker name (e.g., "recent_releases").
        chunk: The new content to insert.

    Returns:
        Updated README content with the replaced chunk.
    """
    pattern = re.compile(
        r"<!-- {} starts -->.*?<!-- {} ends -->".format(marker, marker),
        re.DOTALL,
    )
    new_chunk = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(
        marker, chunk, marker
    )
    return pattern.sub(new_chunk, content)


def make_query(username: str) -> str:
    """Build the GraphQL query for fetching repositories.

    Args:
        username: The GitHub username to query.

    Returns:
        GraphQL query string.
    """
    return f"""
query MyQuery {{
  user(login: "{username}") {{
    repositories(last: {REPO_LIMITS["repositories"]}, orderBy: {{field: UPDATED_AT, direction: ASC}}, privacy: PUBLIC) {{
      edges {{
        node {{
          name
          description
          url
          pushedAt
        }}
      }}
    }}
    repositoriesContributedTo(last: {REPO_LIMITS["contributions"]}, orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
      edges {{
        node {{
          name
          description
          url
          pushedAt
        }}
      }}
    }}
  }}
}}
"""


def format_repository(repo_node: dict[str, Any]) -> RepositoryEntry:
    """Format a repository node from GraphQL response.

    Args:
        repo_node: Repository data from GraphQL API.

    Returns:
        Formatted RepositoryEntry object.
    """
    return RepositoryEntry(
        repo=repo_node["name"],
        description=repo_node["description"] or "No description",
        pushed_at=repo_node["pushedAt"].split("T")[0],
        url=repo_node["url"],
    )


def format_blog_entry(entry: dict[str, Any]) -> BlogEntry | None:
    """Format a blog entry from RSS/Atom feed.

    Args:
        entry: Raw entry from feedparser.

    Returns:
        Formatted BlogEntry object, or None if parsing fails.
    """
    time_published = entry.get("updated", entry.get("published", ""))
    if not time_published:
        return None

    try:
        time_parsed = parse(time_published)
        formatted_date = "{}-{:02}-{:02}".format(
            time_parsed.year, time_parsed.month, time_parsed.day
        )
    except Exception:
        logger.warning("Could not parse date: %s", time_published)
        return None

    return BlogEntry(
        title=entry.get("title", "Untitled"),
        url=entry.get("link", "").split("#")[0],
        published=formatted_date,
    )


# --- Data fetching functions ---

def fetch_repos(oauth_token: str, username: str) -> dict[str, list[RepositoryEntry]]:
    """Fetch repositories and contributions from GitHub API.

    Args:
        oauth_token: GitHub personal access token.
        username: GitHub username to query.

    Returns:
        Dictionary with 'repositories' and 'repositoriesContributedTo' lists.
    """
    if not oauth_token:
        logger.error("GitHub token not provided")
        return {"repositories": [], "repositoriesContributedTo": []}

    client = GraphqlClient(endpoint=GITHUB_GRAPHQL_ENDPOINT)

    try:
        data = client.execute(
            query=make_query(username),
            headers={
                "Authorization": "Bearer {}".format(oauth_token),
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
    except Exception as e:
        logger.error("Failed to fetch repositories: %s", e)
        return {"repositories": [], "repositoriesContributedTo": []}

    if not data or "data" not in data or "user" not in data.get("data", {}):
        logger.error("Invalid response from GitHub API")
        return {"repositories": [], "repositoriesContributedTo": []}

    user_data = data["data"]["user"]
    releases: dict[str, list[RepositoryEntry]] = {
        "repositories": [],
        "repositoriesContributedTo": [],
    }

    seen_repos: set[str] = set()

    for repo in user_data.get("repositories", {}).get("edges", []):
        name = repo["node"]["name"]
        if name not in seen_repos:
            seen_repos.add(name)
            releases["repositories"].append(format_repository(repo["node"]))

    seen_repos = set()
    for repo in user_data.get("repositoriesContributedTo", {}).get("edges", []):
        name = repo["node"]["name"]
        if name not in seen_repos:
            seen_repos.add(name)
            releases["repositoriesContributedTo"].append(format_repository(repo["node"]))

    return releases


def fetch_blog_entries(blogs: dict[str, BlogConfig]) -> dict[str, list[BlogEntry]]:
    """Fetch and parse blog entries from RSS/Atom feeds.

    Args:
        blogs: Dictionary mapping blog names to BlogConfig objects.

    Returns:
        Dictionary mapping blog names to lists of BlogEntry objects.
    """
    result: dict[str, list[BlogEntry]] = {}

    for blog_name, config in blogs.items():
        if not validate_url(config.feed_url):
            logger.warning("Invalid feed URL for %s: %s", blog_name, config.feed_url)
            result[blog_name] = []
            continue

        try:
            feed = feedparser.parse(config.feed_url)
            entries: list[BlogEntry] = []

            for entry in feed.get("entries", []):
                blog_entry = format_blog_entry(entry)
                if blog_entry:
                    entries.append(blog_entry)

            result[blog_name] = entries
            logger.info("Fetched %d entries from %s", len(entries), blog_name)

        except Exception as e:
            logger.error("Failed to fetch feed %s: %s", config.feed_url, e)
            result[blog_name] = []

    return result


def fetch_mastodon_posts(config: MastodonConfig) -> list[BlogEntry]:
    """Fetch recent posts from a Mastodon account via RSS feed.

    Args:
        config: MastodonConfig with username and server.

    Returns:
        List of BlogEntry objects representing Mastodon posts.
    """
    # Reuse fetch_blog_entries with a single-item dict
    blogs_dict = {"mastodon": BlogConfig(feed_url=config.feed_url)}
    result = fetch_blog_entries(blogs_dict)
    posts = result.get("mastodon", [])
    logger.info("Fetched %d posts from Mastodon @%s", len(posts), config.username)
    return posts


# --- Formatting functions ---

def format_repositories_md(
    releases: dict[str, list[RepositoryEntry]],
) -> str:
    """Format repository data as Markdown.

    Args:
        releases: Dictionary of repository lists by category.

    Returns:
        Formatted Markdown string.
    """
    md_parts: list[str] = []

    for name, repo_list in releases.items():
        if not repo_list:
            logger.warning("No repositories found for %s", name)
            continue

        md_parts.append("## " + name)
        repo_list.sort(key=lambda r: r.pushed_at, reverse=True)

        entries = [
            "* [{repo}]({url}),  {description} - {pushed_at}".format(
                repo=r.repo, url=r.url, description=r.description, pushed_at=r.pushed_at
            )
            for r in repo_list
        ]
        md_parts.append("\n".join(entries))

    return "\n\n".join(md_parts)


def format_blog_entries_md(
    blogs: dict[str, list[BlogEntry]],
    blog_configs: dict[str, BlogConfig],
    max_entries: int = 5,
) -> str:
    """Format blog entries as Markdown.

    Args:
        blogs: Dictionary of blog entry lists.
        blog_configs: Dictionary mapping blog names to BlogConfig objects.
        max_entries: Maximum number of entries to include per blog.

    Returns:
        Formatted Markdown string.
    """
    entries_md_parts: list[str] = []

    for blog_name, entries in blogs.items():
        if not entries:
            continue

        config = blog_configs.get(blog_name)
        if config and config.display_url:
            # Use custom display URL if provided
            base_url = config.display_url
        else:
            # Extract domain from feed URL
            feed_url = config.feed_url if config else ""
            parsed = urlsplit(feed_url)
            base_url = "{0.scheme}://{0.netloc}".format(parsed)

        entries_md_parts.append(
            "## " + "[{0}]({1})".format(blog_name, base_url)
        )

        # Limit to max_entries
        for entry in entries[:max_entries]:
            # Clean up double slashes in URLs
            clean_url = re.sub(r"(?<!:)/{2,}", "/", entry.url)
            entries_md_parts.append(
                "* [{}]({}) - {}".format(entry.title, clean_url, entry.published)
            )

    return "\n\n".join(entries_md_parts)


def format_mastodon_posts_md(
    posts: list[BlogEntry],
    config: MastodonConfig,
    max_posts: int = 5,
) -> str:
    """Format Mastodon posts as Markdown.

    Args:
        posts: List of Mastodon post entries.
        config: MastodonConfig with profile information.
        max_posts: Maximum number of posts to include.

    Returns:
        Formatted Markdown string.
    """
    if not posts:
        return ""

    md_parts: list[str] = []
    base_url = config.display_url if config.display_url else config.profile_url
    md_parts.append(f"## [{config.username}@{config.server}]({base_url})")

    for post in posts[:max_posts]:
        clean_url = re.sub(r"(?<!:)/{2,}", "/", post.url)
        md_parts.append(
            "* [{}]({}) - {}".format(post.title, clean_url, post.published)
        )

    return "\n".join(md_parts)


# --- Main entry point ---

def main() -> None:
    """Main entry point for README generation."""
    config = get_config()
    username = config["github_username"]
    token = config["token"]
    readme_path = pathlib.Path(__file__).parent.resolve() / config["readme_file"]
    max_blog_entries = config.get("max_blog_entries", 5)
    max_mastodon_posts = config.get("max_mastodon_posts", 5)

    logger.info("Starting README update for user: %s", username)

    if not readme_path.exists():
        logger.error("README.md not found at %s", readme_path)
        sys.exit(1)

    # Fetch and format repositories
    releases = fetch_repos(token, username)
    md = format_repositories_md(releases)

    readme_contents = readme_path.read_text(encoding="utf-8")
    rewritten = replace_chunk(readme_contents, "recent_releases", md)

    # Fetch and format blog entries
    blogs = fetch_blog_entries(DEFAULT_BLOGS)
    entries_md = format_blog_entries_md(blogs, DEFAULT_BLOGS, max_blog_entries)
    rewritten = replace_chunk(rewritten, "blog", entries_md)

    # Fetch and format Mastodon posts
    if DEFAULT_MASTODON:
        mastodon_posts = fetch_mastodon_posts(DEFAULT_MASTODON)
        mastodon_md = format_mastodon_posts_md(
            mastodon_posts, DEFAULT_MASTODON, max_mastodon_posts
        )
        rewritten = replace_chunk(rewritten, "mastodon", mastodon_md)

    # Write updated README
    readme_path.write_text(rewritten, encoding="utf-8")
    logger.info("README updated successfully")


def test_feeds() -> None:
    """Test fetching blog and Mastodon feeds without updating README."""
    logger.info("Testing feed fetching (no GitHub API, no README write)")

    # Test blog feeds
    blogs = fetch_blog_entries(DEFAULT_BLOGS)
    for blog_name, entries in blogs.items():
        logger.info("%s: %d entries", blog_name, len(entries))
        for entry in entries[:2]:
            logger.info("  - %s (%s)", entry.title, entry.published)

    # Test Mastodon feed
    if DEFAULT_MASTODON:
        posts = fetch_mastodon_posts(DEFAULT_MASTODON)
        logger.info("Mastodon @%s: %d posts", DEFAULT_MASTODON.username, len(posts))
        for post in posts[:2]:
            logger.info("  - %s (%s)", post.title, post.published)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_feeds()
    else:
        main()
