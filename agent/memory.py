import sqlite3
from datetime import datetime
from typing import List, Dict

class AgentMemory:
    """Short-term session memory (Legacy). 
    Mostly bypassed now that the agent uses the OS Partner Task Ledger (.md files)."""
    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self.summary = ""

    def update_summary(self, action_type: str, content: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.history.append({"time": timestamp, "type": action_type, "content": content})
        
        # Keep only last 10 actions to prevent overflow
        if len(self.history) > 10:
            self.history.pop(0)

    def get_summary(self) -> str:
        if not self.history:
            return "No recent actions."
        return "\n".join([f"[{item['time']}] {item['type']}: {item['content']}" for item in self.history])


class LongTermMemory:
    """SQLite-based persistent memory for the OS Partner."""
    def __init__(self, db_path="memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                resolution TEXT,
                tags TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def add_memory(self, memory_text: str):
        """
        The new bridge method called by the 'TASK COMPLETE' kill switch in main.py.
        Extracts the task name and saves the details.
        """
        task_name = "Completed Task"
        if "Successfully completed task:" in memory_text:
            # Extract just the task name from the main.py formatted string
            task_name = memory_text.split("Final prompt was:")[0].replace("Successfully completed task:", "").strip()
            
        self.store_experience(task=task_name, resolution=memory_text)

    def store_experience(self, task: str, resolution: str, tags: List[str] = None):
        """Core storage method."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        tags_str = ",".join(tags) if tags else ""
        
        cursor.execute(
            "INSERT INTO experiences (task, resolution, tags) VALUES (?, ?, ?)",
            (task, resolution, tags_str)
        )
        conn.commit()
        conn.close()

    def retrieve_relevant_experience(self, keyword: str, limit: int = 3) -> str:
        """
        SMART SEARCH: Splits the agent's keyword string into individual words
        and searches the database for ANY of those words, ranking by recency.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Strip out tiny words like "a", "an", "to" and split into a list
        search_terms = [k.strip() for k in keyword.split() if len(k.strip()) > 2]
        
        # Fallback if the agent just searched one small word
        if not search_terms:
            search_terms = [keyword.strip()]

        # Dynamically build an SQL query that checks for ANY of the search terms
        query_conditions = " OR ".join(["task LIKE ? OR resolution LIKE ? OR tags LIKE ?" for _ in search_terms])
        
        params = []
        for term in search_terms:
            # We add the term 3 times because we check task, resolution, and tags
            params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
            
        query = f"""
            SELECT task, resolution, timestamp 
            FROM experiences 
            WHERE {query_conditions}
            ORDER BY timestamp DESC 
            LIMIT ?
        """
        params.append(limit)
        
        try:
            cursor.execute(query, params)
            results = cursor.fetchall()
        except Exception as e:
            conn.close()
            return f"Database search error: {str(e)}"
            
        conn.close()
        
        if not results:
            return f"No past experiences found containing the keywords: '{keyword}'."
            
        formatted_results = "📚 PAST EXPERIENCES FOUND:\n\n"
        for task, resolution, timestamp in results:
            formatted_results += f"[{timestamp}] TASK: {task}\nNOTES: {resolution}\n" + "-"*30 + "\n"
            
        return formatted_results