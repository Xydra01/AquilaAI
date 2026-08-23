"""Local data tools: SQLite/SQL execution and basic REST HTTP clients."""
from __future__ import annotations

import sqlite3
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from agent.core import format_tool_result


def execute_sql_query(db_path: str, query: str) -> str:
    """
    Execute a read-only SQL query against a local SQLite database.
    USE WHEN: You need to extract structured data from a local SQLite database file.
    """
    path = Path(db_path).resolve()
    if not path.exists():
        return format_tool_result("ERROR", "execute_sql_query failed", f"Database file not found: {path}")

    # Restrict to SELECT queries for safety by default
    if not query.strip().upper().startswith(("SELECT", "PRAGMA")):
        return format_tool_result("ERROR", "execute_sql_query failed", "Only SELECT and PRAGMA queries are permitted for safety.")

    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if not rows:
                return format_tool_result("OK", "execute_sql_query", "(No results)")
            
            # Format results as JSON
            results = [dict(row) for row in rows]
            # Truncate output if too large
            out_str = json.dumps(results, indent=2)
            if len(out_str) > 15000:
                out_str = out_str[:15000] + "\n... (truncated)"
                
            return format_tool_result("OK", "execute_sql_query", out_str)
            
    except Exception as e:
        return format_tool_result("ERROR", "execute_sql_query failed", str(e))


def rest_api_client(url: str, method: str = "GET", headers_json: str = "{}", payload_json: str = "") -> str:
    """
    Make a generic HTTP request to a local or external REST API.
    USE WHEN: You need to interface with a local server, fetch JSON, or test a webhook.
    """
    try:
        headers = json.loads(headers_json)
        data = None
        if payload_json:
            data = payload_json.encode('utf-8')

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8', errors='replace')
            status = response.status
            
            try:
                # Try to pretty print if it's JSON
                parsed = json.loads(content)
                content = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                pass
                
            if len(content) > 15000:
                content = content[:15000] + "\n... (truncated)"
                
            return format_tool_result("OK", f"HTTP {status}", content)

    except urllib.error.HTTPError as e:
        content = e.read().decode('utf-8', errors='replace')
        return format_tool_result("ERROR", f"HTTP {e.code}", content)
    except Exception as e:
        return format_tool_result("ERROR", "rest_api_client failed", str(e))


DATA_TOOLS: dict[str, dict[str, Any]] = {
    "execute_sql_query": {
        "func": execute_sql_query,
        "description": "Execute a read-only SQL query against a local SQLite database.",
    },
    "rest_api_client": {
        "func": rest_api_client,
        "description": "Make a generic HTTP request to a local or external REST API.",
    },
}
