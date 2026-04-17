import streamlit as st
import os
from pathlib import Path

# Import the new entry function we just made in main.py
from main import process_user_input, dispatch_and_route, client

# 1. Page Configuration
st.set_page_config(page_title="Aquila OS", page_icon="🦅", layout="wide")

# 2. Session State (Memory)
# This keeps the chat history alive while you use the web interface
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "System Online. How can I assist you today?"}
    ]

# 3. Split-Pane Layout
# Chat gets 60% of the screen, the Task Ledger gets 40%
chat_col, ledger_col = st.columns([1.5, 1])

# --- RIGHT PANE: THE TASK LEDGER ---
with ledger_col:
    st.header("📋 Active Task Ledger")
    st.markdown("---")
    
    # Find the most recently modified markdown file in Agent-Tasks
    tasks_dir = Path("Agent-Tasks")
    if tasks_dir.exists() and list(tasks_dir.glob("*.md")):
        latest_file = max(tasks_dir.glob("*.md"), key=os.path.getmtime)
        
        with open(latest_file, "r", encoding="utf-8") as f:
            ledger_content = f.read()
            
        # Streamlit natively renders markdown perfectly!
        st.markdown(ledger_content)
    else:
        st.info("No active tasks. Aquila is idle.")

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
            with st.spinner("Aquila is thinking..."):
                
                # 1. The Fast Path Routing
                route_decision = dispatch_and_route(prompt)
                
                if route_decision.get("type") == "chat":
                    # FAST PATH: Instant chat, no tools, no loops
                    chat_history = [{"role": "system", "content": "You are Aquila. Reply concisely and naturally."}]
                    chat_history.append({"role": "user", "content": prompt})
                    
                    # Normal LLM call
                    final_response = client.chat(chat_history, temperature=0.4, max_tokens=500)
                    st.markdown(final_response)
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                    
                else:
                    # HEAVY PATH: The Autonomous Loop
                    task_name = route_decision.get("task_name", "new_task")
                    st.info(f"🚀 Initializing autonomous task: `{task_name}`")
                    
                    # TODO: Phase 3 & 4 (Planner -> Creator Loop) will go right here!
                    # For now, we just placeholder it so it doesn't crash.
                    final_response = f"I have routed this to my task queue as `{task_name}`. Ready for Phase 3!"
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                    
        st.rerun()