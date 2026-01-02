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
        """Generates a Compact, Readable Horizontal Graph using HTML Labels."""
        dot = [
            'digraph History {',
            '  rankdir=LR;',
            '  bgcolor="white";', 
            '  splines=ortho;', # Clean right-angle lines
            
            # TIGHT SPACING
            '  nodesep=0.2;',
            '  ranksep=0.3;',
            
            # GLOBAL STYLES
            '  node [shape=plain, fontname="Arial"];', 
            '  edge [color="#888888", arrowsize=0.6, penwidth=1.0];'
        ]
        
        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])
        
        for n in sorted_nodes:
            nid = n["id"]
            full_note = n.get('note', 'Step')
            
            # Truncate slightly for display, but keep enough to read
            # HTML Labels allow distinct styling for Title vs ID
            display_note = (full_note[:15] + '..') if len(full_note) > 15 else full_note
            
            # COLORS
            bg_color = "#f9f9f9"
            border_color = "#999999"
            border_width = "1"
            
            if nid == self.head_id:
                bg_color = "#fff6cd" # Yellow for Current
                border_color = "#eebb00"
                border_width = "2"
            elif nid in self.branches.values():
                bg_color = "#e6ffe6" # Green for Tips
                border_color = "#66aa66"

            # HTML LABEL (Table)
            # This is the trick to make it compact but readable
            label = (
                f'<<TABLE BORDER="{border_width}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" BGCOLOR="{bg_color}" COLOR="{border_color}">'
                f'<TR><TD><B><FONT POINT-SIZE="10">{display_note}</FONT></B></TD></TR>'
                f'<TR><TD><FONT POINT-SIZE="8" COLOR="#555555">{nid[:4]}</FONT></TD></TR>'
                f'</TABLE>>'
            )
            
            # Tooltip shows full text on hover
            safe_tooltip = full_note.replace('"', "'")
            dot.append(f'  "{nid}" [label={label}, tooltip="{safe_tooltip}"];')
            
            if n["parent"] and n["parent"] in self.nodes:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')
                
        dot.append("}")
        return "\n".join(dot)
