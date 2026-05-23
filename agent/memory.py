import sqlite3
import chromadb
from pathlib import Path
from datetime import datetime

from workspace_paths import agent_data_path, get_vector_db_path


class DualMemorySystem:
    """Manages both Semantic Facts (SQLite) and Episodic Experiences (ChromaDB)."""
    
    def __init__(
        self,
        storage_dir: str | Path | None = None,
        instance_id: str = "default",
        *,
        chroma_path: str | Path | None = None,
    ):
        self.instance_id = instance_id or "default"
        self.storage_dir = (
            Path(storage_dir) if storage_dir is not None else agent_data_path("Agent-Memory")
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.storage_dir / "fact_graph.db"
        self._init_sqlite()
        
        chroma_dir = Path(chroma_path) if chroma_path is not None else get_vector_db_path()
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
        self.collection = self.chroma_client.get_or_create_collection(name="episodic_experiences")
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.instance_id)
        self.tool_collection = self.chroma_client.get_or_create_collection(
            name=f"agent_tools_{safe_id}"
        )
        self._tools_indexed = False

    def _scratchpad_key(self, task_name: str) -> str:
        return f"{self.instance_id}::{task_name}"

    # Tool Routing
    def index_tools(self, tools_dict: dict):
        """Embeds all available tools into the vector database on startup."""
        if not tools_dict:
            return
        if self._tools_indexed and self.tool_collection.count() >= len(tools_dict):
            return

        ids = []
        documents = []

        try:
            from tool_catalog import routing_document_for_tool
        except ImportError:
            try:
                from recon_policy import routing_document_for_tool
            except ImportError:
                routing_document_for_tool = None

        for name, info in tools_dict.items():
            ids.append(name)
            desc = info.get("description", "")
            if routing_document_for_tool:
                documents.append(routing_document_for_tool(name, desc))
            else:
                documents.append(f"Tool Name: {name}. Description: {desc}")

        self.tool_collection.upsert(
            documents=documents,
            ids=ids
        )
        self._tools_indexed = True
        # #region agent log
        try:
            import json as _json
            import time as _time
            from pathlib import Path as _Path

            _log = _Path(__file__).resolve().parents[1] / "debug-5063e5.log"
            with open(_log, "a", encoding="utf-8") as _f:
                _f.write(
                    _json.dumps(
                        {
                            "sessionId": "5063e5",
                            "hypothesisId": "H1",
                            "location": "memory.py:index_tools",
                            "message": "tools_indexed",
                            "data": {
                                "instance_id": self.instance_id,
                                "collection": self.tool_collection.name,
                                "count": len(ids),
                            },
                            "timestamp": int(_time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass
        # #endregion
        print(f"🛠️ System indexed {len(ids)} tools into the semantic router.")

    def route_tools(self, objective: str, max_tools: int = 15) -> list[str]:
        """Finds the most relevant tools for the current objective."""
        if self.tool_collection.count() == 0: return []
        
        results = self.tool_collection.query(
            query_texts=[objective],
            n_results=min(max_tools, self.tool_collection.count())
        )
        return results['ids'][0] if results['ids'] else []

    def _init_sqlite(self):
        """Creates the fact and scratchpad tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT,
                    fact TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scratchpad (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT,
                    note TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workspace_summaries (
                    instance_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (instance_id, task_name)
                )
            ''')
            conn.commit()

    # Scratchpad
    def save_scratchpad_note(self, task_name: str, note: str, instance_id: str | None = None) -> str:
        """Saves a temporary research note tied to the current task."""
        key = self._scratchpad_key(task_name) if instance_id is None else f"{instance_id}::{task_name}"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO scratchpad (task_name, note) VALUES (?, ?)", (key, note))
            conn.commit()
        return f"✅ Data securely saved to SQLite scratchpad for task: {task_name}"

    def get_scratchpad_notes(self, task_name: str, instance_id: str | None = None) -> str:
        """Retrieves all notes gathered for the current task."""
        key = self._scratchpad_key(task_name) if instance_id is None else f"{instance_id}::{task_name}"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT note FROM scratchpad WHERE task_name = ? ORDER BY timestamp ASC",
                (key,),
            )
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(
                    "SELECT note FROM scratchpad WHERE task_name = ? ORDER BY timestamp ASC",
                    (task_name,),
                )
                rows = cursor.fetchall()
            
        if not rows:
            return "No research notes found for this task."
            
        compiled_notes = f"=== SCRATCHPAD NOTES FOR {task_name} ===\n"
        for idx, row in enumerate(rows):
            compiled_notes += f"--- Note {idx + 1} ---\n{row[0]}\n\n"
        return compiled_notes

    def list_scratchpad_task_names(self, instance_id: str | None = None) -> list[str]:
        """Distinct scratchpad keys for this instance (suffix after 'instance::')."""
        iid = instance_id or self.instance_id
        prefix = f"{iid}::"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT task_name FROM scratchpad WHERE task_name LIKE ?",
                (f"{prefix}%",),
            )
            rows = cursor.fetchall()
        names: list[str] = []
        for (key,) in rows:
            if key.startswith(prefix):
                names.append(key[len(prefix) :])
            else:
                names.append(key)
        return names

    def save_workspace_summary_row(
        self, task_name: str, summary_text: str, instance_id: str | None = None
    ) -> None:
        iid = instance_id or self.instance_id
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO workspace_summaries (instance_id, task_name, summary_text, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(instance_id, task_name) DO UPDATE SET
                    summary_text=excluded.summary_text,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (iid, task_name, summary_text),
            )
            conn.commit()

    def get_workspace_summary_row(self, task_name: str, instance_id: str | None = None) -> str:
        iid = instance_id or self.instance_id
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT summary_text FROM workspace_summaries WHERE instance_id = ? AND task_name = ?",
                (iid, task_name),
            )
            row = cursor.fetchone()
        return row[0] if row else ""

    # Semantic Memory
    def store_fact(self, topic: str, fact: str) -> str:
        """Stores an absolute rule or preference."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO facts (topic, fact) VALUES (?, ?)", (topic.lower(), fact))
            conn.commit()
        return f"✅ Fact securely stored under topic '{topic}'."

    def get_all_facts(self) -> str:
        """Retrieves all stored facts to inject into the Planner's context."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT topic, fact FROM facts ORDER BY topic")
            rows = cursor.fetchall()
            
        if not rows:
            return "No permanent facts stored yet."
            
        formatted_facts = "=== PERMANENT SYSTEM FACTS & LORE ===\n"
        for topic, fact in rows:
            formatted_facts += f"- [{topic.upper()}]: {fact}\n"
        return formatted_facts

    # Long Term Episodic Memory
    def store_experience(self, task_name: str, summary: str, instance_id: str | None = None):
        """Embeds a completed task summary into the vector database."""
        iid = instance_id or self.instance_id
        doc_id = f"{iid}_{task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.collection.add(
            documents=[summary],
            metadatas=[{
                "task": task_name,
                "instance_id": iid,
                "date": datetime.now().isoformat(),
            }],
            ids=[doc_id],
        )
        print(f"🧠 System encoded episodic memory for: {task_name} [{iid}]")

    def recall_experiences(self, query: str, n_results: int = 3, instance_id: str | None = None) -> str:
        """Performs a semantic search to find similar past tasks."""
        if self.collection.count() == 0:
            return "No past experiences to draw from."

        iid = instance_id or self.instance_id
        where_filter = {"instance_id": iid}
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count()),
                where=where_filter,
            )
        except Exception:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count()),
            )

        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        if not docs[0]:
            return "No relevant past experiences found."

        recalled = "=== RELEVANT PAST EXPERIENCES ===\n"
        shown = 0
        for doc, meta in zip(docs[0], metas[0] if metas else [{}] * len(docs[0])):
            if meta and meta.get("instance_id") not in (None, iid):
                continue
            shown += 1
            recalled += f"Memory {shown}: {doc}\n\n"
            if shown >= n_results:
                break
        if shown == 0:
            return "No relevant past experiences found."
        return recalled
