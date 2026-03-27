"""Understanding Agent — extracts topics, entities, sentiment from articles."""
import json
from models.schemas import Article, AnalyzedArticle
from utils.llm import ask_llm_json


def understand(articles: list[Article]) -> list[AnalyzedArticle]:
    """Analyze all articles in a single LLM call to avoid rate limits."""
    if not articles:
        return []

    # Build compact article list for batch prompt
    article_summaries = []
    for i, a in enumerate(articles):
        article_summaries.append({
            "index": i,
            "title": a.title,
            "description": (a.description or a.content)[:300],
        })

    prompt = f"""Analyze these news articles and extract structured information for each.

Articles:
{json.dumps(article_summaries, indent=2)}

Return a JSON array with one object per article (same order, same index):
[
  {{
    "index": 0,
    "topics": ["topic1", "topic2"],
    "entities": ["entity1", "entity2"],
    "sentiment": "positive"
  }}
]

- topics: 2-4 tags (e.g. "technology", "AI", "markets")
- entities: key people, companies, or places (max 5)
- sentiment: one of "positive", "negative", "neutral"
"""

    try:
        results = ask_llm_json(prompt)
        # Build a lookup by index
        result_map = {r["index"]: r for r in results}
    except Exception as e:
        print(f"[Understanding] Batch analysis error: {e}")
        result_map = {}

    analyzed = []
    for i, article in enumerate(articles):
        data = result_map.get(i, {})
        analyzed.append(AnalyzedArticle(
            title=article.title,
            description=article.description,
            content=article.content,
            source=article.source,
            url=article.url,
            published_at=article.published_at,
            image_url=article.image_url,
            topics=data.get("topics", []),
            entities=data.get("entities", []),
            sentiment=data.get("sentiment", "neutral"),
        ))

    print(f"[Understanding] Analyzed {len(analyzed)} articles in 1 API call")
    return analyzed
