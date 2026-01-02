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
        """Generates a Compact, White-Background Horizontal Graph."""
        dot = [
            'digraph History {',
            '  rankdir=LR;',
            # 1. Force White Background (Fixes the black/transparent issue)
            '  bgcolor="white";',
            
            # 2. TIGHT Layout settings (Fixes "Too Big")
            '  nodesep=0.2;',  # Closer together horizontally
            '  ranksep=0.3;',  # Closer together vertically
            '  ratio=compress;', # Try to compress the drawing
            
            # 3. Small Node Styling
            # height=0 forces node to fit text exactly
            # margin=0.05 removes internal padding
            '  node [shape=box, style="filled,rounded", fillcolor="#f9f9f9", fontname="Arial", fontsize=9, height=0, margin="0.05,0.05"];',
            '  edge [color="#666666", arrowsize=0.5, penwidth=1.0];'
        ]
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])
        
        for n in sorted_nodes:
            nid = n["id"]
            
            # 4. Aggressive Text Truncation
            full_note = n.get('note', 'Step')
            # Keep only first 12 chars to keep box small
            short_note = (full_note[:12] + '..') if len(full_note) > 12 else full_note
            
            # Use simple label
            label = f"{short_note}\\n{nid[:4]}"
            
            # Styling
            color = "#f0f0f0" # Light Grey default
            penwidth = "1"
            
            # Active Node (HEAD) - Yellow
            if nid == self.head_id:
                color = "#fff6cd" 
                penwidth = "2"
            
            # Branch Tips - Light Green
            if nid in self.branches.values():
                if color == "#f0f0f0": color = "#e6ffe6" 
            
            dot.append(f'  "{nid}" [label="{label}", fillcolor="{color}", penwidth="{penwidth}"];')
            
            if n["parent"] and n["parent"] in self.nodes:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')
                
        dot.append("}")
        return "\n".join(dot)
