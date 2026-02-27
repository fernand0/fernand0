from python_graphql_client import GraphqlClient
import feedparser
import logging
import os
import pathlib
import re
import sys
from urllib.parse import urlsplit

from dateutil.parser import parse

# Inspired by https://simonwillison.net/2020/Jul/10/self-updating-profile-readme/

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("FERNAND0_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "fernand0")

DEFAULT_BLOGS = {
    "fernand0@GitHub": "https://fernand0.github.io/feed.xml",
    "Bitácora de fernand0": "https://blog.elmundoesimperfecto.com/atom.xml",
}


def validate_url(url: str) -> bool:
    """Validate that a URL is well-formed."""
    try:
        result = urlsplit(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def replace_chunk(content: str, marker: str, chunk: str) -> str:
    """Replace content between marker comments in the README."""
    pattern = re.compile(
        r"<!-- {} starts -->.*?<!-- {} ends -->".format(marker, marker),
        re.DOTALL,
    )
    new_chunk = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(marker, chunk, marker)
    return pattern.sub(new_chunk, content)


def make_query(username: str, after_cursor: str | None = None) -> str:
    """Build the GraphQL query for fetching repositories."""
    cursor = '"{}"'.format(after_cursor) if after_cursor else "null"
    return f"""
query MyQuery {{
  user(login: "{username}") {{
    repositories(last: 10, orderBy: {{field: UPDATED_AT, direction: ASC}}, privacy: PUBLIC) {{
      edges {{
        node {{
          name
          description
          url
          pushedAt
        }}
      }}
    }}
    repositoriesContributedTo(last: 20, orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
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


def fetch_repos(oauth_token: str, username: str) -> dict:
    """Fetch repositories and contributions from GitHub API."""
    if not oauth_token:
        logger.error("GitHub token not provided")
        return {"repositories": [], "repositoriesContributedTo": []}

    try:
        data = client.execute(
            query=make_query(username),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
    except Exception as e:
        logger.error("Failed to fetch repositories: %s", e)
        return {"repositories": [], "repositoriesContributedTo": []}

    if not data or "data" not in data or "user" not in data.get("data", {}):
        logger.error("Invalid response from GitHub API")
        return {"repositories": [], "repositoriesContributedTo": []}

    user_data = data["data"]["user"]
    releases = {"repositories": [], "repositoriesContributedTo": []}

    seen_repos = set()
    for repo in user_data.get("repositories", {}).get("edges", []):
        name = repo["node"]["name"]
        if name not in seen_repos:
            seen_repos.add(name)
            releases["repositories"].append({
                "repo": name,
                "description": repo["node"]["description"] or "No description",
                "pushed_at": repo["node"]["pushedAt"].split("T")[0],
                "url": repo["node"]["url"],
            })

    seen_repos = set()
    for repo in user_data.get("repositoriesContributedTo", {}).get("edges", []):
        name = repo["node"]["name"]
        if name not in seen_repos:
            seen_repos.add(name)
            releases["repositoriesContributedTo"].append({
                "repo": name,
                "description": repo["node"]["description"] or "No description",
                "pushed_at": repo["node"]["pushedAt"].split("T")[0],
                "url": repo["node"]["url"],
            })

    return releases


def fetch_blog_entries(blogs: dict) -> dict:
    """Fetch and parse blog entries from RSS/Atom feeds."""
    result = {}
    for blog_name, feed_url in blogs.items():
        if not validate_url(feed_url):
            logger.warning("Invalid feed URL for %s: %s", blog_name, feed_url)
            result[blog_name] = []
            continue

        try:
            feed = feedparser.parse(feed_url)
            entries = []
            for entry in feed.get("entries", []):
                time_published = entry.get("updated", entry.get("published", ""))
                if not time_published:
                    continue
                try:
                    time_parsed = parse(time_published)
                    formatted_date = "{}-{:02}-{:02}".format(
                        time_parsed.year, time_parsed.month, time_parsed.day
                    )
                except Exception:
                    logger.warning("Could not parse date: %s", time_published)
                    continue

                entries.append({
                    "title": entry.get("title", "Untitled"),
                    "url": entry.get("link", "").split("#")[0],
                    "published": formatted_date,
                })
            result[blog_name] = entries
            logger.info("Fetched %d entries from %s", len(entries), blog_name)
        except Exception as e:
            logger.error("Failed to fetch feed %s: %s", feed_url, e)
            result[blog_name] = []

    return result


def main():
    """Main entry point."""
    logger.info("Starting README update for user: %s", GITHUB_USERNAME)

    readme = root / "README.md"
    if not readme.exists():
        logger.error("README.md not found at %s", readme)
        sys.exit(1)

    # Fetch and format repositories
    releases = fetch_repos(TOKEN, GITHUB_USERNAME)
    md_parts = []
    for name, repo_list in releases.items():
        if not repo_list:
            logger.warning("No repositories found for %s", name)
            continue
        md_parts.append("## " + name)
        repo_list.sort(key=lambda r: r["pushed_at"], reverse=True)
        md_parts.append(
            "\n".join(
                "* [{repo}]({url}),  {description} - {pushed_at}".format(**release)
                for release in repo_list
            )
        )
    md = "\n\n".join(md_parts)

    readme_contents = readme.read_text(encoding="utf-8")
    rewritten = replace_chunk(readme_contents, "recent_releases", md)

    # Fetch and format blog entries
    blogs = fetch_blog_entries(DEFAULT_BLOGS)
    entries_md_parts = []
    for blog_name, entries in blogs.items():
        if not entries:
            continue
        feed_url = DEFAULT_BLOGS.get(blog_name, "")
        parsed = urlsplit(feed_url)
        entries_md_parts.append(
            "## " + "[{0}]({1.scheme}://{1.netloc}/)".format(blog_name, parsed)
        )
        for entry in entries:
            entries_md_parts.append(
                "* [{}]({}) - {}".format(entry["title"], entry["url"], entry["published"])
            )
    entries_md = "\n\n".join(entries_md_parts)

    rewritten = replace_chunk(rewritten, "blog", entries_md)

    # Write updated README
    readme.write_text(rewritten, encoding="utf-8")
    logger.info("README updated successfully")


if __name__ == "__main__":
    main()
