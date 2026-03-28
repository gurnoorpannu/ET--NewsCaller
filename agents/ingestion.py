"""Ingestion Agent — fetches news articles from NewsAPI and RSS feeds."""
import math
import requests
import feedparser
from models.schemas import Article
from config import NEWS_API_KEY, MAX_ARTICLES, DEFAULT_COUNTRY


# Fallback RSS feeds (free, no API key needed)
RSS_FEEDS = [
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]


def fetch_from_newsapi(query: str = None, category: str = "general") -> list[Article]:
    """Fetch articles from NewsAPI."""
    if not NEWS_API_KEY or NEWS_API_KEY == "YOUR_NEWSAPI_KEY_HERE":
        return []

    try:
        if query:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "pageSize": MAX_ARTICLES,
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": NEWS_API_KEY,
            }
        else:
            url = "https://newsapi.org/v2/top-headlines"
            params = {
                "country": DEFAULT_COUNTRY,
                "category": category,
                "pageSize": MAX_ARTICLES,
                "apiKey": NEWS_API_KEY,
            }

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("articles", []):
            articles.append(Article(
                title=item.get("title", "") or "",
                description=item.get("description", "") or "",
                content=item.get("content", "") or "",
                source=item.get("source", {}).get("name", ""),
                url=item.get("url", ""),
                published_at=item.get("publishedAt", ""),
                image_url=item.get("urlToImage", "") or "",
            ))
        return articles
    except Exception as e:
        print(f"[Ingestion] NewsAPI error: {e}")
        return []


def fetch_from_rss(feed_urls: list[str] = None) -> list[Article]:
    """Fetch articles from RSS feeds."""
    feeds = feed_urls or RSS_FEEDS
    if not feeds:
        return []
    articles = []

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            per_feed = math.ceil(MAX_ARTICLES / len(feeds))
            for entry in feed.entries[:per_feed]:
                articles.append(Article(
                    title=entry.get("title", ""),
                    description=entry.get("summary", ""),
                    content=entry.get("summary", ""),
                    source=feed.feed.get("title", "RSS"),
                    url=entry.get("link", ""),
                    published_at=entry.get("published", ""),
                ))
        except Exception as e:
            print(f"[Ingestion] RSS error for {feed_url}: {e}")

    return articles


def ingest(query: str = None, interests: list[str] = None) -> list[Article]:
    """
    Main ingestion function.
    Tries NewsAPI first, falls back to RSS.
    If interests provided, fetches targeted content.
    """
    articles = []

    # Try NewsAPI with interests as queries
    if interests:
        for interest in interests[:3]:
            articles.extend(fetch_from_newsapi(query=interest))
    elif query:
        articles.extend(fetch_from_newsapi(query=query))
    else:
        articles.extend(fetch_from_newsapi())

    # If NewsAPI didn't return enough, supplement with RSS
    if len(articles) < 5:
        rss_articles = fetch_from_rss()
        articles.extend(rss_articles)

    # Deduplicate by title
    seen = set()
    unique = []
    for a in articles:
        if a.title and a.title not in seen:
            seen.add(a.title)
            unique.append(a)

    print(f"[Ingestion] Fetched {len(unique)} articles")
    return unique[:MAX_ARTICLES]
