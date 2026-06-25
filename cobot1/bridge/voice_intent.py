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
    return re.sub(r"\s+", " ", text.strip())


def _parse_commands(data: dict[str, Any]) -> list[VoiceCommand]:
    commands: list[VoiceCommand] = []
    for item in data.get("commands", []):
        task_ids = item.get("task_ids") or []
        commands.append(
            VoiceCommand(
                id=str(item["id"]),
                phrase=normalize(str(item["phrase"])),
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
        commands.append(
            {
                "id": item["id"],
                "phrase": item["phrase"],
                "action": item["action"],
            }
        )
    return {
        "commands": commands,
        "speech": data.get("speech", {}),
        "labels": data.get("labels", {}),
    }
