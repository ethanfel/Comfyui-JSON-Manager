import time
import uuid

class HistoryTree:
    def __init__(self, raw_data):
        # Load existing tree or initialize fresh
        self.nodes = raw_data.get("nodes", {})
        self.branches = raw_data.get("branches", {"main": None}) # Tip of each branch
        self.head_id = raw_data.get("head_id", None) # Current active node
        
        # Migration: Convert old list-based history if found
        if "prompt_history" in raw_data and isinstance(raw_data["prompt_history"], list):
            self._migrate_legacy(raw_data["prompt_history"])

    def _migrate_legacy(self, old_list):
        """Converts old flat list to a linear tree on 'main'."""
        parent = None
        # Old list is usually newest first, so we reverse to build chronological tree
        for item in reversed(old_list):
            node_id = str(uuid.uuid4())[:8]
            self.nodes[node_id] = {
                "id": node_id,
                "parent": parent,
                "timestamp": time.time(),
                "data": item,
                "note": item.get("note", "Legacy Import")
            }
            parent = node_id
        
        self.branches["main"] = parent
        self.head_id = parent

    def get_current_node(self):
        if self.head_id and self.head_id in self.nodes:
            return self.nodes[self.head_id]
        return None

    def commit(self, data, note="Snapshot"):
        """Saves a new node. Auto-branches if we are not at the tip of a named branch."""
        new_id = str(uuid.uuid4())[:8]
        
        # Create Node
        self.nodes[new_id] = {
            "id": new_id,
            "parent": self.head_id,
            "timestamp": time.time(),
            "data": data,
            "note": note
        }
        
        # Logic: Are we extending an existing branch tip?
        active_branch = None
        for b_name, tip_id in self.branches.items():
            if tip_id == self.head_id:
                active_branch = b_name
                break
        
        if active_branch:
            # Linear extension
            self.branches[active_branch] = new_id
        else:
            # Forking! We are not at a tip, so we must be in the past.
            # Create a new branch name
            base_name = "branch"
            count = 1
            while f"{base_name}_{count}" in self.branches:
                count += 1
            new_branch_name = f"{base_name}_{count}"
            self.branches[new_branch_name] = new_id
            
        # Move Head
        self.head_id = new_id
        return new_id

    def checkout(self, node_id):
        """Jumps to a specific point in time."""
        if node_id in self.nodes:
            self.head_id = node_id
            return self.nodes[node_id]["data"]
        return None

    def to_dict(self):
        """Export for JSON saving."""
        return {
            "nodes": self.nodes,
            "branches": self.branches,
            "head_id": self.head_id
        }

    def generate_graphviz(self):
        """Generates a DOT string for visualization."""
        dot = ["digraph History {"]
        dot.append('  rankdir=TB; node [shape=box, style=filled, fillcolor="#f0f0f0", fontname="Arial"];')
        dot.append('  edge [color="#888888"];')
        
        # Sort nodes by time for consistent layout
        sorted_nodes = sorted(self.nodes.values(), key=lambda x: x["timestamp"])
        
        for n in sorted_nodes:
            nid = n["id"]
            label = f"{n.get('note', 'Step')}\\n({nid})"
            
            # Highlight HEAD
            color = "#f0f0f0"
            penwidth = "1"
            if nid == self.head_id:
                color = "#ffeba0" # Yellow for current
                penwidth = "3"
            
            # Highlight Tips
            for b_name, tip_id in self.branches.items():
                if nid == tip_id:
                    label += f"\\n[{b_name}]"
                    if color == "#f0f0f0": color = "#d0f0c0" # Green for tips
            
            dot.append(f'  "{nid}" [label="{label}", fillcolor="{color}", penwidth="{penwidth}"];')
            
            if n["parent"]:
                dot.append(f'  "{n["parent"]}" -> "{nid}";')
                
        dot.append("}")
        return "\n".join(dot)
