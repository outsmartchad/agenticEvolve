"""Voice module — TTS (edge-tts) and STT (local whisper.cpp) for agenticEvolve.

Adapted from openclaw's voice pipeline patterns:
- TTS: edge-tts (free, 300+ neural voices, no API key)
- STT: local whisper-cli (whisper.cpp, ~500ms on Apple Silicon)
- Audio conversion via ffmpeg
- Language auto-detection with CJK/Cantonese heuristics
"""
import asyncio
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"
TMP_AUDIO = EXODIR / "tmp" / "audio"

# ── TTS defaults ──────────────────────────────────────────────
DEFAULT_TTS_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_TTS_RATE = "+0%"
DEFAULT_TTS_VOLUME = "+0%"
MAX_TTS_CHARS = 4000  # edge-tts handles long text fine, but cap for sanity

    


def _ensure_dirs():
    TMP_AUDIO.mkdir(parents=True, exist_ok=True)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ── TTS: Text → Audio ────────────────────────────────────────

async def text_to_speech(
    text: str,
    voice: str = DEFAULT_TTS_VOICE,
    rate: str = DEFAULT_TTS_RATE,
    volume: str = DEFAULT_TTS_VOLUME,
    output_format: str = "ogg",  # "ogg" for Telegram voice, "mp3" for general
) -> Path | None:
    """Convert text to audio using edge-tts. Returns path to audio file or None on error.

    For Telegram voice messages, output_format="ogg" produces OGG/Opus.
    """
    _ensure_dirs()

    if not text or not text.strip():
        return None

    # Truncate if too long
    if len(text) > MAX_TTS_CHARS:
        text = text[:MAX_TTS_CHARS] + "..."

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    # edge-tts outputs MP3 by default
    mp3_path = TMP_AUDIO / f"tts_{timestamp}.mp3"

    try:
        # Use edge-tts Python API
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
        )
        await communicate.save(str(mp3_path))

        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            log.error("edge-tts produced empty file")
            return None

        log.info(f"TTS: edge-tts generated {mp3_path} ({mp3_path.stat().st_size} bytes)")

        # Convert to OGG/Opus for Telegram voice messages
        if output_format == "ogg" and _has_ffmpeg():
            ogg_path = TMP_AUDIO / f"tts_{timestamp}.ogg"
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(mp3_path),
                    "-c:a", "libopus", "-b:a", "48k",
                    "-vbr", "on", "-compression_level", "10",
                    "-application", "voip",
                    str(ogg_path),
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and ogg_path.exists():
                mp3_path.unlink(missing_ok=True)
                log.info(f"TTS: converted to OGG/Opus {ogg_path} ({ogg_path.stat().st_size} bytes)")
                return ogg_path
            else:
                log.warning(f"ffmpeg OGG conversion failed: {result.stderr.decode()[:200]}")
                # Fall back to MP3
                return mp3_path
        else:
            return mp3_path

    except Exception as e:
        log.error(f"TTS error: {e}")
        mp3_path.unlink(missing_ok=True)
        return None


async def list_voices(language_filter: str = "en") -> list[dict]:
    """List available edge-tts voices, optionally filtered by language prefix."""
    try:
        import edge_tts
        voices = await edge_tts.list_voices()
        if language_filter:
            voices = [v for v in voices if v.get("Locale", "").lower().startswith(language_filter.lower())]
        return voices
    except Exception as e:
        log.error(f"Failed to list voices: {e}")
        return []


# ── STT: Audio → Text ────────────────────────────────────────

