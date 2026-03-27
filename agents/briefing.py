"""Briefing Agent — generates a personalized news briefing."""
import json
from models.schemas import AnalyzedArticle, UserProfile, Briefing
from utils.llm import ask_llm_json
from datetime import datetime


def generate_briefing(
    articles: list[AnalyzedArticle],
    profile: UserProfile,
    profile_interpretation: dict,
    top_n: int = 3,
) -> Briefing:
    """Generate a conversational briefing from top articles in a single LLM call."""
    top_articles = articles[:top_n]

    articles_text = []
    for i, a in enumerate(top_articles):
        articles_text.append({
            "index": i,
            "title": a.title,
            "source": a.source,
            "topics": a.topics,
            "sentiment": a.sentiment,
            "summary": (a.description or a.content)[:300],
        })

    tone = profile_interpretation.get("tone", "professional")
    focus = ", ".join(profile_interpretation.get("focus_areas", ["general"]))

    prompt = f"""You are a personal AI news companion delivering a morning briefing via voice call.

User: {profile.name} (Role: {profile.role})
Tone: {tone}
Focus on: {focus}
Depth: {profile.preferred_depth}

Top news articles:
{json.dumps(articles_text, indent=2)}

Return a single JSON object with:
- "briefing_text": A natural, conversational briefing (under 400 words). Start with a brief personalized greeting using their name. For each article, summarize in 2-3 sentences and explain why it matters for this user. End with an invite to ask questions. NO markdown, NO bullet points — written for voice.
- "why_it_matters": A JSON array with one short sentence per article explaining relevance to a {profile.role} interested in {', '.join(profile.interests[:3])}.

Example format:
{{
  "briefing_text": "Good morning Gurnoor! ...",
  "why_it_matters": ["Sentence for article 0", "Sentence for article 1", "Sentence for article 2"]
}}
"""

    try:
        data = ask_llm_json(prompt)
        summary_text = data.get("briefing_text", "")
        why_list = data.get("why_it_matters", [])

        for i, article in enumerate(top_articles):
            if i < len(why_list):
                article.why_it_matters = why_list[i]

    except Exception as e:
        print(f"[Briefing] Error: {e}")
        summary_text = f"Good morning {profile.name}! Here are your top stories today."

    briefing = Briefing(
        greeting=f"Good morning, {profile.name}!",
        top_articles=top_articles,
        summary_text=summary_text,
        generated_at=datetime.now().isoformat(),
    )

    print(f"[Briefing] Generated briefing with {len(top_articles)} articles in 1 API call")
    return briefing
