"""Understanding Agent — extracts topics, entities, sentiment from articles."""
from models.schemas import Article, AnalyzedArticle
from utils.llm import ask_llm_json


def analyze_article(article: Article) -> AnalyzedArticle:
    """Extract structured insights from a single article."""
    prompt = f"""Analyze this news article and extract structured information.

Title: {article.title}
Description: {article.description}
Content: {article.content[:1000]}

Return JSON with these fields:
- "topics": list of 2-4 topic tags (e.g., ["technology", "AI", "startups"])
- "entities": list of key people, companies, or places mentioned (max 5)
- "sentiment": one of "positive", "negative", or "neutral"
"""

    try:
        data = ask_llm_json(prompt)
        return AnalyzedArticle(
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
        )
    except Exception as e:
        print(f"[Understanding] Error analyzing '{article.title[:50]}': {e}")
        return AnalyzedArticle(
            title=article.title,
            description=article.description,
            content=article.content,
            source=article.source,
            url=article.url,
            published_at=article.published_at,
            image_url=article.image_url,
            topics=[],
            entities=[],
            sentiment="neutral",
        )


def understand(articles: list[Article]) -> list[AnalyzedArticle]:
    """Analyze all articles. Returns list of AnalyzedArticle."""
    analyzed = []
    for article in articles:
        result = analyze_article(article)
        analyzed.append(result)
    print(f"[Understanding] Analyzed {len(analyzed)} articles")
    return analyzed
