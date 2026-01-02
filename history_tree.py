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
        """Generates a Compact Graph with HTML Labels and Tooltips."""
        dot = [
            'digraph History {',
            '  rankdir=LR;',
            '  bgcolor="white";', 
            
            # TIGHT LAYOUT
            '  nodesep=0.2;',  
            '  ranksep=0.3;',
            '  splines=ortho;', # Orthogonal lines (right angles) look cleaner/techier
            
            # BASE NODE STYLE
            '  node [shape=plain, fontname="Arial", fontsize=9];', # shape=plain for HTML labels
            '  edge [color="#888888", arrowsize=0.6, penwidth=1.0];'
        ]
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])
        
        for n in sorted_nodes:
            nid = n["id"]
            full_note = n.get('note', 'Step')
            
            # Sanitize for HTML (replace quotes)
            safe_note = full_note.replace('"', "'")
            
            # Truncate visual label
            short_note = (full_note[:12] + '..') if len(full_note) > 12 else full_note
            
            # Determine Colors
            bg_color = "#f4f4f4"
            border_color = "#cccccc"
            border_width = "1"
            
            if nid == self.head_id:
                bg_color = "#fff6cd" # Yellow
                border_color = "#eebb00"
                border_width = "2"
            elif nid in self.branches.values():
                bg_color = "#e6ffe6" # Green tip
                border_color = "#99cc99"
            
            # HTML Label Construction
            # This creates a tight table-like node
            label = (
                f'<<TABLE BORDER="{border_width}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" BGCOLOR="{bg_color}" COLOR="{border_color}">'
                f'<TR><TD><B>{short_note}</B></TD></TR>'
                f'<TR><TD><FONT POINT-SIZE="8" COLOR="#666666">{nid[:4]}</FONT></TD></TR>'
                f'</TABLE>>'
            )
            
            # Add node with Tooltip
            dot.append(f'  "{nid}" [label={label}, tooltip="{safe_note}"];')
            
            if n["parent"] and n["parent"] in self.nodes:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')
                
        dot.append("}")
        return "\n".join(dot)
