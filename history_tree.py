import time
import uuid
from typing import Any

KEY_PROMPT_HISTORY = "prompt_history"


class HistoryTree:
    def __init__(self, raw_data: dict[str, Any]) -> None:
        self.nodes: dict[str, dict[str, Any]] = raw_data.get("nodes", {})
        self.branches: dict[str, str | None] = raw_data.get("branches", {"main": None})
        self.head_id: str | None = raw_data.get("head_id", None)

        if KEY_PROMPT_HISTORY in raw_data and isinstance(raw_data[KEY_PROMPT_HISTORY], list) and not self.nodes:
            self._migrate_legacy(raw_data[KEY_PROMPT_HISTORY])

    def _migrate_legacy(self, old_list: list[dict[str, Any]]) -> None:
        parent = None
        for item in reversed(old_list):
            node_id = str(uuid.uuid4())[:8]
            self.nodes[node_id] = {
                "id": node_id, "parent": parent, "timestamp": time.time(),
                "data": item, "note": item.get("note", "Legacy Import")
            }
            parent = node_id
        self.branches["main"] = parent
        self.head_id = parent

    def commit(self, data: dict[str, Any], note: str = "Snapshot") -> str:
        new_id = str(uuid.uuid4())[:8]

        # Cycle detection: walk parent chain from head to verify no cycle
        if self.head_id:
            visited = set()
            current = self.head_id
            while current:
                if current in visited:
                    raise ValueError(f"Cycle detected in history tree at node {current}")
                visited.add(current)
                node = self.nodes.get(current)
                current = node["parent"] if node else None

        active_branch = None
        for b_name, tip_id in self.branches.items():
            if tip_id == self.head_id:
                active_branch = b_name
                break
        
        if not active_branch:
            base_name = "branch"
            count = 1
            while f"{base_name}_{count}" in self.branches: count += 1
            active_branch = f"{base_name}_{count}"
            
        self.nodes[new_id] = {
            "id": new_id, "parent": self.head_id, "timestamp": time.time(),
            "data": data, "note": note
        }
        self.branches[active_branch] = new_id
        self.head_id = new_id
        return new_id

    def checkout(self, node_id: str) -> dict[str, Any] | None:
        if node_id in self.nodes:
            self.head_id = node_id
            return self.nodes[node_id]["data"]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "branches": self.branches, "head_id": self.head_id}

    # --- UPDATED GRAPH GENERATOR ---
    def generate_graph(self, direction: str = "LR") -> str:
        """
        Generates Graphviz source.
        direction: "LR" (Horizontal) or "TB" (Vertical)
        """
        node_count = len(self.nodes)
        if node_count <= 5:
            nodesep, ranksep = 0.5, 0.6
        elif node_count <= 15:
            nodesep, ranksep = 0.3, 0.4
        else:
            nodesep, ranksep = 0.15, 0.25

        # Build reverse lookup: branch tip -> branch name(s)
        tip_to_branches: dict[str, list[str]] = {}
        for b_name, tip_id in self.branches.items():
            if tip_id:
                tip_to_branches.setdefault(tip_id, []).append(b_name)

        dot = [
            'digraph History {',
            f'  rankdir={direction};',
            '  bgcolor="white";',
            '  splines=ortho;',
            f'  nodesep={nodesep};',
            f'  ranksep={ranksep};',
            '  node [shape=plain, fontname="Arial"];',
            '  edge [color="#888888", arrowsize=0.6, penwidth=1.0];'
        ]

        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])

        for n in sorted_nodes:
            nid = n["id"]
            full_note = n.get('note', 'Step')

            display_note = (full_note[:25] + '..') if len(full_note) > 25 else full_note

            ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))

            # Branch label for tip nodes
            branch_label = ""
            if nid in tip_to_branches:
                branch_label = ", ".join(tip_to_branches[nid])

            # COLORS
            bg_color = "#f9f9f9"
            border_color = "#999999"
            border_width = "1"

            if nid == self.head_id:
                bg_color = "#fff6cd"
                border_color = "#eebb00"
                border_width = "2"
            elif nid in self.branches.values():
                bg_color = "#e6ffe6"
                border_color = "#66aa66"

            # HTML LABEL
            rows = [
                f'<TR><TD><B><FONT POINT-SIZE="10">{display_note}</FONT></B></TD></TR>',
                f'<TR><TD><FONT POINT-SIZE="8" COLOR="#555555">{ts} • {nid[:4]}</FONT></TD></TR>',
            ]
            if branch_label:
                rows.append(f'<TR><TD><FONT POINT-SIZE="8" COLOR="#4488cc"><I>{branch_label}</I></FONT></TD></TR>')

            label = (
                f'<<TABLE BORDER="{border_width}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" BGCOLOR="{bg_color}" COLOR="{border_color}">'
                + "".join(rows)
                + '</TABLE>>'
            )

            safe_tooltip = full_note.replace('"', "'")
            dot.append(f'  "{nid}" [label={label}, tooltip="{safe_tooltip}"];')

            if n["parent"] and n["parent"] in self.nodes:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')

        dot.append("}")
        return "\n".join(dot)
