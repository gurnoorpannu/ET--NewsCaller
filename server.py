"""FastAPI server for the MyET AI Voice Dashboard."""
import io
import json
import base64
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models.schemas import UserProfile, Briefing, AnalyzedArticle
from agents.voice import text_to_speech, speech_to_text
from agents.conversation import answer_question
from utils.llm import ask_llm


# --- In-memory session store (single user for demo) ---
session = {
    "profile": None,
    "briefing": None,
    "chat_history": [],
    "is_pipeline_running": False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🎙️ MyET AI Dashboard server starting...")
    yield
    print("Server shutting down.")


app = FastAPI(title="MyET AI Voice Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


# --- Request/Response Models ---

class ProfileRequest(BaseModel):
    name: str
    role: str
    interests: list[str]
    preferred_depth: str = "medium"


class ChatRequest(BaseModel):
    text: str = ""
    audio_base64: str = ""  # base64-encoded webm audio from browser


class ChatResponse(BaseModel):
    text: str
    audio_base64: str  # base64-encoded mp3
    transcript: str = ""  # what we heard (if audio input)


# --- API Routes ---

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("dashboard/static/index.html", "r") as f:
        return f.read()


@app.post("/api/profile")
async def set_profile(req: ProfileRequest):
    profile = UserProfile(
        name=req.name,
        role=req.role,
        interests=[i.lower() for i in req.interests],
        preferred_depth=req.preferred_depth,
    )
    session["profile"] = profile
    session["chat_history"] = []
    return {"status": "ok", "name": profile.name}


@app.post("/api/start-briefing")
async def start_briefing():
    profile = session.get("profile")
    if not profile:
        raise HTTPException(400, "Profile not set. Call /api/profile first.")

    session["is_pipeline_running"] = True

    try:
        from pipeline import run_pipeline
        briefing = run_pipeline(profile)
        session["briefing"] = briefing
        session["is_pipeline_running"] = False

        # Generate audio for briefing
        audio_bytes = text_to_speech(briefing.summary_text)
        audio_b64 = base64.b64encode(audio_bytes).decode()

        # Prepare articles for frontend
        articles_data = []
        for a in briefing.top_articles:
            articles_data.append({
                "title": a.title,
                "source": a.source,
                "description": a.description[:200],
                "topics": a.topics,
                "sentiment": a.sentiment,
                "relevance_score": a.relevance_score,
                "why_it_matters": a.why_it_matters,
                "url": a.url,
            })

        return {
            "status": "ok",
            "greeting": briefing.greeting,
            "summary_text": briefing.summary_text,
            "audio_base64": audio_b64,
            "articles": articles_data,
        }
    except Exception as e:
        session["is_pipeline_running"] = False
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    profile = session.get("profile")
    briefing = session.get("briefing")

    if not profile:
        raise HTTPException(400, "Profile not set.")

    # Determine user input: text or audio
    user_text = req.text
    transcript = ""

    if req.audio_base64 and not user_text:
        # Decode audio and run STT
        try:
            audio_bytes = base64.b64decode(req.audio_base64)
            user_text = speech_to_text(audio_bytes)
            transcript = user_text
            if not user_text:
                return ChatResponse(
                    text="I couldn't quite catch that. Could you try again?",
                    audio_base64=base64.b64encode(
                        text_to_speech("I couldn't quite catch that. Could you try again?")
                    ).decode(),
                    transcript="",
                )
        except Exception as e:
            print(f"[Dashboard] STT error: {e}")
            return ChatResponse(
                text="Sorry, there was an issue processing your audio.",
                audio_base64=base64.b64encode(
                    text_to_speech("Sorry, there was an issue processing your audio.")
                ).decode(),
                transcript="",
            )

    if not user_text:
        raise HTTPException(400, "No text or audio provided.")

    # Add to history
    session["chat_history"].append({"role": "user", "content": user_text})

    # Generate response
    if briefing:
        response_text = answer_question(
            question=user_text,
            briefing=briefing,
            profile=profile,
            chat_history=session["chat_history"],
        )
    else:
        # No briefing yet — general conversation
        response_text = ask_llm(
            f"""You are MyET AI, a friendly personal news companion.
The user hasn't generated a briefing yet. Respond helpfully.
User ({profile.name}, {profile.role}): {user_text}

Keep your response conversational and under 3 sentences. No markdown.""",
            temperature=0.7,
        )

    session["chat_history"].append({"role": "assistant", "content": response_text})

    # Generate TTS
    audio_bytes = text_to_speech(response_text)
    audio_b64 = base64.b64encode(audio_bytes).decode()

    return ChatResponse(
        text=response_text,
        audio_base64=audio_b64,
        transcript=transcript or user_text,
    )


@app.get("/api/status")
async def status():
    return {
        "has_profile": session.get("profile") is not None,
        "has_briefing": session.get("briefing") is not None,
        "is_running": session.get("is_pipeline_running", False),
        "profile_name": session["profile"].name if session.get("profile") else None,
        "chat_count": len(session.get("chat_history", [])),
    }


@app.post("/api/reset")
async def reset():
    session["profile"] = None
    session["briefing"] = None
    session["chat_history"] = []
    session["is_pipeline_running"] = False
    return {"status": "ok"}
