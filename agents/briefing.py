"""Briefing Agent — generates a personalized news briefing."""
from models.schemas import AnalyzedArticle, UserProfile, Briefing
from utils.llm import ask_llm
from datetime import datetime


def generate_briefing(
    articles: list[AnalyzedArticle],
    profile: UserProfile,
    profile_interpretation: dict,
    top_n: int = 3,
) -> Briefing:
    """
    Generate a conversational briefing from top articles.
    This is what gets converted to voice.
    """
    top_articles = articles[:top_n]

    articles_text = ""
    for i, a in enumerate(top_articles, 1):
        articles_text += f"""
Article {i}: {a.title}
Source: {a.source}
Topics: {', '.join(a.topics)}
Sentiment: {a.sentiment}
Summary: {a.description or a.content[:300]}
---
"""

    tone = profile_interpretation.get("tone", "professional")
    focus = ", ".join(profile_interpretation.get("focus_areas", ["general"]))

    prompt = f"""You are a personal AI news companion delivering a morning briefing via voice call.

User: {profile.name} (Role: {profile.role})
Tone: {tone}
Focus on: {focus}
Depth: {profile.preferred_depth}

Top news articles for this user:
{articles_text}

Generate a natural, conversational briefing that:
1. Starts with a brief personalized greeting (use their name)
2. For each article (number them):
   - Summarize the key point in 2-3 sentences
   - Explain WHY this matters specifically for this user (given their role and interests)
   - Keep it conversational — this will be read aloud
3. End with a brief wrap-up inviting them to ask questions

Keep the total briefing under 400 words. Make it sound natural, like a knowledgeable friend updating you.
Do NOT use markdown formatting, bullet points, or special characters — this is for voice.
"""

    summary_text = ask_llm(prompt)

    # Extract "why it matters" for each article
    for i, article in enumerate(top_articles):
        why_prompt = f"""In one sentence, explain why this news matters to a {profile.role}
interested in {', '.join(profile.interests[:3])}: "{article.title}" """
        article.why_it_matters = ask_llm(why_prompt, temperature=0.5).strip()

    briefing = Briefing(
        greeting=f"Good morning, {profile.name}!",
        top_articles=top_articles,
        summary_text=summary_text,
        generated_at=datetime.now().isoformat(),
    )

    print(f"[Briefing] Generated briefing with {len(top_articles)} articles")
    return briefing
