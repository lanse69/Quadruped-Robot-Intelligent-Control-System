"""Filesystem object store for immutable QRICS runtime artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonPayload = dict[str, Any]


@dataclass(frozen=True)
class ObjectRef:
    uri: str
    checksum: str
    size_bytes: int

    def to_json(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
        }


class FileObjectStore:
    """Write-once local object store for replay/report/audit artifacts."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_json(self, namespace: str, object_id: str, payload: JsonPayload) -> ObjectRef:
        namespace_path = self._namespace_path(namespace)
        blob = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        checksum = hashlib.sha256(blob).hexdigest()
        filename = f"{_safe_name(object_id)}-{checksum[:16]}.json"
        path = namespace_path / filename
        if path.exists():
            existing = path.read_bytes()
            if hashlib.sha256(existing).hexdigest() != checksum:
                raise ValueError(f"object path collision for {path}")
        else:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_bytes(blob)
            tmp.replace(path)
        return ObjectRef(uri=path.as_posix(), checksum=f"sha256:{checksum}", size_bytes=len(blob))

    def read_json(self, ref: ObjectRef) -> JsonPayload:
        path = Path(ref.uri)
        blob = path.read_bytes()
        checksum = f"sha256:{hashlib.sha256(blob).hexdigest()}"
        if checksum != ref.checksum:
            raise ValueError(f"checksum mismatch for {ref.uri}")
        data = json.loads(blob.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"stored JSON object is not a mapping: {ref.uri}")
        return data

    def _namespace_path(self, namespace: str) -> Path:
        if not namespace or namespace.startswith("/") or ".." in Path(namespace).parts:
            raise ValueError("namespace must be a relative path without '..'")
        path = self.root / namespace
        path.mkdir(parents=True, exist_ok=True)
        return path


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return safe or "object"
