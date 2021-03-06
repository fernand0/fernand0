from python_graphql_client import GraphqlClient
import configparser
import feedparser
import httpx
import json
import pathlib
import re
import os

from dateutil.parser import parse
from urllib.parse import urlsplit


# Quick and dirty modification inspired by https://simonwillison.net/2020/Jul/10/self-updating-profile-readme/

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("FERNAND0_TOKEN", "")


def replace_chunk(content, marker, chunk):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    chunk = "<!-- {} starts -->\n{}\n<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)

def make_query(after_cursor=None):
    return """
query MyQuery {
  user(login: "fernand0") {
    repositories(last: 10, orderBy: {field: UPDATED_AT, direction: ASC}, privacy: PUBLIC) {
      edges {
        node {
          name
          description
          url
          owner {
            login
          }
          pushedAt
        }
      }
    }
    repositoriesContributedTo(last: 20, orderBy: {field: PUSHED_AT, direction: DESC}) {
      edges {
        node {
          name
          description
          url
          pushedAt
        }
      }
    }

  }
}
""".replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    )

def fetch_repos(oauth_token):
    repos = []
    releases = {}
    repo_names = set()
    has_next_page = True
    after_cursor = None

    #while has_next_page:
    data = client.execute(
        query=make_query(after_cursor),
        headers={"Authorization": "Bearer {}".format(oauth_token)},
    )
    releases["repositories"]=[]
    for repo in data["data"]["user"]["repositories"]["edges"]:
        if repo["node"]["name"] not in repo_names:
            repos.append(repo)
            repo_names.add(repo["node"]["name"])
            releases["repositories"].append(
                {
                    "repo": repo["node"]["name"],
                    "description": repo["node"]["description"],
                    "pushed_at": repo["node"]["pushedAt"].split("T")[0],
                    "url": repo["node"]["url"]
                }
            )
    releases["repositoriesContributedTo"]=[]
    repo_names = set()
    for repo in data["data"]["user"]["repositoriesContributedTo"]["edges"]:
        if repo["node"]["name"] not in repo_names:
            repos.append(repo)
            repo_names.add(repo["node"]["name"])
            releases["repositoriesContributedTo"].append(
                {
                    "repo": repo["node"]["name"],
                    "description": repo["node"]["description"],
                    "pushed_at": repo["node"]["pushedAt"].split("T")[0],
                    "url": repo["node"]["url"]
                }
            )
    return releases

def fetch_blog_entries(blogs):

    entries = {}
    for blog in blogs.keys():
        entries[blog] = feedparser.parse(blogs[blog])["entries"]

    result = {}
    for entry in entries.keys():
        result[entry] = []
        for blogEntry in entries[entry]:
            timePublished=blogEntry["published"]
            timeParsed = parse(timePublished)
            timePublished = "{}-{:02}-{:02}".format(timeParsed.year,
                    timeParsed.month, timeParsed.day)
            result[entry].append({
                "title": blogEntry["title"],
                "url": blogEntry["link"].split("#")[0],
                "published": timePublished,
            }
            )
        for resu in result:
            for res in result[resu]:
                print("res",res)


    return result

if __name__ == "__main__":

    readme = root / "README.md"
    releases = fetch_repos(TOKEN)
    md = ""
    for name in releases.keys():
        md = md+"\n\n"+"## "+name
        releases[name].sort(key=lambda r: r["pushed_at"], reverse=True)
        print(releases[name])
        md = md+"\n"+"\n".join(
            [
                "* [{repo}]({url}),  {description}- {pushed_at}".format(**release) 
                for release in releases[name]#[:5]
            ]
        )
    readme_contents = readme.open().read()
    rewritten = replace_chunk(readme_contents, "recent_releases", md)

    myBlogs = {'fernand0@GitHub':'https://fernand0.github.io/feed.xml',
            'Reflexiones e Irreflexiones':'http://fernand0.blogalia.com/rss20.xml'}
    blogs = fetch_blog_entries(myBlogs)#[:5]
    entries_md = "" 
    for blog in blogs:
        entries_md = entries_md + "\n\n" + "## " + "[{0}]({1.scheme}://{1.netloc}/)".format(blog,urlsplit(myBlogs[blog]))
        for entry in blogs[blog]:
            entries_md = entries_md+"\n" + "* [{}]({}) - {}".format(entry['title'],entry['url'],entry['published'])
    rewritten = replace_chunk(rewritten, "blog", entries_md)

    print(rewritten)
    readme.open("w").write(rewritten)
