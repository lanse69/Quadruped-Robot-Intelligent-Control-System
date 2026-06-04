from pathlib import Path

from qrics.storage.object_store import FileObjectStore


def test_file_object_store_writes_json_immutably(tmp_path: Path) -> None:
    store = FileObjectStore(tmp_path / "objects")
    first = store.put_json("replay_manifest", "run_1", {"run_id": "run_1", "step": 1})
    second = store.put_json("replay_manifest", "run_1", {"run_id": "run_1", "step": 1})

    assert first == second
    assert first.uri.endswith(".json")
    assert first.checksum.startswith("sha256:")
    assert store.read_json(first)["run_id"] == "run_1"
