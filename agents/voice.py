"""Voice Agent — Text-to-Speech (ElevenLabs/gTTS) and Speech-to-Text (Google)."""
import io
import os
import subprocess
import wave
import struct
import tempfile
import speech_recognition as sr
from config import ELEVENLABS_API_KEY


def text_to_speech(text: str, lang: str = "en") -> bytes:
    """Convert text to speech audio bytes (MP3) using ElevenLabs.
    Falls back to gTTS if ElevenLabs key is not configured.
    """
    if ELEVENLABS_API_KEY:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            audio_generator = client.text_to_speech.convert(
                voice_id="JBFqnCBsd6RMkjVDRZzb",  # George — clear, professional
                text=text,
                model_id="eleven_multilingual_v2",
            )
            return b"".join(audio_generator)
        except Exception as e:
            print(f"[Voice] ElevenLabs TTS error: {e}. Falling back to gTTS.")

    # Fallback: gTTS
    from gtts import gTTS
    tts = gTTS(text=text, lang=lang, slow=False)
    buffer = io.BytesIO()
    tts.write_to_fp(buffer)
    buffer.seek(0)
    return buffer.read()


def _webm_to_wav_ffmpeg(webm_path: str, wav_path: str) -> bool:
    """
    Convert WebM to WAV using ffmpeg via subprocess (no shell — no injection risk).
    Returns True if conversion succeeded and output file exists.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", webm_path,
                "-ar", "16000",   # 16 kHz sample rate for speech recognition
                "-ac", "1",       # mono channel
                wav_path,
            ],
            capture_output=True,  # suppress stdout/stderr noise
            timeout=30,           # don't hang forever
        )
        return result.returncode == 0 and os.path.exists(wav_path)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # FileNotFoundError = ffmpeg not installed
        return False


def _wav_from_raw_pcm(audio_bytes: bytes) -> bytes:
    """Wrap raw bytes in a minimal WAV header as a last-resort fallback."""
    # 16-bit PCM, 16000 Hz, mono
    sample_rate = 16000
    num_channels = 1
    bits_per_sample = 16
    num_frames = len(audio_bytes) // (bits_per_sample // 8)

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(bits_per_sample // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_bytes)
    buffer.seek(0)
    return buffer.read()


def speech_to_text(audio_bytes: bytes) -> str:
    """Convert audio bytes to text using Google's free STT.

    Tries ffmpeg conversion first, falls back to treating
    audio as raw PCM if ffmpeg is not installed.
    """
    if not audio_bytes:
        return ""

    recognizer = sr.Recognizer()

    # Write webm to temp file
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        f.flush()
        webm_path = f.name

    wav_path = webm_path.replace(".webm", ".wav")

    try:
        # Try ffmpeg first (best quality)
        if _webm_to_wav_ffmpeg(webm_path, wav_path):
            with sr.AudioFile(wav_path) as source:
                audio = recognizer.record(source)
        else:
            # ffmpeg not available — try treating audio as raw PCM in a WAV wrapper
            print("[Voice] ffmpeg not found, attempting raw PCM fallback...")
            wav_bytes = _wav_from_raw_pcm(audio_bytes)
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio = recognizer.record(source)

        text = recognizer.recognize_google(audio)
        return text

    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"[Voice] STT network error: {e}")
        return ""
    except Exception as e:
        print(f"[Voice] STT error: {e}")
        return ""
    finally:
        for path in [webm_path, wav_path]:
            try:
                os.unlink(path)
            except OSError:
                pass
