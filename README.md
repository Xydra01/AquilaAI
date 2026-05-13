# 🦅 AquilaAI (Version 3.1)

**A Multi-Modal, Locally-Run Autonomous Agent OS**

AquilaAI is an advanced, tool-based autonomous agent designed to execute complex research, software development, and system operation tasks. Built entirely around open-source, locally hosted LLMs (via Ollama), AquilaAI acts as a true digital colleague capable of deep compartmentalization, memory management, and self-correction.

## 🚀 Key Features

### 1. The Unified Execution Engine

In Version 3.1, AquilaAI abandoned legacy reactive chat loops in favor of a robust, state-managed **Unified Execution Loop**.

* **The OS Enforcer:** Aquila operates on a strict iteration budget per objective. If she gets stuck debugging code or falls down a research rabbit hole, the OS Enforcer physically interrupts her context window, forcing her to save her work and advance to the next step.
* **The "Kill Switch":** Integrated watchdog timers protect local hardware from infinite loops or generation hang-ups.

### 2. Deep-Dive Research & Autonomous Tasking

AquilaAI operates across distinct, specialized modes routed through a Streamlit UI:

* **🔍 Research Mode:** Utilizes an integrated, privacy-focused web scraper (with Cloudflare bypass and native PDF parsing) to autonomously gather, synthesize, and extract targeted data.
* **⚙️ Autonomous Task:** Empowers Aquila to write multi-file software projects, manipulate local directories, and run automated testing.
* **💬 Cognitive Chat:** A fast, RAG-injected chat interface for rapid interactions that bypasses the heavy tool-execution loop.

### 3. The JSON "Final Report" Schema

Aquila uses a strictly constrained JSON schema for all internal monologue and tool execution. By injecting the `"final_report"` key directly into her root schema, the OS securely extracts massive, heavily formatted Markdown documentation and code blocks without breaking the Python JSON parsers.

### 4. Epistemic State Tracking (The Scratchpad)

To prevent context-window bloat, Aquila undergoes a complete short-term memory wipe between objectives. To survive this, she relies on **The First Step Rule** and a **Mandatory Paper Trail**:

* She must use the `save_research_note` tool to dump variables, code structures, and facts to her local scratchpad.
* Upon starting a new objective, her very first autonomous action is to use `read_all_research_notes` to re-orient herself and pass the context to her "future self."

## 🛠️ Architecture Stack

* **LLM Engine:** Ollama (Local)
* **Web Search:** Local SearXNG Instance
* **UI/Frontend:** Streamlit
* **Web Extraction:** BeautifulSoup, PyMuPDF, Cloudscraper

## 🏁 Getting Started & Setup

Currently, AquilaAI v3.1 requires manual orchestration of its backend services.

### Prerequisites

* **Python 3.10+**
* **Ollama** (Locally installed and running)
* **Docker** (Required for the SearXNG local search container)

### Step 1: Initialize the LLM Engine

Ensure Ollama is running on your machine and that you have pulled your preferred target model.

```bash
ollama serve
ollama pull llama3  # Or your designated Aquila model

```

### Step 2: Spin Up Local Web Search (SearXNG)

Aquila relies on a local SearXNG instance to perform privacy-respecting, rate-limit-free web scraping. Start the container via Docker:

```bash
docker run -d -p 8080:8080 searxng/searxng

```

### Step 3: Install Python Dependencies

Clone the repository and install the required environmental packages:

```bash
git clone https://github.com/your-repo/aquila-ai.git
cd aquila-ai
pip install -r requirements.txt

```

### Step 4: Launch the OS

Boot up the Streamlit interface to access the Unified Execution Engine:

```bash
streamlit run app.py

```

Navigate to `http://localhost:8501` in your browser. From the sidebar, you can select between Chat, Research, or Task modes and begin deploying Aquila.

## 🔮 The Roadmap (Version 4.0 "True OS")

The 3.x era is laying the groundwork for Aquila's evolution into a persistent desktop OS.

* **v3.2:** Transition to a Python Qt (PySide6) GUI with a real-time, side-by-side Writing Canvas. This update will also introduce a **1-Click executable/installer** to automatically orchestrate Docker, local servers, and the Python backend for frictionless startup.
* **v3.3:** Code Mode Canvas with a sandboxed TDD (Test-Driven Development) loop to resolve linter/execution catch-22s.
* **v3.4:** Cross-Modal Interoperability (e.g., Write Mode autonomously triggering Research Mode).
* **v4.0:** Deep Git integration, recurring background tasks, and a unified calendar/email dashboard.
