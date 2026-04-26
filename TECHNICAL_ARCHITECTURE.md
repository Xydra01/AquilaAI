# Technical Architecture Overview: agent-projects

## 📋 Executive Summary

This document provides a comprehensive technical architecture overview of the `agent-projects` directory structure. The project serves as an autonomous AI agent workspace with tool orchestration, memory management, and task execution capabilities.

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    agent-projects (Root)                         │
├─────────────────────────────────────────────────────────────────┤
│  📁 Agent-Creations/      → Output artifacts & documentation     │
│  📁 Agent-Logs/           → Execution logs & audit trails        │
│  📁 Agent-Memory/         → SQLite knowledge graph database      │
│  📁 Agent-Tasks/          → Task queue & state management        │
│  📁 agent/                → Core application codebase             │
│  📁 tool_library/         → Modular tool implementations          │
├─────────────────────────────────────────────────────────────────┤
│  📄 .env                  → Environment configuration             │
│  📄 Modelfile             → Model deployment specifications       │
│  📄 docker-compose.yml    → Container orchestration               │
│  📄 searxng-settings.yml  → Search engine configuration           │
│  📄 start.sh              → Entry point script                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Directory Structure Analysis

### 1. **Agent-Creations/**
- **Purpose:** Output artifacts, generated documentation, and research briefings
- **Key Files:**
  - `tech_briefing_2026.md` → Technical specifications and emerging tech analysis
- **Architecture Role:** Read-only output directory for agent-generated content

### 2. **Agent-Logs/**
- **Purpose:** Execution logging and audit trail maintenance
- **Key Files:**
  - `map_out_the_agentprojects.log` → Main execution log
  - `map_out_the_agentprojects_20260426_155258.log` → Timestamped session logs
- **Architecture Role:** Observability and debugging infrastructure

### 3. **Agent-Memory/**
- **Purpose:** Persistent knowledge storage using SQLite
- **Key Files:**
  - `fact_graph.db` → SQLite database for fact graph storage
- **Architecture Role:** Long-term memory and knowledge retrieval system

### 4. **Agent-Tasks/**
- **Purpose:** Task queue management and state tracking
- **Key Files:**
  - `map_out_the_agentprojects.json` → Task state and metadata
- **Architecture Role:** Task orchestration and workflow management

### 5. **agent/**
- **Purpose:** Core application logic and tool implementations
- **Subdirectories:**
  - `tool_library/` → Modular tool implementations
- **Key Files:**
  - `app.py` → Application entry point
  - `main.py` → Main execution logic
  - `memory.py` → Memory management utilities
  - `tools.py` → Tool orchestration
  - `tool_lister.py` → Tool discovery and listing
- **Architecture Role:** Core business logic and tool execution engine

### 6. **tool_library/**
- **Purpose:** Modular tool implementations
- **Key Files:**
  - `__init__.py` → Package initialization
  - `agent_tools.py` → Agent-specific tools
  - `coding_tools.py` → Code generation and manipulation
  - `email_tools.py` → Email communication utilities
  - `os_tools.py` → Operating system interactions
  - `web_tools.py` → Web scraping and search capabilities
- **Architecture Role:** Tool abstraction layer for autonomous operations

---

## 🔧 Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Database** | SQLite | Persistent knowledge graph storage |
| **Containerization** | Docker | Environment orchestration |
| **Search Engine** | SearXNG | Local web search capabilities |
| **Python** | Standard Library + External Packages | Core application logic |
| **Model Interface** | Modelfile | LLM model deployment |
| **Environment** | .env | Configuration management |

---

## 📦 Dependencies & Configuration

### Environment Variables (`.env`)
- Contains SMTP credentials for email functionality
- API keys for external services
- Configuration parameters for tool operations

### Docker Configuration (`docker-compose.yml`)
- Defines container services and networking
- Manages dependency installation
- Handles environment variable injection

### Search Configuration (`searxng-settings.yml`)
- Configures local SearXNG instance
- Defines search engine preferences
- Sets result limits and timeouts

---

## 🔄 Data Flow Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   User      │────▶│   agent/    │────▶│   tool_     │
│   Input     │     │   main.py   │     │   library/  │
└─────────────┘     └─────────────┘     └─────────────┘
                              │
                              ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Memory    │◀────│   memory.py │◀────│   agent-    │
│   (SQLite)  │     │             │     │   Tools     │
└─────────────┘     └─────────────┘     └─────────────┘
                              │
                              ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Output    │◀────│   app.py    │◀────│   Logs      │
│   (Markdown)│     │             │     │   (Agent-    │
└─────────────┘     └─────────────┘     │   Logs/)    │
                                        └─────────────┘
```

---

## 🎯 Key Architectural Patterns

### 1. **Tool Abstraction Pattern**
- Tools are modular and interchangeable
- Each tool category (coding, email, OS, web) is isolated
- Enables dynamic tool discovery via `tool_lister.py`

### 2. **Memory-First Design**
- All significant data is persisted to SQLite
- Research notes are saved before advancing objectives
- Memory wipe on objective transition ensures clean state

### 3. **Observability Pattern**
- Comprehensive logging in `Agent-Logs/`
- Timestamped log files for session tracking
- Fact graph database for knowledge retrieval

### 4. **Configuration-Driven Architecture**
- Environment variables control behavior
- Docker Compose manages deployment
- Search settings externalized for flexibility

---

## 📊 Component Interactions

### Tool Library Categories

| Tool Module | Capabilities | Use Cases |
|-------------|--------------|-----------|
| `agent_tools.py` | Objective management, state tracking | Task orchestration |
| `coding_tools.py` | File operations, code generation | Development automation |
| `email_tools.py` | SMTP communication | External notifications |
| `os_tools.py` | File system operations | Resource management |
| `web_tools.py` | Web search, page reading | Information gathering |

### Memory System
- **Storage:** SQLite database (`fact_graph.db`)
- **Access:** Vector database (ChromaDB) for semantic search
- **Lifecycle:** Notes saved via `save_research_note`, retrieved via `read_all_research_notes`

---

## 🔐 Security Considerations

- Environment variables mask sensitive credentials
- Local-only search engine (SearXNG) for privacy
- SQLite database for controlled data access
- Docker isolation for containerized services

---

## 🚀 Deployment Architecture

### Entry Points
1. **`start.sh`** → Shell script entry point
2. **`app.py`** → Python application entry
3. **`docker-compose.yml`** → Containerized deployment

### Startup Sequence
1. Load environment variables from `.env`
2. Initialize SQLite memory database
3. Load tool library modules
4. Execute main application logic
5. Begin objective processing loop

---

## 📈 Scalability Considerations

- **Horizontal Scaling:** Docker Compose enables multiple instances
- **Memory Management:** SQLite handles concurrent read operations
- **Tool Loading:** Modular tool library enables selective loading
- **Log Rotation:** Timestamped log files support rotation

---

## 🎯 Future Enhancement Areas

1. **Database Migration:** Consider PostgreSQL for larger datasets
2. **Caching Layer:** Add Redis for frequently accessed data
3. **API Gateway:** Expose tools via REST/GraphQL endpoints
4. **Monitoring:** Integrate Prometheus/Grafana for metrics
5. **CI/CD:** Add GitHub Actions for automated testing

---

## 📝 Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-26 | Aquila | Initial architecture documentation |

---

*Document generated by Aquila Autonomous AI Worker*
*Last updated: 2026-04-26*