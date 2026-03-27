"""Personalization Agent — filters and ranks articles based on user profile."""
import json
from models.schemas import AnalyzedArticle, UserProfile
from utils.llm import ask_llm_json


def personalize(
    articles: list[AnalyzedArticle],
    profile: UserProfile,
    profile_interpretation: dict,
) -> list[AnalyzedArticle]:
    """
    Score and rank articles based on user relevance.
    Returns articles sorted by relevance (highest first).
    """
    if not articles:
        return []

    # Build article summaries for the LLM
    article_summaries = []
    for i, a in enumerate(articles):
        article_summaries.append({
            "index": i,
            "title": a.title,
            "topics": a.topics,
            "sentiment": a.sentiment,
        })

    prompt = f"""You are a news personalization engine. Score each article's relevance to this user.

User Profile:
- Role: {profile.role}
- Interests: {', '.join(profile.interests)}
- Priority Topics: {', '.join(profile_interpretation.get('priority_topics', []))}
- Focus Areas: {', '.join(profile_interpretation.get('focus_areas', []))}

Articles:
{json.dumps(article_summaries, indent=2)}

Return a JSON array of objects with "index" and "score" (0.0 to 1.0).
Score based on how relevant each article is to THIS specific user.
Example: [{{"index": 0, "score": 0.85}}, {{"index": 1, "score": 0.3}}]
"""

    try:
        raw = ask_llm_json(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        scores = json.loads(raw.strip())

        # Apply scores
        score_map = {s["index"]: s["score"] for s in scores}
        for i, article in enumerate(articles):
            article.relevance_score = score_map.get(i, 0.5)

    except Exception as e:
        print(f"[Personalization] Error scoring: {e}")
        for article in articles:
            article.relevance_score = 0.5

    # Sort by relevance
    ranked = sorted(articles, key=lambda a: a.relevance_score, reverse=True)
    print(f"[Personalization] Ranked {len(ranked)} articles. Top: '{ranked[0].title[:50]}' ({ranked[0].relevance_score})")
    return ranked
