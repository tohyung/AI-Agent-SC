"""Append-only logical model outputs for exact-input offline replay."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _request_hash(model: str, system: str, user: str) -> str:
    source = json.dumps({"model": model, "system": system, "user": user},
                        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class JournaledModel:
    """Replay only exact prior outputs; changed input always calls the delegate."""

    def __init__(self, delegate: Any, path: Path) -> None:
        self.delegate = delegate
        self.model = str(delegate.model)
        self.path = path
        self._outputs: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if (set(record) != {"request_sha256", "model", "output", "recorded_at_utc"}
                        or record["model"] != self.model
                        or not isinstance(record["request_sha256"], str)
                        or not isinstance(record["output"], dict)):
                    raise ValueError("invalid logical model journal")
                prior = self._outputs.get(record["request_sha256"])
                if prior is not None and prior != record["output"]:
                    raise ValueError("conflicting outputs for one model request")
                self._outputs[record["request_sha256"]] = record["output"]

    def generate(self, system: str, user: str) -> dict[str, Any]:
        request_id = _request_hash(self.model, system, user)
        cached = self._outputs.get(request_id)
        if cached is not None:
            return deepcopy(cached)
        output = self.delegate.generate(system, user)
        if not isinstance(output, dict):
            raise ValueError("logical model output must be a JSON object")
        record = {"request_sha256": request_id, "model": self.model,
                  "output": output, "recorded_at_utc": datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as writer:
            writer.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            writer.flush()
            os.fsync(writer.fileno())
        self._outputs[request_id] = deepcopy(output)
        return deepcopy(output)

    def set_call_budget(self, limit: int) -> None:
        self.delegate.set_call_budget(limit)

    @property
    def llm_calls(self) -> int:
        return self.delegate.llm_calls

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return self.delegate.call_log

    def usage_summary(self) -> dict[str, Any]:
        return self.delegate.usage_summary()


class FirstCoreReplayModel:
    """Reuse an unchanged Stage 2B core once, then forward repair/generation calls."""

    def __init__(self, delegate: JournaledModel, core: dict[str, Any],
                 initial_errors: list[str] | None = None) -> None:
        self.delegate = delegate
        self.core = deepcopy(core)
        self.initial_errors = deepcopy(initial_errors) if initial_errors is not None else None
        self.replayed = False
        self.model = delegate.model

    def generate(self, system: str, user: str) -> dict[str, Any]:
        if not self.replayed:
            if not system.startswith("Extract user intent only as one JSON ShadowSemanticCore"):
                raise ValueError("stored semantic core may only replay at Stage 2B")
            self.replayed = True
            return deepcopy(self.core)
        return self.delegate.generate(system, user)

    def replay_metadata_for(self, core: dict[str, Any]) -> list[str] | None:
        if self.replayed and core == self.core:
            return deepcopy(self.initial_errors)
        return None

    def set_call_budget(self, limit: int) -> None:
        self.delegate.set_call_budget(limit)

    @property
    def llm_calls(self) -> int:
        return self.delegate.llm_calls

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return self.delegate.call_log

    def usage_summary(self) -> dict[str, Any]:
        return self.delegate.usage_summary()


class SavedContractReplayModel:
    """Replay one immutable contract output for the same accepted-intent artifact."""

    def __init__(self, delegate: JournaledModel, accepted_intent_id: str,
                 output: dict[str, Any]) -> None:
        self.delegate = delegate
        self.accepted_intent_id = accepted_intent_id
        self.output = deepcopy(output)
        self.replayed = False
        self.model = delegate.model

    def generate(self, system: str, user: str) -> dict[str, Any]:
        if (not self.replayed
                and system.startswith("Generate one canonical Marlowe Core V1 JSON contract")):
            request = json.loads(user)
            if request.get("accepted_intent_id") != self.accepted_intent_id:
                raise ValueError("stored contract belongs to a different accepted intent")
            self.replayed = True
            return deepcopy(self.output)
        return self.delegate.generate(system, user)

    def set_call_budget(self, limit: int) -> None:
        self.delegate.set_call_budget(limit)

    @property
    def llm_calls(self) -> int:
        return self.delegate.llm_calls

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return self.delegate.call_log

    def usage_summary(self) -> dict[str, Any]:
        return self.delegate.usage_summary()
