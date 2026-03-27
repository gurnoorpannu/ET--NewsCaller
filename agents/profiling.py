"""Profiling Agent — interprets user profile into actionable preferences."""
from models.schemas import UserProfile
from utils.llm import ask_llm_json


def interpret_profile(profile: UserProfile) -> dict:
    """
    Takes raw user profile and returns enriched preferences
    that the personalization agent can use.
    """
    prompt = f"""You are a news personalization expert. Given this user profile,
determine what kind of news content would be most relevant and how it should be presented.

User Profile:
- Name: {profile.name}
- Role: {profile.role}
- Interests: {', '.join(profile.interests)}
- Preferred Depth: {profile.preferred_depth}

Return JSON with:
- "priority_topics": list of 5-8 specific topics this user would care about
- "tone": how to communicate with this user (e.g., "professional", "casual", "academic")
- "focus_areas": what aspects of news to emphasize (e.g., "market impact", "technical details", "policy implications")
- "avoid": topics or angles less relevant to this user
"""

    try:
        data = ask_llm_json(prompt)
        print(f"[Profiling] Interpreted profile for {profile.name}: {data.get('priority_topics', [])}")
        return data
    except Exception as e:
        print(f"[Profiling] Error: {e}")
        return {
            "priority_topics": profile.interests,
            "tone": "professional",
            "focus_areas": ["general relevance"],
            "avoid": [],
        }
