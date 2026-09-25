from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DATASET


@dataclass
class Case:
    id: str
    version: int
    type: str
    difficulty: int
    language: str
    info_mode: str
    challenges: list[str]
    persona: str
    prompt: str
    params: dict[str, Any]
    hidden_facts: list[dict[str, str]]
    missing_facts: list[str]
    expected_behavior: str
    reference_contract: Any
    checks: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Case:
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def load_cases(path: Path = DATASET) -> list[Case]:
    with path.open(encoding="utf-8") as handle:
        return [Case.from_dict(json.loads(line)) for line in handle if line.strip()]


def save_cases(cases: list[Case], path: Path = DATASET) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in cases:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
