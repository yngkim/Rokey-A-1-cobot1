"""서버 TTS — MP3 생성 (클라이언트 HTML Audio / 미디어 볼륨 재생용)."""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from typing import Any

DEFAULT_VOICE = "ko-KR-SunHiNeural"
MAX_CACHE = 96
MAX_TEXT_LEN = 400

_cache: OrderedDict[str, bytes] = OrderedDict()
_cache_lock = asyncio.Lock()


def _cache_key(text: str, voice: str) -> str:
    raw = f"{voice}\0{text.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _trim_cache() -> None:
    while len(_cache) > MAX_CACHE:
        _cache.popitem(last=False)


async def synthesize_speech_mp3(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """텍스트 → MP3 bytes. edge-tts 사용."""
    cleaned = (text or "").strip()
    if not cleaned:
        return b""
    if len(cleaned) > MAX_TEXT_LEN:
        cleaned = cleaned[:MAX_TEXT_LEN]

    key = _cache_key(cleaned, voice)
    async with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]

    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "edge-tts가 필요합니다: pip install edge-tts"
        ) from exc

    communicate = edge_tts.Communicate(cleaned, voice=voice)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            chunks.append(chunk["data"])

    audio = b"".join(chunks)
    if not audio:
        raise RuntimeError("TTS audio empty")

    async with _cache_lock:
        _cache[key] = audio
        _cache.move_to_end(key)
        _trim_cache()
    return audio


def tts_status() -> dict[str, Any]:
    try:
        import edge_tts  # noqa: F401

        return {"available": True, "engine": "edge-tts", "voice": DEFAULT_VOICE}
    except ImportError:
        return {"available": False, "engine": None, "voice": DEFAULT_VOICE}
