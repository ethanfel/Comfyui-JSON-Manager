import streamlit as st
import json
import copy
from utils import save_json, get_file_mtime

def render_raw_editor(data, file_path):
    st.subheader(f"💻 Raw Editor: {file_path.name}")
    
    # Toggle to hide massive history objects
    # This is crucial because history trees can get huge and make the text area laggy.
    col_ctrl, col_info = st.columns([1, 2])
    with col_ctrl:
        hide_history = st.checkbox(
            "Hide History (Safe Mode)", 
            value=True, 
            help="Hides 'history_tree' and 'prompt_history' to keep the editor fast and prevent accidental deletion of version control."
        )

    # Prepare display data
    if hide_history:
        display_data = copy.deepcopy(data)
        # Safely remove heavy keys for the view only
        if "history_tree" in display_data: del display_data["history_tree"]
        if "prompt_history" in display_data: del display_data["prompt_history"]
    else:
        display_data = data

    # Convert to string
    # ensure_ascii=False ensures emojis and special chars render correctly
    try:
        json_str = json.dumps(display_data, indent=4, ensure_ascii=False)
    except Exception as e:
        st.error(f"Error serializing JSON: {e}")
        json_str = "{}"

    # The Text Editor
    # We use ui_reset_token in the key to force the text area to reload content on save
    new_json_str = st.text_area(
        "JSON Content", 
        value=json_str, 
        height=650, 
        key=f"raw_edit_{file_path.name}_{st.session_state.ui_reset_token}"
    )
    
    st.markdown("---")
    
    if st.button("💾 Save Raw Changes", type="primary", use_container_width=True):
        try:
            # 1. Parse the text back to JSON
            input_data = json.loads(new_json_str)
            
            # 2. If we were in Safe Mode, we must merge the hidden history back in
            if hide_history:
                if "history_tree" in data:
                    input_data["history_tree"] = data["history_tree"]
                if "prompt_history" in data:
                    input_data["prompt_history"] = data["prompt_history"]
            
            # 3. Save to Disk
            save_json(file_path, input_data)
            
            # 4. Update Session State
            # We clear and update the existing dictionary object so other tabs see the changes
            data.clear()
            data.update(input_data)
            
            # 5. Update Metadata to prevent conflict warnings
            st.session_state.last_mtime = get_file_mtime(file_path)
            st.session_state.ui_reset_token += 1
            
            st.toast("Raw JSON Saved Successfully!", icon="✅")
            st.rerun()
            
        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON Syntax: {e}")
            st.error("Please fix the formatting errors above before saving.")
        except Exception as e:
            st.error(f"❌ Unexpected Error: {e}")