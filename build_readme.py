"""
Build README - Self-updating GitHub profile README generator.

Fetches recent GitHub repositories and blog posts to update README.md.
Inspired by https://simonwillison.net/2020/Jul/10/self-updating-profile-readme/
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any, TypedDict
from urllib.parse import urlsplit

import feedparser
import yaml
from bs4 import BeautifulSoup
from dateutil.parser import parse
from python_graphql_client import GraphqlClient

from cache import get_cache_key, load_cache, save_cache, DEFAULT_TTL

# --- Configuration ---

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GITHUB_API_VERSION = "2023-12-28"


@dataclass
class BlogConfig:
    """Configuration for a blog source."""
    feed_url: str
    display_url: str | None = None  # Optional: override display URL


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


@dataclass
class Config:
    """Application configuration loaded from config.yaml."""
    github_username: str
    token_env_var: str
    readme_file: str
    max_repositories: int
    max_contributions: int
    max_blog_entries: int
    max_mastodon_posts: int
    blogs: dict[str, BlogConfig]
    mastodon: MastodonConfig | None = None

    @property
    def token(self) -> str:
        """Get GitHub token from environment variable."""
        return os.environ.get(self.token_env_var, "")


DEFAULT_CONFIG = Config(
    github_username="fernand0",
    token_env_var="FERNAND0_TOKEN",
    readme_file="README.md",
    max_repositories=10,
    max_contributions=20,
    max_blog_entries=5,
    max_mastodon_posts=5,
    blogs={
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
    },
    mastodon=MastodonConfig(username="fernand0", server="mastodon.social"),
)


REPO_LIMITS: dict[str, int] = {
    "repositories": 10,
    "repositoriesContributedTo": 20,
}

# Logger instance (configured in main())
logger = logging.getLogger(__name__)


# --- Type definitions ---


class TokenValidationError(Exception):
    """Raised when GitHub token validation fails."""
    pass


class GraphQLRepoNode(TypedDict, total=False):
    """Type for a repository node in GraphQL response."""
    name: str
    description: str | None
    url: str
    pushedAt: str


class GraphQLRepoEdge(TypedDict):
    """Type for a repository edge in GraphQL response."""
    node: GraphQLRepoNode


class GraphQLRepoConnection(TypedDict, total=False):
    """Type for a repository connection in GraphQL response."""
    edges: list[GraphQLRepoEdge]


class GraphQLUser(TypedDict, total=False):
    """Type for user data in GraphQL response."""
    repositories: GraphQLRepoConnection
    repositoriesContributedTo: GraphQLRepoConnection


class GraphQLData(TypedDict):
    """Type for GraphQL response data."""
    user: GraphQLUser | None


class GraphQLResponse(TypedDict, total=False):
    """Type for GraphQL API response."""
    data: GraphQLData | None


class FeedEntry(TypedDict, total=False):
    """Type for feedparser entry."""
    title: str
    description: str
    link: str
    published: str
    updated: str


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


def load_config(config_path: pathlib.Path | None = None) -> Config:
    """Load configuration from config.yaml file.

    Falls back to DEFAULT_CONFIG if file doesn't exist or is invalid.

    Args:
        config_path: Optional path to config file. Defaults to config.yaml
                    in the same directory as this script.

    Returns:
        Config object with all configuration settings.
    """
    if config_path is None:
        config_path = pathlib.Path(__file__).parent / "config.yaml"

    if not config_path.exists():
        logger.info("Config file not found at %s, using defaults", config_path)
        return DEFAULT_CONFIG

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning("Config file is empty, using defaults")
            return DEFAULT_CONFIG

        # Parse blogs configuration
        blogs: dict[str, BlogConfig] = {}
        blogs_data = data.get("blogs", {})
        for blog_name, blog_config in blogs_data.items():
            if isinstance(blog_config, dict):
                blogs[blog_name] = BlogConfig(
                    feed_url=blog_config.get("feed_url", ""),
                    display_url=blog_config.get("display_url"),
                )

        # Parse Mastodon configuration
        mastodon: MastodonConfig | None = None
        mastodon_data = data.get("mastodon")
        if mastodon_data and isinstance(mastodon_data, dict):
            mastodon = MastodonConfig(
                username=mastodon_data.get("username", ""),
                server=mastodon_data.get("server", "mastodon.social"),
                display_url=mastodon_data.get("display_url"),
            )

        # Parse GitHub configuration
        github_data = data.get("github", {})
        readme_data = data.get("readme", {})

        config = Config(
            github_username=github_data.get("username", DEFAULT_CONFIG.github_username),
            token_env_var=github_data.get("token_env_var", DEFAULT_CONFIG.token_env_var),
            readme_file=readme_data.get("file", DEFAULT_CONFIG.readme_file),
            max_repositories=readme_data.get(
                "max_repositories", DEFAULT_CONFIG.max_repositories
            ),
            max_contributions=readme_data.get(
                "max_contributions", DEFAULT_CONFIG.max_contributions
            ),
            max_blog_entries=readme_data.get(
                "max_blog_entries", DEFAULT_CONFIG.max_blog_entries
            ),
            max_mastodon_posts=readme_data.get(
                "max_mastodon_posts", DEFAULT_CONFIG.max_mastodon_posts
            ),
            blogs=blogs if blogs else DEFAULT_CONFIG.blogs,
            mastodon=mastodon if mastodon else DEFAULT_CONFIG.mastodon,
        )

        logger.info("Configuration loaded from %s", config_path)
        return config

    except yaml.YAMLError as e:
        logger.error("Error parsing config file: %s. Using defaults.", e)
        return DEFAULT_CONFIG
    except Exception as e:
        logger.error("Error loading config file: %s. Using defaults.", e)
        return DEFAULT_CONFIG


def validate_token_format(token: str) -> bool:
    """Validate GitHub token format.

    GitHub tokens have specific formats:
    - Classic: ghp_ followed by 36 alphanumeric characters
    - Fine-grained: github_pat_ followed by alphanumeric string

    Args:
        token: The token to validate.

    Returns:
        True if the token format is valid, False otherwise.
    """
    if not token:
        return False

    # Classic personal access token (ghp_)
    classic_pattern = re.compile(r"^ghp_[a-zA-Z0-9]{36}$")
    # Fine-grained personal access token (github_pat_)
    fine_grained_pattern = re.compile(r"^github_pat_[a-zA-Z0-9_]+$")

    return bool(classic_pattern.match(token) or fine_grained_pattern.match(token))


def validate_token(token: str, username: str) -> None:
    """Validate GitHub token by making a test API call.

    Args:
        token: The GitHub personal access token.
        username: The GitHub username to verify access for.

    Raises:
        TokenValidationError: If the token is invalid or lacks required permissions.
    """
    if not token:
        raise TokenValidationError(
            f"GitHub token is missing. Set the {DEFAULT_CONFIG.token_env_var} "
            f"environment variable with a valid personal access token.\n"
            f"Create one at: https://github.com/settings/tokens\n"
            f"Required scope: public_repo (or repo for private repos)"
        )

    if not validate_token_format(token):
        raise TokenValidationError(
            f"GitHub token format is invalid.\n"
            f"Classic tokens start with 'ghp_' followed by 36 characters.\n"
            f"Fine-grained tokens start with 'github_pat_'.\n"
            f"Please check your token is correctly set in the environment."
        )

    # Test the token with a lightweight API call
    client = GraphqlClient(endpoint=GITHUB_GRAPHQL_ENDPOINT)
    test_query = """
    query ValidateToken {
      viewer {
        login
        name
      }
    }
    """

    try:
        response = client.execute(
            query=test_query,
            headers={
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
    except Exception as e:
        raise TokenValidationError(
            f"Failed to connect to GitHub API: {e}\n"
            f"Check your network connection and token validity."
        ) from e

    if not response or "data" not in response or not response.get("data") or not response["data"].get("viewer"):
        raise TokenValidationError(
            "GitHub token is invalid or expired.\n"
            "Please generate a new token at: https://github.com/settings/tokens"
        )

    viewer_login = response["data"]["viewer"]["login"]
    if viewer_login.lower() != username.lower():
        logger.warning(
            "Token belongs to user '%s' but GITHUB_USERNAME is '%s'. "
            "This may cause permission issues.",
            viewer_login,
            username,
        )

    logger.info("GitHub token validated successfully for user: %s", viewer_login)

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


def get_config(config_path: pathlib.Path | None = None) -> Config:
    """Load configuration from config.yaml or environment variables.

    Args:
        config_path: Optional path to configuration file.

    Returns:
        Config object with all configuration settings.
    """
    return load_config(config_path)


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
    repositoriesContributedTo(last: {REPO_LIMITS["repositoriesContributedTo"]}, orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
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


def format_repository(repo_node: GraphQLRepoNode) -> RepositoryEntry:
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


def format_blog_entry(entry: FeedEntry) -> BlogEntry | None:
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

    url = entry.get("link", "").split("#")[0]
    return BlogEntry(
        title=entry.get("title", entry.get("description", "")),
        url=url,
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

    # Check cache first
    cache_key = get_cache_key("github", {"username": username, "query": make_query(username)})
    cached_data = load_cache(cache_key)
    if cached_data is not None:
        logger.info("Using cached GitHub API response")
        return _convert_cached_repos(cached_data)

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

    if not data or "data" not in data or not data.get("data") or "user" not in data.get("data", {}):
        logger.error("Invalid response from GitHub API")
        return {"repositories": [], "repositoriesContributedTo": []}

    # Save to cache
    save_cache(cache_key, data, DEFAULT_TTL["github"])

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


def _convert_cached_repos(data: dict[str, Any]) -> dict[str, list[RepositoryEntry]]:
    """Convert cached GitHub API response to RepositoryEntry objects.

    Args:
        data: Cached API response data.

    Returns:
        Dictionary with repository lists.
    """
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

        # Check cache first
        cache_key = get_cache_key("blog", {"feed_url": config.feed_url})
        cached_data = load_cache(cache_key)
        if cached_data is not None:
            logger.info("Using cached feed for %s", blog_name)
            result[blog_name] = _convert_cached_blog_entries(cached_data)
            continue

        try:
            feed = feedparser.parse(config.feed_url)
            entries: list[BlogEntry] = []

            for entry in feed.get("entries", []):
                blog_entry = format_blog_entry(entry)
                if blog_entry:
                    entries.append(blog_entry)

            result[blog_name] = entries
            
            # Save to cache
            save_cache(cache_key, {"entries": feed.get("entries", [])}, DEFAULT_TTL["blog"])
            
            logger.info("Fetched %d entries from %s", len(entries), blog_name)

        except Exception as e:
            logger.error("Failed to fetch feed %s: %s", config.feed_url, e)
            result[blog_name] = []

    return result


def _convert_cached_blog_entries(data: dict[str, Any]) -> list[BlogEntry]:
    """Convert cached feed entries to BlogEntry objects.

    Args:
        data: Cached feed data with 'entries' key.

    Returns:
        List of BlogEntry objects.
    """
    entries: list[BlogEntry] = []
    for entry in data.get("entries", []):
        blog_entry = format_blog_entry(entry)
        if blog_entry:
            entries.append(blog_entry)
    return entries


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
        text = "* [{}]({}) - {}".format(post.title, clean_url, post.published)
        soup = BeautifulSoup(text, "html.parser")
        for span in soup.find_all("span"):
            span.unwrap()
        for p in soup.find_all("p"):
            p.unwrap()
        md_parts.append(str(soup))

    return "\n".join(md_parts)


# --- Main entry point ---

def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="build_readme",
        description="Self-updating GitHub profile README generator",
        epilog="Examples:\n"
               "  %(prog)s                    # Run with default config\n"
               "  %(prog)s --dry-run          # Preview without writing\n"
               "  %(prog)s --verbose          # Show debug output\n"
               "  %(prog)s --clear-cache      # Clear API cache\n"
               "  %(prog)s --config custom.yaml  # Use custom config\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate README content but don't write to file",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug output",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the API response cache and exit",
    )

    parser.add_argument(
        "--config", "-c",
        type=pathlib.Path,
        metavar="FILE",
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics and exit",
    )

    return parser


def main() -> None:
    """Main entry point for README generation."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle --clear-cache
    if args.clear_cache:
        from cache import clear_cache
        cleared = clear_cache()
        print(f"Cleared {cleared} cache file(s)")
        sys.exit(0)

    # Handle --stats
    if args.stats:
        from cache import get_cache_stats
        stats = get_cache_stats()
        print(f"Cache statistics:")
        print(f"  Files: {stats['files']}")
        print(f"  Size: {stats['size_kb']} KB")
        sys.exit(0)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Load configuration
    config = get_config(args.config) if args.config else get_config()
    username = config.github_username
    token = config.token
    readme_path = pathlib.Path(__file__).parent.resolve() / config.readme_file
    max_blog_entries = config.max_blog_entries
    max_mastodon_posts = config.max_mastodon_posts

    logger.info("Starting README update for user: %s", username)

    # Validate token before any operations
    try:
        validate_token(token, username)
    except TokenValidationError as e:
        logger.error("Token validation failed: %s", e)
        sys.exit(1)

    if not readme_path.exists():
        logger.error("README.md not found at %s", readme_path)
        sys.exit(1)

    # Fetch and format repositories
    releases = fetch_repos(token, username)
    md = format_repositories_md(releases)

    readme_contents = readme_path.read_text(encoding="utf-8")
    rewritten = replace_chunk(readme_contents, "recent_releases", md)

    # Fetch and format blog entries
    blogs = fetch_blog_entries(config.blogs)
    entries_md = format_blog_entries_md(blogs, config.blogs, max_blog_entries)
    rewritten = replace_chunk(rewritten, "blog", entries_md)

    # Fetch and format Mastodon posts
    if config.mastodon:
        mastodon_posts = fetch_mastodon_posts(config.mastodon)
        mastodon_md = format_mastodon_posts_md(
            mastodon_posts, config.mastodon, max_mastodon_posts
        )
        rewritten = replace_chunk(rewritten, "mastodon", mastodon_md)

    # Write updated README (or preview in dry-run mode)
    if args.dry_run:
        print("=== DRY RUN: Generated README content ===")
        print(rewritten[:500] + "..." if len(rewritten) > 500 else rewritten)
        print("=== End of preview ===")
        logger.info("Dry run complete (no files written)")
    else:
        readme_path.write_text(rewritten, encoding="utf-8")
        logger.info("README updated successfully")


