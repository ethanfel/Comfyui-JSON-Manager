import streamlit as st
import requests
from PIL import Image
from io import BytesIO
import urllib.parse
from utils import save_config

def render_single_instance(instance_config, index, all_instances):
    url = instance_config.get("url", "http://127.0.0.1:8188")
    name = instance_config.get("name", f"Server {index+1}")
    
    COMFY_URL = url.rstrip("/")
    
    c_head, c_set = st.columns([3, 1])
    c_head.markdown(f"### 🔌 {name}")
    
    with c_set.popover("⚙️ Settings"):
        st.caption("Press Update to apply changes!")
        new_name = st.text_input("Name", value=name, key=f"name_{index}")
        new_url = st.text_input("URL", value=url, key=f"url_{index}")
        
        if new_url != url:
            st.warning("⚠️ Unsaved URL! Click Update below.")

        if st.button("💾 Update & Save", key=f"save_{index}", type="primary"):
            all_instances[index]["name"] = new_name
            all_instances[index]["url"] = new_url
            st.session_state.config["comfy_instances"] = all_instances
            
            save_config(
                st.session_state.current_dir, 
                st.session_state.config['favorites'], 
                st.session_state.config # Save full config including new keys
            )
            st.toast("Server config saved!", icon="💾")
            st.rerun()
            
        st.divider()
        if st.button("🗑️ Remove Server", key=f"del_{index}"):
            all_instances.pop(index)
            st.session_state.config["comfy_instances"] = all_instances
            save_config(
                st.session_state.current_dir, 
                st.session_state.config['favorites'], 
                st.session_state.config
            )
            st.rerun()

    # --- 1. STATUS DASHBOARD ---
    with st.expander("📊 Server Status", expanded=True):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        try:
            res = requests.get(f"{COMFY_URL}/queue", timeout=1.5)
            queue_data = res.json()
            running_cnt = len(queue_data.get("queue_running", []))
            pending_cnt = len(queue_data.get("queue_pending", []))
            
            col1.metric("Status", "🟢 Online" if running_cnt > 0 else "💤 Idle")
            col2.metric("Pending", pending_cnt)
            col3.metric("Running", running_cnt)
            
            if col4.button("🔄 Check Img", key=f"refresh_{index}", use_container_width=True):
                 st.session_state[f"force_img_refresh_{index}"] = True
        except Exception:
            col1.metric("Status", "🔴 Offline")
            col2.metric("Pending", "-")
            col3.metric("Running", "-")
            st.error(f"Could not connect to API at {COMFY_URL}")
    
    # --- 2. LIVE VIEW (VIA REMOTE BROWSER) ---
    st.write("") 
    c_label, c_ctrl = st.columns([1, 2])
    c_label.subheader("📺 Live View")
    
    enable_preview = c_ctrl.checkbox("Enable Live Preview", value=True, key=f"live_toggle_{index}")
    
    if enable_preview:
        # Height Slider
        iframe_h = st.slider(
            "Height (px)", 
            min_value=600, max_value=2500, value=1000, step=50, 
            key=f"h_slider_{index}"
        )

        # Get Configured Viewer URL
        viewer_base = st.session_state.config.get("viewer_url", "http://192.168.1.51:5800")
        
        # Most Firefox containers (like jlesage/firefox) act as VNC clients and don't take ?url=
        # So we just frame the VNC/Web interface.
        final_src = viewer_base

        st.info(f"Viewing via Remote Browser: `{final_src}`")
        st.caption(f"🎯 Target ComfyUI: `{COMFY_URL}` (You may need to type this into the remote browser manually)")

        st.markdown(
            f"""
            <iframe src="{final_src}" width="100%" height="{iframe_h}px" 
                style="border: 2px solid #666; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            </iframe>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info("Live Preview is disabled.")

    st.markdown("---")

    # --- 3. LATEST OUTPUT ---
    if st.session_state.get(f"force_img_refresh_{index}", False):
        st.caption("🖼️ Most Recent Output")
        try:
            hist_res = requests.get(f"{COMFY_URL}/history", timeout=2)
            history = hist_res.json()
            if history:
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
                    st.image(image, caption=f"Last Output: {img_name}")
                else:
                    st.warning("Last run had no image output.")
            else:
                st.info("No history found.")
            st.session_state[f"force_img_refresh_{index}"] = False
        except Exception as e:
            st.error(f"Error fetching image: {e}")

def render_comfy_monitor():
    # --- GLOBAL SETTINGS FOR MONITOR ---
    with st.expander("🔧 Monitor Settings (Remote Browser)", expanded=False):
        current_viewer = st.session_state.config.get("viewer_url", "http://192.168.1.51:5800")
        new_viewer = st.text_input("Remote Browser URL (Firefox/Neko)", value=current_viewer, help="e.g., http://192.168.1.51:5800 or http://localhost:8080")
        
        if st.button("💾 Save Monitor Settings"):
            st.session_state.config["viewer_url"] = new_viewer
            save_config(
                st.session_state.current_dir, 
                st.session_state.config['favorites'], 
                st.session_state.config
            )
            st.success("Monitor settings saved!")
            st.rerun()

    # --- INSTANCE MANAGEMENT ---
    if "comfy_instances" not in st.session_state.config:
        st.session_state.config["comfy_instances"] = [
            {"name": "Main Server", "url": "http://192.168.1.100:8188"}
        ]
    
    instances = st.session_state.config["comfy_instances"]
    tab_names = [i["name"] for i in instances] + ["➕ Add Server"]
    tabs = st.tabs(tab_names)
    
    for i, tab in enumerate(tabs[:-1]):
        with tab:
            render_single_instance(instances[i], i, instances)
            
    with tabs[-1]:
        st.header("Add New ComfyUI Instance")
        with st.form("add_server_form"):
            new_name = st.text_input("Server Name", placeholder="e.g. Render Node 2")
            new_url = st.text_input("URL", placeholder="http://192.168.1.50:8188")
            if st.form_submit_button("Add Instance"):
                if new_name and new_url:
                    instances.append({"name": new_name, "url": new_url})
                    st.session_state.config["comfy_instances"] = instances
                    
                    save_config(
                        st.session_state.current_dir, 
                        st.session_state.config['favorites'], 
                        st.session_state.config
                    )
                    st.success("Server Added!")
                    st.rerun()
                else:
                    st.error("Please fill in both Name and URL.")