import sqlite3
import sys
import os
import threading
import chromadb
from pathlib import Path
from datetime import datetime

from .workspace_paths import agent_data_path, get_vector_db_path
from .embeddings import embedding_collection_tag, get_aquila_embedding_function


def _pytest_running() -> bool:
    return "pytest" in sys.modules


def _make_chroma_client(chroma_path: str | Path | None):
    """Persistent in production; ephemeral in pytest unless a test passes chroma_path."""
    if chroma_path is not None:
        chroma_dir = Path(chroma_path)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(chroma_dir))
    persist = os.getenv("AQUILA_TEST_PERSIST_CHROMA", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if _pytest_running() and not persist:
        return chromadb.EphemeralClient()
    chroma_dir = get_vector_db_path()
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_dir))


def _index_timeout_seconds() -> float:
    raw = os.getenv("AQUILA_TOOL_INDEX_TIMEOUT_SEC", "45").strip()
    try:
        return max(0.01, float(raw))
    except ValueError:
        return 45.0


def _keyword_route(objective: str, tool_docs: dict[str, str], max_tools: int) -> list[str]:
    """Offline lexical fallback when Chroma routing is unavailable."""
    import re

    tokens = set(re.findall(r"[a-z0-9]+", (objective or "").lower()))
    if not tokens:
        return list(tool_docs.keys())[:max_tools]
    scored: list[tuple[int, str]] = []
    for name, doc in tool_docs.items():
        blob = f"{name} {doc}".lower().replace("_", " ")
        words = set(re.findall(r"[a-z0-9]+", blob))
        score = len(tokens & words)
        if name.lower() in (objective or "").lower():
            score += 5
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if scored:
        return [n for _, n in scored[:max_tools]]
    return list(tool_docs.keys())[:max_tools]


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

        # Defer Chroma/ONNX until store/index/recall needs it. Opening PersistentClient
        # + loading MiniLM on every first chat was hanging packaged installs before
        # any Ollama request was sent.
        self._chroma_path_override = (
            Path(chroma_path) if chroma_path is not None else None
        )
        self.chroma_client = None
        self.collection = None
        self.tool_collection = None
        self._embedding_fn = None
        self._tools_indexed = False
        self._tool_docs: dict[str, str] = {}

    def _resolved_chroma_dir(self) -> Path:
        if self._chroma_path_override is not None:
            return self._chroma_path_override
        return get_vector_db_path()

    @staticmethod
    def _dir_nonempty(path: Path) -> bool:
        try:
            return path.is_dir() and any(path.iterdir())
        except OSError:
            return False

    def _ensure_chroma(self) -> bool:
        """Open Chroma + embedding function on first real vector use."""
        if self.chroma_client is not None and self.collection is not None:
            return True
        try:
            self._embedding_fn = get_aquila_embedding_function()
            tag = embedding_collection_tag()
            self.chroma_client = _make_chroma_client(self._chroma_path_override)
            self.collection = self.chroma_client.get_or_create_collection(
                name=f"episodic_experiences_{tag}",
                embedding_function=self._embedding_fn,
            )
            safe_id = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in self.instance_id
            )
            self.tool_collection = self.chroma_client.get_or_create_collection(
                name=f"agent_tools_{safe_id}_{tag}",
                embedding_function=self._embedding_fn,
            )
            return True
        except Exception as exc:
            try:
                from agent.core import human_print

                human_print(f"Chroma unavailable ({exc}) — continuing without vectors.")
            except Exception:
                pass
            self.chroma_client = None
            self.collection = None
            self.tool_collection = None
            return False

    def close(self) -> None:
        """Release Chroma native handles (important during long pytest runs on Windows)."""
        client = getattr(self, "chroma_client", None)
        if client is None:
            return
        try:
            reset = getattr(client, "reset", None)
            if callable(reset):
                reset()
        except Exception:
            pass
        self.chroma_client = None
        self.collection = None
        self.tool_collection = None
        self._tools_indexed = False

    def _scratchpad_key(self, task_name: str) -> str:
        return f"{self.instance_id}::{task_name}"

    # Tool Routing
    def index_tools(self, tools_dict: dict):
        """Embed tools into Chroma using an offline-safe embedding function."""
        if not tools_dict:
            return
        if not self._ensure_chroma() or self.tool_collection is None:
            # Still keep docs for keyword routing.
            self._tool_docs = {}
            for name, info in tools_dict.items():
                desc = info.get("description", "")
                self._tool_docs[name] = f"Tool Name: {name}. Description: {desc}"
            return
        if self._tools_indexed and self.tool_collection.count() >= len(tools_dict):
            return
        ids = []
        documents = []

        try:
            from agent.policies import routing_document_for_tool
        except ImportError:
            routing_document_for_tool = None

        self._tool_docs = {}
        for name, info in tools_dict.items():
            ids.append(name)
            desc = info.get("description", "")
            if routing_document_for_tool:
                doc = routing_document_for_tool(name, desc)
            else:
                doc = f"Tool Name: {name}. Description: {desc}"
            documents.append(doc)
            self._tool_docs[name] = doc

        error_box: list[BaseException] = []

        def _upsert() -> None:
            try:
                self.tool_collection.upsert(documents=documents, ids=ids)
            except BaseException as exc:  # noqa: BLE001
                error_box.append(exc)

        timeout = _index_timeout_seconds()
        worker = threading.Thread(target=_upsert, name="aquila-tool-index", daemon=True)
        worker.start()
        worker.join(timeout=timeout)
        if worker.is_alive():
            from agent.core import human_print

            human_print(
                f"Tool index timed out after {timeout:.0f}s — using keyword routing."
            )
            return
        if error_box:
            from agent.core import human_print

            human_print(f"Tool index failed ({error_box[0]}) — using keyword routing.")
            return

        self._tools_indexed = True
        from agent.core import human_print

        human_print(f"System indexed {len(ids)} tools into the semantic router.")

    def route_tools(self, objective: str, max_tools: int = 15) -> list[str]:
        """Finds the most relevant tools for the current objective."""
        if self._tool_docs and (
            self.tool_collection is None
            or self.tool_collection.count() == 0
            or not self._tools_indexed
        ):
            return _keyword_route(objective, self._tool_docs, max_tools)

        if self.tool_collection is None or self.tool_collection.count() == 0:
            if self._tool_docs:
                return _keyword_route(objective, self._tool_docs, max_tools)
            return []

        try:
            results = self.tool_collection.query(
                query_texts=[objective],
                n_results=min(max_tools, self.tool_collection.count()),
            )
            ids = results["ids"][0] if results.get("ids") else []
            if ids:
                return ids
        except Exception:
            pass
        if self._tool_docs:
            return _keyword_route(objective, self._tool_docs, max_tools)
        return []

    def _init_sqlite(self):
        """Creates the fact and scratchpad tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT,
                    fact TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scratchpad (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT,
                    note TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_summaries (
                    instance_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (instance_id, task_name)
                )
            """
            )
            conn.commit()

    # Scratchpad
    def save_scratchpad_note(
        self, task_name: str, note: str, instance_id: str | None = None
    ) -> str:
        """Saves a temporary research note tied to the current task."""
        key = (
            self._scratchpad_key(task_name)
            if instance_id is None
            else f"{instance_id}::{task_name}"
        )
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO scratchpad (task_name, note) VALUES (?, ?)", (key, note)
            )
            conn.commit()
        return f"✅ Data securely saved to SQLite scratchpad for task: {task_name}"

    def get_scratchpad_notes(
        self, task_name: str, instance_id: str | None = None
    ) -> str:
        """Retrieves all notes gathered for the current task."""
        key = (
            self._scratchpad_key(task_name)
            if instance_id is None
            else f"{instance_id}::{task_name}"
        )
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

    def get_workspace_summary_row(
        self, task_name: str, instance_id: str | None = None
    ) -> str:
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
            cursor.execute(
                "INSERT INTO facts (topic, fact) VALUES (?, ?)",
                (topic.lower(), fact),
            )
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
    def store_experience(
        self,
        task_name: str,
        summary: str,
        instance_id: str | None = None,
        *,
        mode: str | None = None,
        walkthrough_path: str | None = None,
        deliverable_path: str | None = None,
        plan_approach: str | None = None,
        user_verified: bool = False,
    ):
        """Embeds a completed task summary into the vector database."""
        iid = instance_id or self.instance_id
        doc_id = f"{iid}_{task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        metadata: dict = {
            "task": task_name,
            "instance_id": iid,
            "date": datetime.now().isoformat(),
        }
        if mode:
            metadata["mode"] = mode
        if walkthrough_path:
            metadata["walkthrough_path"] = walkthrough_path[:500]
        if deliverable_path:
            metadata["deliverable_path"] = deliverable_path[:500]
        if plan_approach:
            metadata["plan_approach"] = plan_approach[:500]
        metadata["user_verified"] = user_verified

        if not self._ensure_chroma() or self.collection is None:
            from agent.core import human_print

            human_print(
                f"Episodic store skipped (Chroma unavailable) for: {task_name} [{iid}]"
            )
            return

        self.collection.add(
            documents=[summary],
            metadatas=[metadata],
            ids=[doc_id],
        )
        from agent.core import human_print

        human_print(f"System encoded episodic memory for: {task_name} [{iid}]")

    def recall_experiences(
        self, query: str, n_results: int = 3, instance_id: str | None = None
    ) -> str:
        """Performs a semantic search to find similar past tasks."""
        if not isinstance(n_results, int) or n_results <= 0:
            return "No past experiences to draw from."

        # Do not open Chroma/ONNX on a cold chat when there is no vector data yet.
        if self.collection is None:
            chroma_dir = self._resolved_chroma_dir()
            if not self._dir_nonempty(chroma_dir):
                return "No past experiences to draw from."
            if not self._ensure_chroma():
                return "No past experiences to draw from."

        if self.collection is None or self.collection.count() == 0:
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
