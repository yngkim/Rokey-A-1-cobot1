"""고정 문장 음성 명령 해석."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cobot1.bridge.voice_config import load_voice_config


@dataclass(frozen=True)
class VoiceCommand:
    id: str
    phrase: str
    action: str
    task_id: str = ""
    task_ids: tuple[str, ...] = ()


def normalize(text: str) -> str:
    """STT 결과 정규화 — 띄어쓰기·조사·존댓말 변형을 등록 문장 형식에 맞춤."""
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"핸드폰[을를]\s*", "핸드폰 ", text)
    # Web Speech API가 자주 넣는 띄어쓰기·존댓말 변형
    text = re.sub(r"가져다\s*줘", "가져다줘", text)
    text = re.sub(r"가져다\s*주세요", "가져다줘", text)
    text = re.sub(r"가져와\s*줘", "가져와줘", text)
    text = re.sub(r"가져와\s*주세요", "가져와줘", text)
    text = re.sub(r"가져가\s*줘", "가져가줘", text)
    text = re.sub(r"가져가\s*주세요", "가져가줘", text)
    text = re.sub(r"준비해\s*줘", "준비해 줘", text)
    text = re.sub(r"준비해줘", "준비해 줘", text)
    text = re.sub(r"청소해\s*줘", "청소해줘", text)
    text = re.sub(r"청소해\s*주세요", "청소해줘", text)
    return text.strip()


def _parse_commands(data: dict[str, Any]) -> list[VoiceCommand]:
    commands: list[VoiceCommand] = []
    for item in data.get("commands", []):
        task_ids = item.get("task_ids") or []
        phrases = item.get("phrases") or []
        primary = str(item.get("phrase", "")).strip()
        if primary:
            phrases = [primary, *phrases]
        if not phrases:
            continue
        for phrase in phrases:
            commands.append(
                VoiceCommand(
                    id=str(item["id"]),
                    phrase=normalize(str(phrase)),
                    action=str(item["action"]),
                    task_id=str(item.get("task_id", "")),
                    task_ids=tuple(str(t) for t in task_ids),
                )
            )
    return commands


def resolve_voice_command(
    text: str,
    config: dict[str, Any] | None = None,
) -> VoiceCommand | None:
    data = config if config is not None else load_voice_config()
    normalized = normalize(text)
    for command in _parse_commands(data):
        if normalized == command.phrase:
            return command
    return None


def get_speech(
    command_id: str,
    key: str,
    config: dict[str, Any] | None = None,
) -> str:
    data = config if config is not None else load_voice_config()
    speech = data.get("speech", {})
    if command_id == "global":
        return str(speech.get("global", {}).get(key, ""))
    entry = speech.get(command_id, {})
    return str(entry.get(key, ""))


def get_chain_task_ids(
    chain_id: str,
    config: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    """run_chain 음성 명령의 task_ids (UI 체인 버튼과 동일 시퀀스)."""
    data = config if config is not None else load_voice_config()
    for item in data.get("commands", []):
        if str(item.get("id")) == chain_id and str(item.get("action")) == "run_chain":
            return tuple(str(t) for t in (item.get("task_ids") or []))
    return ()


def get_voice_catalog(config: dict[str, Any] | None = None) -> dict[str, Any]:
    data = config if config is not None else load_voice_config()
    commands = []
    for item in data.get("commands", []):
        phrases = list(item.get("phrases") or [])
        primary = str(item.get("phrase", "")).strip()
        if primary and primary not in phrases:
            phrases.insert(0, primary)
        commands.append(
            {
                "id": item["id"],
                "phrase": primary or (phrases[0] if phrases else ""),
                "phrases": phrases,
                "action": item["action"],
                "task_id": str(item.get("task_id", "")),
            }
        )
    return {
        "commands": commands,
        "speech": data.get("speech", {}),
        "labels": data.get("labels", {}),
    }
