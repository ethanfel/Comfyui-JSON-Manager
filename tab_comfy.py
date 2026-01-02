import streamlit as st
import requests
from PIL import Image
from io import BytesIO

def render_single_instance(instance_config, index, all_instances):
    """Helper to render one specific ComfyUI monitor"""
    url = instance_config.get("url", "http://127.0.0.1:8188")
    name = instance_config.get("name", f"Server {index+1}")
    
    # Clean URL
    COMFY_URL = url.rstrip("/")
    
    # --- HEADER & SETTINGS ---
    c_head, c_set = st.columns([3, 1])
    c_head.markdown(f"### 🔌 {name}")
    
    with c_set.popover("⚙️ Settings"):
        new_name = st.text_input("Name", value=name, key=f"name_{index}")
        new_url = st.text_input("URL", value=url, key=f"url_{index}")
        
        if st.button("💾 Update", key=f"save_{index}"):
            all_instances[index]["name"] = new_name
            all_instances[index]["url"] = new_url
            st.session_state.config["comfy_instances"] = all_instances
            st.rerun()
            
        st.divider()
        if st.button("🗑️ Remove Server", key=f"del_{index}"):
            all_instances.pop(index)
            st.session_state.config["comfy_instances"] = all_instances
            st.rerun()

    # --- 1. STATUS DASHBOARD ---
    col1, col2, col3 = st.columns(3)
    
    try:
        # Timeout is short to prevent UI freezing if server is down
        res = requests.get(f"{COMFY_URL}/queue", timeout=1.5)
        queue_data = res.json()
        
        running_cnt = len(queue_data.get("queue_running", []))
        pending_cnt = len(queue_data.get("queue_pending", []))
        
        col1.metric("Status", "🟢 Online" if running_cnt > 0 else "💤 Idle")
        col2.metric("Pending", pending_cnt)
        col3.metric("Running", running_cnt)

    except Exception:
        col1.metric("Status", "🔴 Offline")
        col2.metric("Pending", "-")
        col3.metric("Running", "-")
        st.error(f"Could not connect to {COMFY_URL}")
        return # Stop rendering if offline

    st.markdown("---")

    # --- 2. LIVE PREVIEW (IFRAME) ---
    with st.expander("📺 Live Interface (IFrame)", expanded=True):
        st.components.v1.iframe(src=COMFY_URL, height=600, scrolling=True)

    st.markdown("---")

    # --- 3. LATEST OUTPUT FETCHER ---
    st.subheader("🖼️ Latest Output")
    
    if st.button("🔄 Check Latest Image", key=f"refresh_{index}"):
        try:
            hist_res = requests.get(f"{COMFY_URL}/history", timeout=2)
            history = hist_res.json()
            
            if history:
                # Get most recent
                last_prompt_id = list(history.keys())[-1]
                outputs = history[last_prompt_id].get("outputs", {})
                
                found_img = None
                for node_id, node_output in outputs.items():
                    if "images" in node_output:
                        for img_info in node_output["images"]:
                            if img_info["type"] == "output":
                                found_img = img_info
                                break
                    if found_img: break
                
                if found_img:
                    img_name = found_img['filename']
                    folder = found_img['subfolder']
                    img_type = found_img['type']
                    
                    img_url = f"{COMFY_URL}/view?filename={img_name}&subfolder={folder}&type={img_type}"
                    
                    img_res = requests.get(img_url)
                    image = Image.open(BytesIO(img_res.content))
                    
                    st.image(image, caption=f"Last Output from {name}: {img_name}", use_container_width=True)
                else:
                    st.warning("Last run had no image output.")
            else:
                st.info("No history found.")
                
        except Exception as e:
            st.error(f"Error fetching image: {e}")


def render_comfy_monitor():
    # Initialize Config if missing
    if "comfy_instances" not in st.session_state.config:
        # Default to one local instance
        st.session_state.config["comfy_instances"] = [
            {"name": "Main Server", "url": "http://192.168.1.100:8188"}
        ]
    
    instances = st.session_state.config["comfy_instances"]
    
    # Create Tab Names: List of Servers + "Add New"
    tab_names = [i["name"] for i in instances] + ["➕ Add Server"]
    tabs = st.tabs(tab_names)
    
    # Render existing instances
    for i, tab in enumerate(tabs[:-1]):
        with tab:
            render_single_instance(instances[i], i, instances)
            
    # Render "Add New" Tab
    with tabs[-1]:
        st.header("Add New ComfyUI Instance")
        with st.form("add_server_form"):
            new_name = st.text_input("Server Name", placeholder="e.g. Render Node 2")
            new_url = st.text_input("URL", placeholder="http://192.168.1.50:8188")
            
            if st.form_submit_button("Add Instance"):
                if new_name and new_url:
                    instances.append({"name": new_name, "url": new_url})
                    st.session_state.config["comfy_instances"] = instances
                    st.success("Server Added!")
                    st.rerun()
                else:
                    st.error("Please fill in both Name and URL.")
