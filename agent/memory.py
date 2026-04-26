import sqlite3
import chromadb
from pathlib import Path
from datetime import datetime

class DualMemorySystem:
    """Manages both Semantic Facts (SQLite) and Episodic Experiences (ChromaDB)."""
    
    def __init__(self, storage_dir: str = "Agent-Memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        
        self.db_path = self.storage_dir / "fact_graph.db"
        self._init_sqlite()
        
        self.chroma_client = chromadb.PersistentClient(path=str(Path.cwd() / "agent" / "vector_db"))
        self.collection = self.chroma_client.get_or_create_collection(name="episodic_experiences")
        self.tool_collection = self.chroma_client.get_or_create_collection(name="agent_tools")

    # --- TOOL ROUTING ---
    def index_tools(self, tools_dict: dict):
        """Embeds all available tools into the vector database on startup."""
        if not tools_dict: return
        
        ids = []
        documents = []
        
        for name, info in tools_dict.items():
            ids.append(name)
            documents.append(f"Tool Name: {name}. Description: {info['description']}")
            
        self.tool_collection.upsert(
            documents=documents,
            ids=ids
        )
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
            conn.commit()

    # --- SCRATCHPAD ---
    def save_scratchpad_note(self, task_name: str, note: str) -> str:
        """Saves a temporary research note tied to the current task."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO scratchpad (task_name, note) VALUES (?, ?)", (task_name, note))
            conn.commit()
        return f"✅ Data securely saved to SQLite scratchpad for task: {task_name}"

    def get_scratchpad_notes(self, task_name: str) -> str:
        """Retrieves all notes gathered for the current task."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT note FROM scratchpad WHERE task_name = ? ORDER BY timestamp ASC", (task_name,))
            rows = cursor.fetchall()
            
        if not rows:
            return "No research notes found for this task."
            
        compiled_notes = f"=== SCRATCHPAD NOTES FOR {task_name} ===\n"
        for idx, row in enumerate(rows):
            compiled_notes += f"--- Note {idx + 1} ---\n{row[0]}\n\n"
        return compiled_notes

    # --- SEMANTIC MEMORY ---
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

    # --- LONG TERM MEMORY ---
    def store_experience(self, task_name: str, summary: str):
        """Embeds a completed task summary into the vector database."""
        doc_id = f"{task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.collection.add(
            documents=[summary],
            metadatas=[{"task": task_name, "date": datetime.now().isoformat()}],
            ids=[doc_id]
        )
        print(f"🧠 System encoded episodic memory for: {task_name}")

    def recall_experiences(self, query: str, n_results: int = 3) -> str:
        """Performs a semantic search to find similar past tasks."""
        if self.collection.count() == 0:
            return "No past experiences to draw from."
            
        results = self.collection.query(
            query_texts=[query],
            n_results=min(n_results, self.collection.count())
        )
        
        if not results['documents'] or not results['documents'][0]:
            return "No relevant past experiences found."
            
        recalled = "=== RELEVANT PAST EXPERIENCES ===\n"
        for idx, doc in enumerate(results['documents'][0]):
            recalled += f"Memory {idx + 1}: {doc}\n\n"
            
        return recalled