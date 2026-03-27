"""Voice Agent — Text-to-Speech and Speech-to-Text."""
import io
import tempfile
import speech_recognition as sr
from gtts import gTTS


def text_to_speech(text: str, lang: str = "en") -> bytes:
    """Convert text to speech audio bytes (MP3)."""
    tts = gTTS(text=text, lang=lang, slow=False)
    buffer = io.BytesIO()
    tts.write_to_fp(buffer)
    buffer.seek(0)
    return buffer.read()


def speech_to_text(audio_bytes: bytes) -> str:
    """Convert audio bytes to text using Google's free STT."""
    recognizer = sr.Recognizer()

    # Write to temp file for SpeechRecognition to read
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        f.flush()
        temp_path = f.name

    try:
        with sr.AudioFile(temp_path) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio)
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"[Voice] STT error: {e}")
        return ""