def test_feeds() -> None:
    """Test fetching blog and Mastodon feeds without updating README.

    This function skips GitHub API calls and token validation,
    making it useful for testing feed configuration without
    requiring a GitHub token.
    """
    logger.info("Testing feed fetching (no GitHub API, no README write)")

    # Load configuration
    config = get_config()

    # Test blog feeds
    blogs = fetch_blog_entries(config.blogs)
    for blog_name, entries in blogs.items():
        logger.info("%s: %d entries", blog_name, len(entries))
        for entry in entries[:2]:
            logger.info("  - %s (%s)", entry.title, entry.published)

    # Test Mastodon feed
    if config.mastodon:
        posts = fetch_mastodon_posts(config.mastodon)
        logger.info(
            "Links shared in Mastodon @%s: %d posts (and other social networks)",
            config.mastodon.username,
            len(posts),
        )
        for post in posts[:2]:
            logger.info("  - %s (%s)", post.title, post.published)


if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()

    # Handle special commands
    if args.clear_cache:
        from cache import clear_cache
        cleared = clear_cache()
        print(f"Cleared {cleared} cache file(s)")
        sys.exit(0)

    if args.stats:
        from cache import get_cache_stats
        stats = get_cache_stats()
        print(f"Cache statistics:")
        print(f"  Files: {stats['files']}")
        print(f"  Size: {stats['size_kb']} KB")
        sys.exit(0)

    # Run test feeds mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_feeds()
    else:
        main()
