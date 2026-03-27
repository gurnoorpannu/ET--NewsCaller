"""Pipeline orchestrator — connects all agents in sequence."""
from models.schemas import UserProfile, Briefing
from agents.ingestion import ingest
from agents.understanding import understand
from agents.profiling import interpret_profile
from agents.personalization import personalize
from agents.briefing import generate_briefing


def run_pipeline(profile: UserProfile) -> Briefing:
    """
    Full pipeline:
    1. Ingest news (based on user interests)
    2. Understand articles (extract topics, entities, sentiment)
    3. Interpret user profile (expand preferences)
    4. Personalize (score & rank articles for user)
    5. Generate briefing (top 3 articles, conversational)
    """
    print("\n" + "=" * 50)
    print("🚀 Starting MyET AI Pipeline")
    print("=" * 50)

    # Step 1: Ingest
    print("\n[1/5] Ingesting news...")
    articles = ingest(interests=profile.interests)
    if not articles:
        return Briefing(
            greeting=f"Hey {profile.name}, I couldn't find any news articles right now. Please try again later.",
            summary_text="No articles available at the moment.",
        )

    # Step 2: Understand
    print("\n[2/5] Analyzing articles...")
    analyzed = understand(articles)

    # Step 3: Profile interpretation
    print("\n[3/5] Interpreting your profile...")
    profile_data = interpret_profile(profile)

    # Step 4: Personalize
    print("\n[4/5] Personalizing for you...")
    ranked = personalize(analyzed, profile, profile_data)

    # Step 5: Generate briefing
    print("\n[5/5] Generating your briefing...")
    briefing = generate_briefing(ranked, profile, profile_data)

    print("\n" + "=" * 50)
    print("✅ Pipeline complete!")
    print("=" * 50)

    return briefing
