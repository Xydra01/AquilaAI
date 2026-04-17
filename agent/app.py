import streamlit as st
import os
from pathlib import Path

# Import the new entry function we just made in main.py
from main import process_user_input

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
        # Display user message instantly
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Trigger Aquila's backend
        with st.chat_message("assistant"):
            with st.spinner("Aquila is processing..."):
                
                # Hand the prompt to the backend and wait for the final string
                final_response = process_user_input(prompt)
                
                # Render her response
                st.markdown(final_response)
                
        # Save her response to memory
        st.session_state.messages.append({"role": "assistant", "content": final_response})
        
        # Force the UI to refresh so the Task Ledger on the right updates!
        st.rerun()