async def speech_to_text(
    audio_path: str | Path,
    language: str = "auto",
) -> str | None:
    """Transcribe audio file to text using local whisper-cli (whisper.cpp).

    Returns transcript string or None on failure.
    Requires: brew install whisper-cpp + model at ~/.agenticEvolve/models/ggml-small.bin
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        log.error(f"STT: audio file not found: {audio_path}")
        return None

    # Convert OGG to WAV/MP3 if needed (some APIs prefer WAV)
    usable_path = await _ensure_compatible_format(audio_path)

    # Local whisper-cli (whisper.cpp) — free, fast on Apple Silicon
    if shutil.which("whisper-cli"):
        result = await _local_whisper(usable_path, language)
        if result:
            _cleanup_temp(usable_path, audio_path)
            return result
        log.warning("STT: Local whisper failed")

    log.error("STT: whisper-cli not found. Install: brew install whisper-cpp")
    _cleanup_temp(usable_path, audio_path)
    return None


WHISPER_MODEL_PATH = EXODIR / "models" / "ggml-small.bin"  # multilingual small model (better CJK/Cantonese accuracy)


async def _local_whisper(audio_path: Path, language: str) -> str | None:
    """Run local whisper-cli (whisper.cpp). Requires model at ~/.agenticEvolve/models/ggml-small.bin"""
    cmd_name = shutil.which("whisper-cli")
    if not cmd_name:
        return None

    model_path = WHISPER_MODEL_PATH
    if not model_path.exists():
        log.warning(f"STT: whisper model not found at {model_path}")
        return None

    try:
        args = [cmd_name, "-m", str(model_path), "-f", str(audio_path), "--no-timestamps"]
        if language and language != "auto":
            args.extend(["-l", language])
        # else: whisper-cli auto-detects language

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode == 0:
            # whisper-cli outputs transcript to stdout, model logs to stderr
            transcript = stdout.decode().strip()
            # Remove any leading/trailing whitespace lines
            lines = [l.strip() for l in transcript.splitlines() if l.strip()]
            transcript = " ".join(lines)
            if transcript:
                log.info(f"STT: Local whisper-cli transcribed {len(transcript)} chars")
                return transcript

        log.warning(f"Local whisper-cli failed (rc={proc.returncode}): {stderr.decode()[:300]}")
        return None

    except asyncio.TimeoutError:
        log.error("STT: Local whisper-cli timed out (60s)")
        return None
    except Exception as e:
        log.error(f"Local whisper error: {e}")
        return None


async def _ensure_compatible_format(audio_path: Path) -> Path:
    """Convert to 16-bit PCM WAV (16 kHz mono) if the audio is in OGG/Opus format.

    whisper-cli (whisper.cpp) expects 16-bit PCM WAV at 16 kHz for best results.
    Previous MP3 conversion was lossy and fragile on non-Homebrew builds.
    """
    suffix = audio_path.suffix.lower()
    if suffix in (".wav", ".mp3", ".m4a", ".flac", ".webm"):
        return audio_path

    if not _has_ffmpeg():
        log.warning("ffmpeg not found, sending original format to API")
        return audio_path

    # Convert OGG/OGA to 16-bit PCM WAV (16 kHz mono) — optimal for whisper-cli
    wav_path = audio_path.with_suffix(".wav")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                str(wav_path),
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and wav_path.exists():
            log.info(f"STT: Converted {suffix} → WAV 16kHz mono ({wav_path.stat().st_size} bytes)")
            return wav_path
    except Exception as e:
        log.warning(f"Audio conversion failed: {e}")

    return audio_path


def _cleanup_temp(usable_path: Path, original_path: Path):
    """Remove temp conversion files and the original audio file."""
    if usable_path != original_path:
        usable_path.unlink(missing_ok=True)
    # Also clean up the original (e.g. OGG downloaded by bridge) to prevent
    # /tmp/agenticEvolve-wa-audio/ from accumulating indefinitely
    original_path.unlink(missing_ok=True)


# ── TTS auto-mode logic ──────────────────────────────────────

class TtsMode:
    """TTS auto-mode: when to auto-reply with voice.

    Modes (adapted from openclaw):
    - off: never auto-TTS (only /speak)
    - always: every reply gets voice
    - inbound: reply with voice when user sends voice
    """
    OFF = "off"
    ALWAYS = "always"
    INBOUND = "inbound"

    @staticmethod
    def is_valid(mode: str) -> bool:
        return mode in (TtsMode.OFF, TtsMode.ALWAYS, TtsMode.INBOUND)


def get_tts_config(config: dict) -> dict:
    """Extract TTS config from main config dict."""
    defaults = {
        "mode": TtsMode.OFF,
        "voice": DEFAULT_TTS_VOICE,
        "rate": DEFAULT_TTS_RATE,
        "volume": DEFAULT_TTS_VOLUME,
    }
    tts_cfg = config.get("tts", {})
    if not tts_cfg:
        return defaults
    return {
        "mode": tts_cfg.get("mode", defaults["mode"]),
        "voice": tts_cfg.get("voice", defaults["voice"]),
        "rate": tts_cfg.get("rate", defaults["rate"]),
        "volume": tts_cfg.get("volume", defaults["volume"]),
    }


# ── TTS directive parsing (adapted from openclaw) ────────────

# Pattern: [[tts:voice=zh-HK-WanLungNeural]] or [[tts:lang=zh-HK]]
TTS_DIRECTIVE_RE = re.compile(r'\[\[tts:([^\]]+)\]\]', re.IGNORECASE)

# Language → default voice mapping
LANG_VOICE_MAP = {
    "zh-HK": "zh-HK-WanLungNeural",       # Cantonese male
    "zh-TW": "zh-TW-YunJheNeural",         # Taiwanese Mandarin male
    "zh-CN": "zh-CN-YunxiNeural",          # Mandarin male
    "ja-JP": "ja-JP-KeitaNeural",          # Japanese male
    "ko-KR": "ko-KR-InJoonNeural",         # Korean male
    "en-US": DEFAULT_TTS_VOICE,            # English
    "en-GB": "en-GB-RyanNeural",           # British English
    "fr-FR": "fr-FR-HenriNeural",          # French
    "de-DE": "de-DE-ConradNeural",         # German
    "es-ES": "es-ES-AlvaroNeural",         # Spanish
}


def parse_tts_directives(text: str) -> tuple[str, dict]:
    """Extract [[tts:...]] directives from text, return (clean_text, overrides).

    Supported directives:
        [[tts:voice=zh-HK-WanLungNeural]]
        [[tts:lang=zh-HK]]
        [[tts:rate=+20%]]
        [[tts:volume=+10%]]
        [[tts:voice=zh-HK-WanLungNeural,rate=+10%]]
    """
    overrides = {}
    matches = TTS_DIRECTIVE_RE.findall(text)
    for match in matches:
        for pair in match.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                k, v = k.strip().lower(), v.strip()
                if k == "lang" and v in LANG_VOICE_MAP:
                    overrides["voice"] = LANG_VOICE_MAP[v]
                elif k == "voice":
                    overrides["voice"] = v
                elif k in ("rate", "volume"):
                    overrides[k] = v

    clean = TTS_DIRECTIVE_RE.sub("", text).strip()
    return clean, overrides


def detect_language_voice(text: str) -> str | None:
    """Simple heuristic to detect CJK language from response text and pick a voice.

    Returns voice name or None to use default.
    """
    if not text:
        return None

    # Count character types in first 200 chars
    sample = text[:200]
    cjk_count = 0
    jp_count = 0
    kr_count = 0
    total = 0

    for ch in sample:
        cp = ord(ch)
        if cp > 127:
            total += 1
            # CJK Unified Ideographs
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
                cjk_count += 1
            # Hiragana + Katakana
            elif 0x3040 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF:
                jp_count += 1
            # Hangul
            elif 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF:
                kr_count += 1

    if total < 5:
        return None

    if jp_count > 3:
        return LANG_VOICE_MAP["ja-JP"]
    if kr_count > 3:
        return LANG_VOICE_MAP["ko-KR"]
    if cjk_count > total * 0.3:
        # CJK but not clearly Japanese/Korean — check for Cantonese markers
        # Common Cantonese-specific characters: 嘅 係 唔 咁 咗 嘢 佢 嚟 噉 啲 冇
        canto_chars = set("嘅係唔咁咗嘢佢嚟噉啲冇喺啱嗰")
        canto_count = sum(1 for ch in sample if ch in canto_chars)
        if canto_count >= 2:
            return LANG_VOICE_MAP["zh-HK"]
        return LANG_VOICE_MAP["zh-CN"]

    return None


async def maybe_tts_reply(
    text: str,
    config: dict,
    inbound_was_voice: bool = False,
) -> tuple[Path | None, str]:
    """Check TTS mode and produce audio if appropriate.

    Returns (audio_path, clean_text) — clean_text has TTS directives stripped.
    """
    tts_cfg = get_tts_config(config)
    mode = tts_cfg["mode"]

    # Parse directives from Claude's response
    clean_text, overrides = parse_tts_directives(text)

    if mode == TtsMode.OFF and not overrides:
        return None, text
    if mode == TtsMode.INBOUND and not inbound_was_voice and not overrides:
        return None, text

    # Determine voice: directive override > language detection > config default
    voice = overrides.get("voice") or detect_language_voice(clean_text) or tts_cfg["voice"]
    rate = overrides.get("rate", tts_cfg["rate"])
    volume = overrides.get("volume", tts_cfg["volume"])

    audio = await text_to_speech(
        text=clean_text,
        voice=voice,
        rate=rate,
        volume=volume,
    )
    return audio, clean_text
