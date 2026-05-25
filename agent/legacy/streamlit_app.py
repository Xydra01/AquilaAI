# Web UI
import streamlit as st
import os
import json
from pathlib import Path

# Import the direct instances from main
from main import global_agent, client, initiate_sleep_cycle

# Page Configuration
st.set_page_config(page_title="Aquila OS", page_icon="🦅", layout="wide")

with st.sidebar:
    st.header("🦅 Aquila OS Controls")
    st.markdown("Select how you want Aquila to handle your next request.")
    
    operation_mode = st.radio(
        "Operation Mode:",
        [
            "💬 Chat", 
            "⚙️ Autonomous Task",
            "🔍 Research Mode"
        ],
        help="Select the specialized environment for your request."
    )
    
    st.divider()
    
    if st.button("🌙 Initiate Sleep Cycle", use_container_width=True):
        with st.spinner("Consolidating memories & flushing cache..."):
            sleep_report = initiate_sleep_cycle()
            st.session_state.messages.append({"role": "assistant", "content": sleep_report})
            st.rerun()

# Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "System Online. How can I assist you today?"}
    ]

# Split-Pane Layout
chat_col, ledger_col = st.columns([1.5, 1])

# Right Pane
with ledger_col:
    st.header("📋 Active Task Ledger")
    st.markdown("---")
    
    ledger_placeholder = st.empty() 
    
    tasks_dir = Path("Agent-Tasks")
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

# Left Pane
with chat_col:
    st.header("💬 Terminal")
    st.markdown("---")
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Command Aquila..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            if operation_mode == "💬 Chat":
                
                with st.spinner("Aquila is searching her memory..."):
                    message_placeholder = st.empty()
                    
                    try:
                        system_facts = global_agent.memory.get_all_facts()
                        past_experiences = global_agent.memory.recall_experiences(prompt, n_results=20)
                    except Exception as e:
                        system_facts = "*(Error retrieving facts)*"
                        past_experiences = "*(Error retrieving experiences)*"
                        st.sidebar.error(f"Memory Error: {e}")

                    base_system_prompt = (
                        "You are Aquila, an advanced autonomous AI. You are highly intelligent, slightly dry/witty, and speak with quiet confidence. "
                        "You are currently in Chat Mode. Have a natural conversation with the user and assist them directly.\\n\\n"
                        "=== YOUR INTERNAL KNOWLEDGE BASE ===\\n"
                        f"{system_facts}\\n\\n"
                        f"{past_experiences}\\n\\n"
                        "Use the knowledge above to inform your answers. If the information is not relevant to the user's current question, ignore it."
                    )
                    
                    chat_history = [{"role": "system", "content": base_system_prompt}]
            
                    recent_msgs = st.session_state.messages[-40:] 
                    while recent_msgs and recent_msgs[0]["role"] != "user":
                        recent_msgs.pop(0)
                    
                    for msg in recent_msgs:
                        chat_history.append({"role": msg["role"], "content": msg["content"]})
                
                    try:
                        final_response = client.chat(chat_history, temperature=0.6, timeout=60)
                        if not final_response or not final_response.strip():
                            final_response = "*(System Error: The LLM returned a blank string. Check terminal logs.)*"
                    except Exception as e:
                        if "timed out" in str(e).lower():
                            final_response = "*(System Timeout: The local model took too long to process the injected memory context.)*"
                        else:
                            final_response = f"*(API Error: {str(e)})*"
                        
                    message_placeholder.markdown(final_response)
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                    
            elif operation_mode == "⚙️ Autonomous Task":
                status_placeholder = st.empty()
                clean_prompt = "".join(c if c.isalnum() or c.isspace() else "" for c in prompt)
                task_name = "_".join(clean_prompt.split()[:4]).lower() or "unnamed_task"
                status_placeholder.info(f"🚀 Initializing autonomous task: `{task_name}`")
                
                try:
                    final_result = global_agent.run_unified_task(
                        task_name=task_name, 
                        user_request=prompt, 
                        mode="autonomous",
                        ledger_placeholder=ledger_placeholder
                    )
                    status_placeholder.success("Execution Complete.")
                    st.session_state.messages.append({"role": "assistant", "content": f"**Task '{task_name}' Finished.**\n\nResult: {final_result}"})
                except Exception as e:
                    status_placeholder.error(f"Task Engine Error: {e}")

            elif operation_mode == "🔍 Research Mode":
                status_placeholder = st.empty()
                clean_prompt = "".join(c if c.isalnum() or c.isspace() else "" for c in prompt)
                research_topic = "_".join(clean_prompt.split()[:4]).lower() or "unnamed_research"
                status_placeholder.info(f"📚 Initializing Deep-Dive Research: `{research_topic}`")
                
                try:
                    final_report = global_agent.run_unified_task(
                        task_name=research_topic, 
                        user_request=prompt, 
                        mode="research",
                        ledger_placeholder=ledger_placeholder
                    )
                    status_placeholder.success("Research Complete.")
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"**Research Data Compiled: '{research_topic}'**\n\nCheck your `Agent-Research/` directory.\n\nSummary:\n{final_report}"
                    })
                except Exception as e:
                    status_placeholder.error(f"Research Engine Error: {e}")
                    
        st.rerun()

# Task manager and resume
with st.sidebar:
    st.divider()
    st.subheader("📂 Task Manager")
    
    # Scan both directories!
    tasks_dir = Path("Agent-Tasks")
    plans_dir = Path("Agent-Plans")
    
    pending_files = []
    if tasks_dir.exists(): pending_files.extend([(f, "autonomous") for f in tasks_dir.glob("*.json")])
    if plans_dir.exists(): pending_files.extend([(f, "research") for f in plans_dir.glob("*.json")])
        
    if pending_files:
        # Create a display name indicating the mode
        task_options = {f"{f.stem} ({mode.title()})": (f.stem, mode) for f, mode in pending_files}
        selected_display = st.selectbox("In-Progress Ledgers:", list(task_options.keys()))
        
        task_to_resume, task_mode = task_options[selected_display]
        
        if st.button("▶️ Resume Selected", use_container_width=True):
            resume_msg = f"Resuming {task_mode} background process: {task_to_resume}..."
            st.session_state.messages.append({"role": "user", "content": resume_msg})
            
            with st.spinner(f"Waking up Aquila for '{task_to_resume}'..."):
                try:
                    final_result = global_agent.run_unified_task(
                        task_name=task_to_resume, 
                        user_request="Resume and complete the remaining objectives in the task ledger.", 
                        mode=task_mode,
                        ledger_placeholder=ledger_placeholder
                    )
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": f"**Process '{task_to_resume}' Finished.**\n\nResult: {final_result}"
                    })
                except Exception as e:
                    st.error(f"Engine Error: {e}")
            st.rerun()
    else:
        st.caption("No pending ledgers. Desk is clean.")