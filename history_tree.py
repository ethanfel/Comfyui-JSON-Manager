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
        """Generates a Compact Fusion 360-style Horizontal Graph."""
        dot = [
            'digraph History {',
            '  rankdir=LR;',
            '  bgcolor="transparent";',
            # COMPACT STYLING
            '  nodesep=0.3;', 
            '  ranksep=0.4;',
            '  node [shape=rect, style="filled,rounded", fontname="Arial", fontsize=10, height=0.4, margin="0.1,0.05"];',
            '  edge [color="#888888", arrowsize=0.6, penwidth=1.0];'
        ]
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])
        
        for n in sorted_nodes:
            nid = n["id"]
            # TRUNCATE LABEL to keep box small
            full_note = n.get('note', 'Step')
            short_note = (full_note[:15] + '..') if len(full_note) > 15 else full_note
            
            label = f"{short_note}\\n<{nid[:4]}>"
            
            # Styling
            color = "#e0e0e0" 
            penwidth = "1"
            
            if nid == self.head_id:
                color = "#ffeba0" # Active Yellow
                penwidth = "2"
            
            if nid in self.branches.values():
                # Branch tips get slightly darker border
                if color == "#e0e0e0": color = "#d0f0c0" 
            
            dot.append(f'  "{nid}" [label="{label}", fillcolor="{color}", penwidth="{penwidth}"];')
            
            if n["parent"] and n["parent"] in self.nodes:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')
                
        dot.append("}")
        return "\n".join(dot)
