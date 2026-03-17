"""Tests for gateway/voice.py — TTS/STT helpers, language detection, directive parsing."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from gateway.voice import (
    TtsMode,
    get_tts_config,
    parse_tts_directives,
    detect_language_voice,
    _cleanup_temp,
    _ensure_compatible_format,
    text_to_speech,
    speech_to_text,
    maybe_tts_reply,
    LANG_VOICE_MAP,
    DEFAULT_TTS_VOICE,
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOLUME,
    MAX_TTS_CHARS,
    TTS_DIRECTIVE_RE,
)


# ══════════════════════════════════════════════════════════════
#  TtsMode
# ══════════════════════════════════════════════════════════════


class TestTtsMode:
    def test_valid_modes(self):
        assert TtsMode.is_valid("off") is True
        assert TtsMode.is_valid("always") is True
        assert TtsMode.is_valid("inbound") is True

    def test_invalid_modes(self):
        assert TtsMode.is_valid("auto") is False
        assert TtsMode.is_valid("") is False
        assert TtsMode.is_valid("ON") is False


# ══════════════════════════════════════════════════════════════
#  get_tts_config
# ══════════════════════════════════════════════════════════════


class TestGetTtsConfig:
    def test_defaults_when_no_tts_key(self):
        cfg = get_tts_config({})
        assert cfg["mode"] == TtsMode.OFF
        assert cfg["voice"] == DEFAULT_TTS_VOICE
        assert cfg["rate"] == DEFAULT_TTS_RATE
        assert cfg["volume"] == DEFAULT_TTS_VOLUME

    def test_defaults_when_tts_is_empty(self):
        cfg = get_tts_config({"tts": {}})
        assert cfg["mode"] == TtsMode.OFF

    def test_partial_override(self):
        cfg = get_tts_config({"tts": {"mode": "always", "voice": "zh-HK-WanLungNeural"}})
        assert cfg["mode"] == "always"
        assert cfg["voice"] == "zh-HK-WanLungNeural"
        assert cfg["rate"] == DEFAULT_TTS_RATE  # default preserved
        assert cfg["volume"] == DEFAULT_TTS_VOLUME

    def test_full_override(self):
        cfg = get_tts_config({
            "tts": {
                "mode": "inbound",
                "voice": "ja-JP-KeitaNeural",
                "rate": "+20%",
                "volume": "-10%",
            }
        })
        assert cfg["mode"] == "inbound"
        assert cfg["voice"] == "ja-JP-KeitaNeural"
        assert cfg["rate"] == "+20%"
        assert cfg["volume"] == "-10%"

    def test_tts_none_returns_defaults(self):
        cfg = get_tts_config({"tts": None})
        assert cfg["mode"] == TtsMode.OFF


# ══════════════════════════════════════════════════════════════
#  parse_tts_directives
# ══════════════════════════════════════════════════════════════


class TestParseTtsDirectives:
    def test_no_directive(self):
        clean, overrides = parse_tts_directives("Hello, world!")
        assert clean == "Hello, world!"
        assert overrides == {}

    def test_voice_directive(self):
        text = "Hello [[tts:voice=zh-HK-WanLungNeural]] world"
        clean, overrides = parse_tts_directives(text)
        assert "[[tts" not in clean
        assert overrides["voice"] == "zh-HK-WanLungNeural"
        assert "Hello" in clean
        assert "world" in clean

    def test_lang_directive_mapped(self):
        text = "你好 [[tts:lang=zh-HK]]"
        clean, overrides = parse_tts_directives(text)
        assert overrides["voice"] == LANG_VOICE_MAP["zh-HK"]
        assert "[[tts" not in clean

    def test_lang_directive_unknown_lang(self):
        text = "Hola [[tts:lang=pt-BR]]"
        clean, overrides = parse_tts_directives(text)
        # pt-BR not in LANG_VOICE_MAP → no override
        assert "voice" not in overrides

    def test_rate_directive(self):
        text = "Fast [[tts:rate=+20%]]"
        clean, overrides = parse_tts_directives(text)
        assert overrides["rate"] == "+20%"

    def test_volume_directive(self):
        text = "Loud [[tts:volume=+10%]]"
        clean, overrides = parse_tts_directives(text)
        assert overrides["volume"] == "+10%"

    def test_combined_directive(self):
        text = "Hi [[tts:voice=en-GB-RyanNeural,rate=+10%,volume=-5%]]"
        clean, overrides = parse_tts_directives(text)
        assert overrides["voice"] == "en-GB-RyanNeural"
        assert overrides["rate"] == "+10%"
        assert overrides["volume"] == "-5%"
        assert clean == "Hi"

    def test_multiple_directives(self):
        text = "A [[tts:voice=foo]] B [[tts:rate=+5%]]"
        clean, overrides = parse_tts_directives(text)
        assert overrides["voice"] == "foo"
        assert overrides["rate"] == "+5%"
        assert "A" in clean and "B" in clean

    def test_case_insensitive_key(self):
        text = "test [[TTS:Voice=myVoice]]"
        clean, overrides = parse_tts_directives(text)
        assert overrides["voice"] == "myVoice"

    def test_empty_text(self):
        clean, overrides = parse_tts_directives("")
        assert clean == ""
        assert overrides == {}


# ══════════════════════════════════════════════════════════════
#  detect_language_voice
# ══════════════════════════════════════════════════════════════


class TestDetectLanguageVoice:
    def test_none_for_empty(self):
        assert detect_language_voice("") is None
        assert detect_language_voice(None) is None

    def test_none_for_english(self):
        assert detect_language_voice("Hello, this is a test message in English.") is None

    def test_none_for_few_cjk(self):
        # Fewer than 5 non-ASCII chars → None
        assert detect_language_voice("Hello 你好") is None

    def test_mandarin_detected(self):
        text = "这是一个测试消息，用来检测语言识别功能是否正常工作。"
        voice = detect_language_voice(text)
        assert voice == LANG_VOICE_MAP["zh-CN"]

    def test_cantonese_detected(self):
        text = "我係一個測試，唔知你識唔識睇呢啲嘢呢？佢嘅嘢好多咁嘅。"
        voice = detect_language_voice(text)
        assert voice == LANG_VOICE_MAP["zh-HK"]

    def test_japanese_detected(self):
        text = "これはテストメッセージです。ひらがなとカタカナが含まれています。"
        voice = detect_language_voice(text)
        assert voice == LANG_VOICE_MAP["ja-JP"]

    def test_korean_detected(self):
        text = "이것은 테스트 메시지입니다. 한글이 포함되어 있습니다. 감사합니다."
        voice = detect_language_voice(text)
        assert voice == LANG_VOICE_MAP["ko-KR"]

    def test_samples_first_200_chars(self):
        # CJK in first 200 chars should be detected even if rest is English
        cjk_prefix = "这是测试消息" * 20  # well over 200 chars of CJK
        text = cjk_prefix + "A" * 500
        voice = detect_language_voice(text)
        assert voice == LANG_VOICE_MAP["zh-CN"]


# ══════════════════════════════════════════════════════════════
#  _cleanup_temp
# ══════════════════════════════════════════════════════════════


class TestCleanupTemp:
    def test_removes_converted_and_original(self, tmp_path):
        original = tmp_path / "voice.ogg"
        converted = tmp_path / "voice.wav"
        original.write_bytes(b"ogg data")
        converted.write_bytes(b"wav data")

        _cleanup_temp(converted, original)
        assert not converted.exists()
        assert not original.exists()  # original now cleaned up too (Bug 3 fix)

    def test_does_not_remove_when_same(self, tmp_path):
        f = tmp_path / "voice.wav"
        f.write_bytes(b"data")

        _cleanup_temp(f, f)
        # When same path, only unlink is called once (original_path.unlink)
        assert not f.exists()

    def test_handles_already_missing_file(self, tmp_path):
        original = tmp_path / "voice.ogg"
        converted = tmp_path / "voice.wav"
        original.write_bytes(b"ogg data")
        # converted doesn't exist — should not raise
        _cleanup_temp(converted, original)
        assert not original.exists()  # original still cleaned up


# ══════════════════════════════════════════════════════════════
#  _ensure_compatible_format
# ══════════════════════════════════════════════════════════════


class TestEnsureCompatibleFormat:
    @pytest.mark.asyncio
    async def test_mp3_passthrough(self, tmp_path):
        f = tmp_path / "audio.mp3"
        f.write_bytes(b"mp3")
        result = await _ensure_compatible_format(f)
        assert result == f

    @pytest.mark.asyncio
    async def test_wav_passthrough(self, tmp_path):
        f = tmp_path / "audio.wav"
        f.write_bytes(b"wav")
        result = await _ensure_compatible_format(f)
        assert result == f

    @pytest.mark.asyncio
    async def test_flac_passthrough(self, tmp_path):
        f = tmp_path / "audio.flac"
        f.write_bytes(b"flac")
        result = await _ensure_compatible_format(f)
        assert result == f

    @pytest.mark.asyncio
    async def test_m4a_passthrough(self, tmp_path):
        f = tmp_path / "audio.m4a"
        f.write_bytes(b"m4a")
        result = await _ensure_compatible_format(f)
        assert result == f

    @pytest.mark.asyncio
    async def test_webm_passthrough(self, tmp_path):
        f = tmp_path / "audio.webm"
        f.write_bytes(b"webm")
        result = await _ensure_compatible_format(f)
        assert result == f

    @pytest.mark.asyncio
    async def test_ogg_converts_with_ffmpeg(self, tmp_path):
        ogg = tmp_path / "audio.ogg"
        ogg.write_bytes(b"ogg data")
        wav_out = tmp_path / "audio.wav"

        mock_result = MagicMock(returncode=0)

        with patch("gateway.voice._has_ffmpeg", return_value=True), \
             patch("gateway.voice.subprocess.run", return_value=mock_result) as mock_run:
            # Simulate ffmpeg creating the output file
            def side_effect(*args, **kwargs):
                wav_out.write_bytes(b"converted wav")
                return mock_result
            mock_run.side_effect = side_effect

            result = await _ensure_compatible_format(ogg)
            assert result == wav_out
            mock_run.assert_called_once()
            # Verify ffmpeg was called with pcm_s16le (16-bit PCM WAV)
            call_args = mock_run.call_args[0][0]
            assert "ffmpeg" in call_args
            assert "pcm_s16le" in call_args
            assert "16000" in call_args

    @pytest.mark.asyncio
    async def test_ogg_falls_back_without_ffmpeg(self, tmp_path):
        ogg = tmp_path / "audio.ogg"
        ogg.write_bytes(b"ogg data")

        with patch("gateway.voice._has_ffmpeg", return_value=False):
            result = await _ensure_compatible_format(ogg)
            assert result == ogg  # returns original

    @pytest.mark.asyncio
    async def test_ogg_falls_back_on_ffmpeg_failure(self, tmp_path):
        ogg = tmp_path / "audio.ogg"
        ogg.write_bytes(b"ogg data")

        mock_result = MagicMock(returncode=1)

        with patch("gateway.voice._has_ffmpeg", return_value=True), \
             patch("gateway.voice.subprocess.run", return_value=mock_result):
            result = await _ensure_compatible_format(ogg)
            assert result == ogg


# ══════════════════════════════════════════════════════════════
#  text_to_speech
# ══════════════════════════════════════════════════════════════


class TestTextToSpeech:
    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self):
        result = await text_to_speech("")
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_none(self):
        result = await text_to_speech("   \n  ")
        assert result is None

    @pytest.mark.asyncio
    async def test_generates_mp3_no_ffmpeg(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.voice.TMP_AUDIO", tmp_path)

        mock_comm = AsyncMock()

        async def mock_save(path):
            Path(path).write_bytes(b"fake mp3 data")

        mock_comm.save = mock_save

        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_comm

        with patch("gateway.voice._has_ffmpeg", return_value=False), \
             patch.dict("sys.modules", {"edge_tts": mock_edge}):
            result = await text_to_speech("Hello world", output_format="mp3")
            assert result is not None
            assert result.suffix == ".mp3"
            assert result.exists()

    @pytest.mark.asyncio
    async def test_converts_to_ogg_with_ffmpeg(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.voice.TMP_AUDIO", tmp_path)

        mock_comm = AsyncMock()

        async def mock_save(path):
            Path(path).write_bytes(b"fake mp3 data")

        mock_comm.save = mock_save

        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_comm

        mock_ffmpeg = MagicMock(returncode=0)

        def ffmpeg_side_effect(cmd, **kwargs):
            # The last arg is the ogg output path
            Path(cmd[-1]).write_bytes(b"fake ogg data")
            return mock_ffmpeg

        with patch("gateway.voice._has_ffmpeg", return_value=True), \
             patch("gateway.voice.subprocess.run", side_effect=ffmpeg_side_effect), \
             patch.dict("sys.modules", {"edge_tts": mock_edge}):
            result = await text_to_speech("Hello world", output_format="ogg")
            assert result is not None
            assert result.suffix == ".ogg"

    @pytest.mark.asyncio
    async def test_truncates_long_text(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.voice.TMP_AUDIO", tmp_path)

        saved_text = {}
        mock_comm = AsyncMock()

        async def mock_save(path):
            Path(path).write_bytes(b"fake mp3 data")

        mock_comm.save = mock_save

        mock_edge = MagicMock()

        def capture_communicate(text, **kwargs):
            saved_text["text"] = text
            return mock_comm

        mock_edge.Communicate.side_effect = capture_communicate

        with patch("gateway.voice._has_ffmpeg", return_value=False), \
             patch.dict("sys.modules", {"edge_tts": mock_edge}):
            long_text = "A" * (MAX_TTS_CHARS + 500)
            result = await text_to_speech(long_text, output_format="mp3")

            assert result is not None
            assert len(saved_text["text"]) == MAX_TTS_CHARS + 3  # truncated + "..."

    @pytest.mark.asyncio
    async def test_edge_tts_error_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.voice.TMP_AUDIO", tmp_path)

        mock_edge = MagicMock()
        mock_edge.Communicate.side_effect = RuntimeError("network error")

        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            result = await text_to_speech("Hello")
            assert result is None


# ══════════════════════════════════════════════════════════════
#  speech_to_text
# ══════════════════════════════════════════════════════════════


class TestSpeechToText:
    @pytest.mark.asyncio
    async def test_missing_file_returns_none(self, tmp_path):
        result = await speech_to_text(tmp_path / "nonexistent.ogg")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_whisper_returns_none(self, tmp_path):
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"mp3 data")

        with patch("gateway.voice.shutil.which", return_value=None):
            result = await speech_to_text(audio)
            assert result is None

    @pytest.mark.asyncio
    async def test_whisper_success(self, tmp_path, monkeypatch):
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"mp3 data")

        model_path = tmp_path / "model.bin"
        model_path.write_bytes(b"fake model")
        monkeypatch.setattr("gateway.voice.WHISPER_MODEL_PATH", model_path)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"Hello world\n", b""))

        with patch("gateway.voice.shutil.which", return_value="/usr/bin/whisper-cli"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
             patch("asyncio.wait_for", return_value=(b"Hello world\n", b"")):
            # Patch _ensure_compatible_format to skip ffmpeg
            with patch("gateway.voice._ensure_compatible_format", return_value=audio):
                result = await speech_to_text(audio, language="en")
                assert result == "Hello world"


# ══════════════════════════════════════════════════════════════
#  maybe_tts_reply
# ══════════════════════════════════════════════════════════════


class TestMaybeTtsReply:
    @pytest.mark.asyncio
    async def test_off_mode_no_directives(self):
        config = {"tts": {"mode": "off"}}
        audio, clean = await maybe_tts_reply("Hello", config)
        assert audio is None
        assert clean == "Hello"

    @pytest.mark.asyncio
    async def test_off_mode_with_directive_triggers_tts(self):
        config = {"tts": {"mode": "off"}}
        text = "Hello [[tts:voice=en-GB-RyanNeural]]"

        with patch("gateway.voice.text_to_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = Path("/tmp/fake.ogg")
            audio, clean = await maybe_tts_reply(text, config)
            assert audio is not None
            mock_tts.assert_called_once()
            # Verify directive voice was passed
            call_kwargs = mock_tts.call_args[1]
            assert call_kwargs["voice"] == "en-GB-RyanNeural"

    @pytest.mark.asyncio
    async def test_inbound_mode_no_voice_skips(self):
        config = {"tts": {"mode": "inbound"}}
        audio, clean = await maybe_tts_reply("Hello", config, inbound_was_voice=False)
        assert audio is None

    @pytest.mark.asyncio
    async def test_inbound_mode_with_voice_triggers(self):
        config = {"tts": {"mode": "inbound"}}

        with patch("gateway.voice.text_to_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = Path("/tmp/fake.ogg")
            audio, clean = await maybe_tts_reply("Hello", config, inbound_was_voice=True)
            assert audio is not None
            mock_tts.assert_called_once()

    @pytest.mark.asyncio
    async def test_always_mode_triggers(self):
        config = {"tts": {"mode": "always"}}

        with patch("gateway.voice.text_to_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = Path("/tmp/fake.ogg")
            audio, clean = await maybe_tts_reply("Hello", config)
            assert audio is not None

    @pytest.mark.asyncio
    async def test_language_detection_used_for_voice(self):
        config = {"tts": {"mode": "always"}}
        text = "这是一个测试消息，用来检测语言识别功能是否正常工作。"

        with patch("gateway.voice.text_to_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = Path("/tmp/fake.ogg")
            audio, clean = await maybe_tts_reply(text, config)
            call_kwargs = mock_tts.call_args[1]
            assert call_kwargs["voice"] == LANG_VOICE_MAP["zh-CN"]

    @pytest.mark.asyncio
    async def test_directive_overrides_detection(self):
        config = {"tts": {"mode": "always"}}
        # Chinese text but directive says use Japanese voice
        text = "这是测试 [[tts:voice=ja-JP-KeitaNeural]]"

        with patch("gateway.voice.text_to_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = Path("/tmp/fake.ogg")
            audio, clean = await maybe_tts_reply(text, config)
            call_kwargs = mock_tts.call_args[1]
            assert call_kwargs["voice"] == "ja-JP-KeitaNeural"


# ══════════════════════════════════════════════════════════════
#  TTS_DIRECTIVE_RE regex
# ══════════════════════════════════════════════════════════════


class TestDirectiveRegex:
    def test_matches_basic(self):
        assert TTS_DIRECTIVE_RE.search("[[tts:voice=foo]]")

    def test_matches_case_insensitive(self):
        assert TTS_DIRECTIVE_RE.search("[[TTS:Voice=bar]]")

    def test_no_match_without_brackets(self):
        assert TTS_DIRECTIVE_RE.search("tts:voice=foo") is None

    def test_no_match_single_bracket(self):
        assert TTS_DIRECTIVE_RE.search("[tts:voice=foo]") is None

    def test_extracts_content(self):
        m = TTS_DIRECTIVE_RE.search("text [[tts:voice=x,rate=+5%]] more")
        assert m.group(1) == "voice=x,rate=+5%"
