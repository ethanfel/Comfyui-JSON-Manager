import html
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
            for _ in range(10):
                node_id = str(uuid.uuid4())[:8]
                if node_id not in self.nodes:
                    break
            self.nodes[node_id] = {
                "id": node_id, "parent": parent, "timestamp": time.time(),
                "data": item, "note": item.get("note", "Legacy Import")
            }
            parent = node_id
        self.branches["main"] = parent
        self.head_id = parent

    def commit(self, data: dict[str, Any], note: str = "Snapshot") -> str:
        # Generate unique node ID with collision check
        for _ in range(10):
            new_id = str(uuid.uuid4())[:8]
            if new_id not in self.nodes:
                break
        else:
            raise ValueError("Failed to generate unique node ID after 10 attempts")

        # Cycle detection: walk parent chain from head to verify no cycle
        if self.head_id:
            visited = set()
            current = self.head_id
            while current:
                if current in visited:
                    raise ValueError(f"Cycle detected in history tree at node {current}")
                visited.add(current)
                node = self.nodes.get(current)
                current = node.get("parent") if node else None

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
        is_vertical = direction == "TB"

        # Vertical mode uses much tighter spacing
        if is_vertical:
            if node_count <= 5:
                nodesep, ranksep = 0.3, 0.2
            elif node_count <= 15:
                nodesep, ranksep = 0.2, 0.15
            else:
                nodesep, ranksep = 0.1, 0.1
        else:
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
            '  splines=polyline;',
            f'  nodesep={nodesep};',
            f'  ranksep={ranksep};',
            '  node [shape=plain, fontname="Arial"];',
            '  edge [color="#888888", arrowsize=0.6, penwidth=1.0];'
        ]

        # Build reverse lookup: node_id -> branch name (walk each branch ancestry)
        node_to_branch: dict[str, str] = {}
        for b_name, tip_id in self.branches.items():
            visited = set()
            current = tip_id
            while current and current in self.nodes:
                if current in visited:
                    break
                visited.add(current)
                if current not in node_to_branch:
                    node_to_branch[current] = b_name
                current = self.nodes[current].get('parent')

        # Per-branch color palette (bg, border) — cycles for many branches
        _branch_palette = [
            ('#f9f9f9', '#999999'),  # grey (default/main)
            ('#eef4ff', '#6699cc'),  # blue
            ('#f5eeff', '#9977cc'),  # purple
            ('#fff0ee', '#cc7766'),  # coral
            ('#eefff5', '#66aa88'),  # teal
            ('#fff8ee', '#ccaa55'),  # sand
        ]
        branch_names = list(self.branches.keys())
        branch_colors = {
            b: _branch_palette[i % len(_branch_palette)]
            for i, b in enumerate(branch_names)
        }

        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])

        # Font sizes and padding - smaller for vertical
        if is_vertical:
            note_font_size = 8
            meta_font_size = 7
            cell_padding = 2
            max_note_len = 18
        else:
            note_font_size = 10
            meta_font_size = 8
            cell_padding = 4
            max_note_len = 25

        for n in sorted_nodes:
            nid = n["id"]
            full_note = n.get('note', 'Step')

            display_note = (full_note[:max_note_len] + '..') if len(full_note) > max_note_len else full_note
            display_note = html.escape(display_note)

            ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))

            # Branch label for tip nodes
            branch_label = ""
            if nid in tip_to_branches:
                branch_label = html.escape(", ".join(tip_to_branches[nid]))

            # COLORS — per-branch tint, overridden for HEAD and tips
            b_name = node_to_branch.get(nid)
            bg_color, border_color = branch_colors.get(
                b_name, _branch_palette[0])
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
                f'<TR><TD><B><FONT POINT-SIZE="{note_font_size}">{display_note}</FONT></B></TD></TR>',
                f'<TR><TD><FONT POINT-SIZE="{meta_font_size}" COLOR="#555555">{ts} • {nid[:4]}</FONT></TD></TR>',
            ]
            if branch_label:
                rows.append(f'<TR><TD><FONT POINT-SIZE="{meta_font_size}" COLOR="#4488cc"><I>{branch_label}</I></FONT></TD></TR>')

            label = (
                f'<<TABLE BORDER="{border_width}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="{cell_padding}" BGCOLOR="{bg_color}" COLOR="{border_color}">'
                + "".join(rows)
                + '</TABLE>>'
            )

            safe_tooltip = (full_note
                .replace('\\', '\\\\')
                .replace('"', '\\"')
                .replace('\n', ' ')
                .replace('\r', '')
                .replace(']', '&#93;'))
            safe_nid = nid.replace('"', '_')
            dot.append(f'  "{safe_nid}" [label={label}, tooltip="{safe_tooltip}"];')

            if n.get("parent") and n["parent"] in self.nodes:
                safe_parent = n["parent"].replace('"', '_')
                dot.append(f'  "{safe_parent}" -> "{safe_nid}";')

        dot.append("}")
        return "\n".join(dot)
