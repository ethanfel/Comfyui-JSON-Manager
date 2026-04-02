import time
import uuid
from typing import Any

KEY_PROMPT_HISTORY = "prompt_history"


class SnapshotTimeline:
    """Flat chronological snapshot list — replaces the old HistoryTree DAG."""

    def __init__(self, raw_data: dict[str, Any]) -> None:
        # Detect and migrate old HistoryTree format
        if "nodes" in raw_data and "branches" in raw_data:
            self._migrate_from_tree(raw_data)
        elif KEY_PROMPT_HISTORY in raw_data and isinstance(raw_data[KEY_PROMPT_HISTORY], list):
            self._migrate_legacy(raw_data[KEY_PROMPT_HISTORY])
        else:
            self.snapshots: dict[str, dict[str, Any]] = raw_data.get("snapshots", {})
            self.current_id: str | None = raw_data.get("current_id", None)

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_from_tree(self, raw_data: dict[str, Any]) -> None:
        """Flatten old HistoryTree nodes into snapshot list, discarding DAG info."""
        self.snapshots = {}
        nodes = raw_data.get("nodes", {})
        for nid, node in nodes.items():
            self.snapshots[nid] = {
                "id": nid,
                "timestamp": node.get("timestamp", time.time()),
                "note": node.get("note", "Migrated"),
                "pinned": False,
                "auto": False,
                "seq_count": self._count_seqs(node.get("data")),
            }
            # Preserve snapshot data if present
            if "data" in node and node["data"]:
                self.snapshots[nid]["data"] = node["data"]
        self.current_id = raw_data.get("head_id")

    def _migrate_legacy(self, old_list: list[dict[str, Any]]) -> None:
        """Convert ancient prompt_history list into snapshots."""
        self.snapshots = {}
        self.current_id = None
        for item in reversed(old_list):
            sid = self._make_id()
            self.snapshots[sid] = {
                "id": sid,
                "timestamp": time.time(),
                "note": item.get("note", "Legacy Import"),
                "pinned": False,
                "auto": False,
                "seq_count": self._count_seqs(item),
                "data": item,
            }
            self.current_id = sid

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def record(self, data: dict[str, Any], note: str = "Snapshot",
               auto: bool = False) -> str:
        """Create a new snapshot and return its ID."""
        sid = self._make_id()
        self.snapshots[sid] = {
            "id": sid,
            "timestamp": time.time(),
            "note": note,
            "pinned": False,
            "auto": auto,
            "seq_count": self._count_seqs(data),
            "data": data,
        }
        self.current_id = sid
        return sid

    def get_snapshot_data(self, snapshot_id: str) -> dict[str, Any] | None:
        """Return the inline snapshot data if present."""
        snap = self.snapshots.get(snapshot_id)
        if snap:
            return snap.get("data")
        return None

    def toggle_pin(self, snapshot_id: str) -> bool:
        """Toggle pinned state, return new value."""
        snap = self.snapshots.get(snapshot_id)
        if snap:
            snap["pinned"] = not snap.get("pinned", False)
            return snap["pinned"]
        return False

    def delete(self, snapshot_id: str) -> None:
        """Remove a snapshot."""
        self.snapshots.pop(snapshot_id, None)
        if self.current_id == snapshot_id:
            # Fall back to most recent remaining
            if self.snapshots:
                self.current_id = max(
                    self.snapshots.values(), key=lambda s: s["timestamp"]
                )["id"]
            else:
                self.current_id = None

    def strip_snapshots(self) -> None:
        """Remove inline data from all snapshots (for slim JSON storage)."""
        for snap in self.snapshots.values():
            snap.pop("data", None)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshots": self.snapshots,
            "current_id": self.current_id,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_id(self) -> str:
        for _ in range(10):
            sid = str(uuid.uuid4())[:8]
            if sid not in self.snapshots:
                return sid
        raise ValueError("Failed to generate unique snapshot ID after 10 attempts")

    @staticmethod
    def _count_seqs(data: dict | None) -> int:
        if not data:
            return 0
        from utils import KEY_BATCH_DATA
        batch = data.get(KEY_BATCH_DATA, [])
        return len(batch) if isinstance(batch, list) else 0


# ------------------------------------------------------------------
# Diff function
# ------------------------------------------------------------------

def diff_snapshots(old_batch: list[dict], new_batch: list[dict]) -> list[dict]:
    """Compare two batch lists by sequence_number, return per-sequence diffs.

    Returns a list of dicts:
        {
            "seq_num": int,
            "status": "unchanged" | "changed" | "added" | "removed",
            "changes": [{"field": str, "old": Any, "new": Any}],
        }
    """
    from utils import KEY_SEQUENCE_NUMBER

    old_by_seq = {int(s.get(KEY_SEQUENCE_NUMBER, 0)): s for s in old_batch}
    new_by_seq = {int(s.get(KEY_SEQUENCE_NUMBER, 0)): s for s in new_batch}

    all_seqs = sorted(set(old_by_seq) | set(new_by_seq))
    result = []

    for seq_num in all_seqs:
        old_item = old_by_seq.get(seq_num)
        new_item = new_by_seq.get(seq_num)

        if old_item and not new_item:
            result.append({"seq_num": seq_num, "status": "removed", "changes": []})
        elif new_item and not old_item:
            result.append({"seq_num": seq_num, "status": "added", "changes": []})
        else:
            # Both exist — field-by-field comparison
            all_keys = sorted(set(old_item) | set(new_item))
            changes = []
            for k in all_keys:
                old_val = old_item.get(k)
                new_val = new_item.get(k)
                if old_val != new_val:
                    changes.append({"field": k, "old": old_val, "new": new_val})
            status = "changed" if changes else "unchanged"
            result.append({"seq_num": seq_num, "status": status, "changes": changes})

    return result
