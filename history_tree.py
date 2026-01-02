import time
import uuid

class HistoryTree:
    def __init__(self, raw_data):
        self.nodes = raw_data.get("nodes", {})
        self.branches = raw_data.get("branches", {"main": None}) 
        self.head_id = raw_data.get("head_id", None)
        
        if "prompt_history" in raw_data and isinstance(raw_data["prompt_history"], list) and not self.nodes:
            self._migrate_legacy(raw_data["prompt_history"])

    def _migrate_legacy(self, old_list):
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

    def commit(self, data, note="Snapshot"):
        new_id = str(uuid.uuid4())[:8]
        
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

    def checkout(self, node_id):
        if node_id in self.nodes:
            self.head_id = node_id
            return self.nodes[node_id]["data"]
        return None

    def to_dict(self):
        return {"nodes": self.nodes, "branches": self.branches, "head_id": self.head_id}

    def generate_horizontal_graph(self):
        """Generates a Fixed-Size, Compact Horizontal Graph."""
        dot = [
            'digraph History {',
            '  rankdir=LR;',
            '  bgcolor="white";', # Clean background
            
            # --- COMPACT LAYOUT SETTINGS ---
            '  nodesep=0.15;',   # Horizontal gap between nodes
            '  ranksep=0.25;',   # Vertical gap between branches
            
            # --- FIXED SIZE NODES (The Key Fix) ---
            # fixedsize=true: Ignores text length, forces the width/height below.
            # width=1.2: Sets box width to ~100px
            # height=0.4: Sets box height to ~30px
            '  node [shape=box, style="filled,rounded", fillcolor="#f9f9f9", fontname="Arial", fontsize=9, fixedsize=true, width=1.3, height=0.45];',
            '  edge [color="#666666", arrowsize=0.5, penwidth=1.0];'
        ]
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])
        
        for n in sorted_nodes:
            nid = n["id"]
            
            # Truncate text to fit in the 1.3 inch box
            full_note = n.get('note', 'Step')
            short_note = (full_note[:10] + '..') if len(full_note) > 10 else full_note
            
            label = f"{short_note}\\n{nid[:4]}"
            
            # Colors
            color = "#f0f0f0" 
            penwidth = "1"
            
            if nid == self.head_id:
                color = "#fff6cd" # Yellow for Active
                penwidth = "2"
            
            if nid in self.branches.values():
                if color == "#f0f0f0": color = "#e6ffe6" # Green for Branch Tips
            
            dot.append(f'  "{nid}" [label="{label}", fillcolor="{color}", penwidth="{penwidth}"];')
            
            if n["parent"] and n["parent"] in self.nodes:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')
                
        dot.append("}")
        return "\n".join(dot)
