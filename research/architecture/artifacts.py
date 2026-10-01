"""Stable content identity and an in-memory artifact store."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .status import AuthorityLevel, ImplementationStatus


HASH_BASIS = "cj1"


class _FrozenDict(dict):
    def _deny(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("artifact payload is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _deny
    __ior__ = _deny

    def __deepcopy__(self, memo: dict[int, Any]) -> _FrozenDict:
        return self


class _FrozenList(list):
    def _deny(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("artifact payload is immutable")

    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = _deny
    __iadd__ = __imul__ = _deny

    def __deepcopy__(self, memo: dict[int, Any]) -> _FrozenList:
        return self


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    return value


def _json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise TypeError("semantic payload must use JSON objects, arrays, integers, booleans or strings")


def canonical_json_v1(payload: Any) -> bytes:
    """No float, NaN, implicit Unicode normalization, or platform newline conversion."""
    _json_value(payload)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def stable_artifact_id(artifact_type: str, schema_version: str, payload: Any) -> str:
    if not artifact_type or not schema_version or ":" in artifact_type or ":" in schema_version:
        raise ValueError("artifact type and schema version must be nonempty colon-free IDs")
    digest = hashlib.sha256(canonical_json_v1(payload)).hexdigest()
    return f"{artifact_type}:{schema_version}:{HASH_BASIS}:{digest}"


@dataclass(frozen=True)
class ArtifactEnvelope:
    artifact_type: str
    schema_version: str
    producer_stage: str
    implementation_status: ImplementationStatus
    authority_level: AuthorityLevel
    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_id: str = field(init=False)
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        payload = deepcopy(self.payload)
        metadata = deepcopy(self.metadata)
        artifact_id = stable_artifact_id(self.artifact_type, self.schema_version, payload)
        object.__setattr__(self, "payload", _freeze(payload))
        object.__setattr__(self, "metadata", _freeze(metadata))
        object.__setattr__(self, "artifact_id", artifact_id)
        object.__setattr__(self, "content_hash", artifact_id.rsplit(":", 1)[1])

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_id": self.artifact_id, "artifact_type": self.artifact_type,
                "schema_version": self.schema_version, "hash_basis": HASH_BASIS,
                "content_hash": self.content_hash, "producer_stage": self.producer_stage,
                "implementation_status": self.implementation_status.value,
                "authority_level": self.authority_level.value,
                "payload": _thaw(self.payload), "metadata": _thaw(self.metadata)}


class ArtifactStore:
    def __init__(self) -> None:
        self._items: dict[str, ArtifactEnvelope] = {}

    def put(self, artifact: ArtifactEnvelope) -> None:
        prior = self._items.get(artifact.artifact_id)
        if prior is not None:
            if (canonical_json_v1(prior.payload) != canonical_json_v1(artifact.payload)
                    or prior.authority_level != artifact.authority_level
                    or prior.artifact_type != artifact.artifact_type
                    or prior.schema_version != artifact.schema_version):
                raise ValueError("artifact identity or authority collision")
            return
        self._items[artifact.artifact_id] = deepcopy(artifact)

    def get(self, artifact_id: str) -> ArtifactEnvelope:
        return deepcopy(self._items[artifact_id])

    def has(self, artifact_id: str) -> bool:
        return artifact_id in self._items
