"""Conversation Agent — handles follow-up Q&A about news."""
from models.schemas import Briefing, UserProfile
from utils.llm import ask_llm


def build_context(briefing: Briefing, profile: UserProfile) -> str:
    """Build context string from briefing for Q&A."""
    context = f"User: {profile.name} ({profile.role}), interested in: {', '.join(profile.interests)}\n\n"
    context += "Today's briefing covered:\n"
    for i, article in enumerate(briefing.top_articles, 1):
        context += f"\n{i}. {article.title}\n"
        context += f"   Source: {article.source}\n"
        context += f"   Topics: {', '.join(article.topics)}\n"
        context += f"   Content: {article.description or article.content[:500]}\n"
        if article.why_it_matters:
            context += f"   Why it matters: {article.why_it_matters}\n"
    return context


def answer_question(
    question: str,
    briefing: Briefing,
    profile: UserProfile,
    chat_history: list[dict] = None,
) -> str:
    """Answer a user's question about the news briefing."""
    context = build_context(briefing, profile)

    history_text = ""
    if chat_history:
        for msg in chat_history[-6:]:  # Last 6 messages for context
            role = "User" if msg["role"] == "user" else "Assistant"
            history_text += f"{role}: {msg['content']}\n"

    prompt = f"""You are MyET AI, a personal news companion. You just delivered a news briefing to the user.
Now they have a follow-up question. Answer based on the briefing context.

{context}

{f"Recent conversation:{chr(10)}{history_text}" if history_text else ""}

User's question: {question}

Instructions:
- Answer conversationally (this will be read aloud via voice)
- Be concise but informative (2-4 sentences)
- If the question is about a specific article, provide deeper context
- If they ask to skip or move on, acknowledge and ask what they'd like to know
- If the question is outside the briefing scope, politely note that and answer briefly if you can
- Do NOT use markdown, bullet points, or special characters
"""

    return ask_llm(prompt, temperature=0.6)
