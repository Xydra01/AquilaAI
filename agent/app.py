import streamlit as st
import os
import json
from pathlib import Path

# Import the direct instances from main
from main import global_agent, client, initiate_sleep_cycle

# 1. Page Configuration
st.set_page_config(page_title="Aquila OS", page_icon="🦅", layout="wide")

with st.sidebar:
    st.header("🦅 Aquila OS Controls")
    st.markdown("Select how you want Aquila to handle your next request.")
    
    # --- THE NEW ROUTING TOGGLE ---
    operation_mode = st.radio(
        "Operation Mode:",
        ["💬 Chat", "⚙️ Autonomous Task"],
        help="Chat is for quick questions. Task wakes up the execution loop."
    )
    
    st.divider()
    
    if st.button("🌙 Initiate Sleep Cycle", use_container_width=True):
        with st.spinner("Consolidating memories & flushing cache..."):
            sleep_report = initiate_sleep_cycle()
            
            # Inject the report directly into the chat stream!
            st.session_state.messages.append({"role": "assistant", "content": sleep_report})
            st.rerun()

# 2. Session State (Memory)
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "System Online. How can I assist you today?"}
    ]

# 3. Split-Pane Layout
chat_col, ledger_col = st.columns([1.5, 1])

# --- RIGHT PANE: THE TASK LEDGER ---
with ledger_col:
    st.header("📋 Active Task Ledger")
    st.markdown("---")
    
    ledger_placeholder = st.empty() 
    
    tasks_dir = Path("Agent-Tasks")
    # --- FIX: Changed .md to .json to sync with the new architecture ---
    if tasks_dir.exists() and list(tasks_dir.glob("*.json")):
        latest_file = max(tasks_dir.glob("*.json"), key=os.path.getmtime)
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                
            with ledger_placeholder.container():
                st.subheader(f"Task: `{latest_file.stem}`")
                st.caption(f"Status: {state.get('status', 'unknown').upper()}")
                
                for i, step in enumerate(state.get("steps", [])):
                    if step["status"] == "completed":
                        st.markdown(f"✅ ~~{step['description']}~~")
                    elif i == state.get("current_step_index"):
                        st.markdown(f"🔄 **{step['description']}**")
                    else:
                        st.markdown(f"⏳ {step['description']}")
        except json.JSONDecodeError:
            ledger_placeholder.error("Error reading JSON state.")
    else:
        ledger_placeholder.info("No active tasks. Aquila is idle.")

# --- LEFT PANE: THE TERMINAL ---
with chat_col:
    st.header("💬 Terminal")
    st.markdown("---")
    
    # Render all past messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # The Chat Input Box
    if prompt := st.chat_input("Command Aquila..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            if operation_mode == "💬 Chat":
                # --- THE FAST CHAT ROUTE (QWEN OPTIMIZED) ---
                with st.spinner("Aquila is typing..."):
                    message_placeholder = st.empty()
                    
                    # Clean, standard prompt. No <think> tag instructions!
                    chat_history = [{
                        "role": "system", 
                        "content": (
                            "You are Aquila, an advanced autonomous AI. You are highly intelligent, slightly dry/witty, and speak with quiet confidence. "
                            "You are currently in Chat Mode. Have a natural conversation with the user and assist them directly."
                        )
                    }]
                    
                    recent_msgs = st.session_state.messages[-6:]
                    while recent_msgs and recent_msgs[0]["role"] != "user":
                        recent_msgs.pop(0)
                    
                    for msg in recent_msgs:
                        chat_history.append({"role": msg["role"], "content": msg["content"]})
                    
                    try:
                        # Removed max_tokens to prevent the Ollama Qwen EOS bug!
                        final_response = client.chat(chat_history, temperature=0.6, timeout=45)
                        if not final_response or not final_response.strip():
                            final_response = "*(System Error: The LLM returned a blank string. Check terminal logs.)*"
                    except Exception as e:
                        if "timed out" in str(e).lower():
                            final_response = "*(System Timeout: The local model took too long to respond.)*"
                        else:
                            final_response = f"*(API Error: {str(e)})*"
                        
                    message_placeholder.markdown(final_response)
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                    
            elif operation_mode == "⚙️ Autonomous Task":
                # --- THE HEAVY EXECUTION ROUTE ---
                status_placeholder = st.empty()
                
                clean_prompt = "".join(c if c.isalnum() or c.isspace() else "" for c in prompt)
                task_name = "_".join(clean_prompt.split()[:4]).lower() or "unnamed_task"
                
                status_placeholder.info(f"🚀 Initializing autonomous task: `{task_name}`")
                
                try:
                    final_result = global_agent.run_autonomous_task(
                        task_name=task_name, 
                        user_request=prompt, 
                        ledger_placeholder=ledger_placeholder
                    )
                    status_placeholder.success("Execution Complete.")
                    st.session_state.messages.append({"role": "assistant", "content": f"**Task '{task_name}' Finished.**\n\nResult: {final_result}"})
                except Exception as e:
                    status_placeholder.error(f"Task Engine Error: {e}")
                    
        st.rerun()