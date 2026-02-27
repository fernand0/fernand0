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
}

DEFAULT_BLOGS: dict[str, str] = {
    "fernand0@dev.to": "https://dev.to/feed/fernand0",
    "fernand0@GitHub": "https://fernand0.github.io/feed.xml",
    "Bitácora de fernand0": "https://blog.elmundoesimperfecto.com/atom.xml",
}

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


def fetch_blog_entries(blogs: dict[str, str]) -> dict[str, list[BlogEntry]]:
    """Fetch and parse blog entries from RSS/Atom feeds.

    Args:
        blogs: Dictionary mapping blog names to feed URLs.

    Returns:
        Dictionary mapping blog names to lists of BlogEntry objects.
    """
    result: dict[str, list[BlogEntry]] = {}

    for blog_name, feed_url in blogs.items():
        if not validate_url(feed_url):
            logger.warning("Invalid feed URL for %s: %s", blog_name, feed_url)
            result[blog_name] = []
            continue

        try:
            feed = feedparser.parse(feed_url)
            entries: list[BlogEntry] = []

            for entry in feed.get("entries", []):
                blog_entry = format_blog_entry(entry)
                if blog_entry:
                    entries.append(blog_entry)

            result[blog_name] = entries
            logger.info("Fetched %d entries from %s", len(entries), blog_name)

        except Exception as e:
            logger.error("Failed to fetch feed %s: %s", feed_url, e)
            result[blog_name] = []

    return result


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
    feed_urls: dict[str, str],
) -> str:
    """Format blog entries as Markdown.

    Args:
        blogs: Dictionary of blog entry lists.
        feed_urls: Mapping of blog names to feed URLs.

    Returns:
        Formatted Markdown string.
    """
    entries_md_parts: list[str] = []

    for blog_name, entries in blogs.items():
        if not entries:
            continue

        feed_url = feed_urls.get(blog_name, "")
        parsed = urlsplit(feed_url)
        base_url = "{0.scheme}://{0.netloc}".format(parsed)
        entries_md_parts.append(
            "## " + "[{0}]({1})/".format(blog_name, base_url)
        )

        for entry in entries:
            # Clean up double slashes in URLs
            clean_url = re.sub(r"(?<!:)/{2,}", "/", entry.url)
            entries_md_parts.append(
                "* [{}]({}) - {}".format(entry.title, clean_url, entry.published)
            )

    return "\n\n".join(entries_md_parts)


# --- Main entry point ---

def main() -> None:
    """Main entry point for README generation."""
    config = get_config()
    username = config["github_username"]
    token = config["token"]
    readme_path = pathlib.Path(__file__).parent.resolve() / config["readme_file"]

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
    entries_md = format_blog_entries_md(blogs, DEFAULT_BLOGS)
    rewritten = replace_chunk(rewritten, "blog", entries_md)

    # Write updated README
    readme_path.write_text(rewritten, encoding="utf-8")
    logger.info("README updated successfully")


if __name__ == "__main__":
    main()
