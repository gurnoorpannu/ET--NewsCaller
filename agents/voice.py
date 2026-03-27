"""Voice Agent — Text-to-Speech and Speech-to-Text."""
import io
import os
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
    """Convert audio bytes to text using Google's free STT.

    Handles WebM/OGG from audio_recorder_streamlit by writing to a temp file
    and letting SpeechRecognition + ffmpeg handle format detection.
    """
    if not audio_bytes:
        return ""

    recognizer = sr.Recognizer()

    # audio_recorder_streamlit returns WebM audio — write with correct extension
    # SpeechRecognition uses the extension to determine format
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        f.flush()
        temp_path = f.name

    # Convert to WAV using ffmpeg (required for SpeechRecognition)
    wav_path = temp_path.replace(".webm", ".wav")
    try:
        os.system(f'ffmpeg -y -i "{temp_path}" -ar 16000 -ac 1 "{wav_path}" -loglevel quiet')

        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio)
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"[Voice] STT error: {e}")
        return ""
    except Exception as e:
        print(f"[Voice] Error processing audio: {e}")
        return ""
    finally:
        # Clean up temp files
        for path in [temp_path, wav_path]:
            try:
                os.unlink(path)
            except OSError:
                pass
