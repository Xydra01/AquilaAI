"""Local calendar tools for managing schedule via SQLite and parsing .ics files."""
from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any

from agent.core import format_tool_result
from agent.storage import agent_data_path


def _get_calendar_db() -> Path:
    db_path = agent_data_path("Agent-Data") / "calendar_v4.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.execute('''
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT UNIQUE,
                    summary TEXT,
                    description TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    location TEXT
                )
            ''')
    return db_path


def import_calendar_ics(ics_path_or_content: str) -> str:
    """
    Import a standard .ics calendar file into the native local calendar database.
    USE WHEN: You need to ingest schedule data from other applications into Aquila.
    """
    path = Path(ics_path_or_content).resolve()
    content = ""
    if path.exists() and path.is_file():
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return format_tool_result("ERROR", "import_calendar_ics failed to read file", str(e))
    else:
        content = ics_path_or_content

    if "BEGIN:VCALENDAR" not in content:
        return format_tool_result("ERROR", "import_calendar_ics failed", "Invalid ICS content")

    # A very primitive ICS parser for demonstration/v4 foundation
    events = []
    current_event: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            current_event = {}
        elif line == "END:VEVENT":
            events.append(current_event)
        elif line.startswith("UID:"):
            current_event["uid"] = line[4:]
        elif line.startswith("SUMMARY:"):
            current_event["summary"] = line[8:]
        elif line.startswith("DESCRIPTION:"):
            current_event["description"] = line[12:]
        elif line.startswith("DTSTART"):
            current_event["start_time"] = line.split(":")[-1]
        elif line.startswith("DTEND"):
            current_event["end_time"] = line.split(":")[-1]
        elif line.startswith("LOCATION:"):
            current_event["location"] = line[9:]

    imported_count = 0
    try:
        db_path = _get_calendar_db()
        with sqlite3.connect(db_path) as conn:
            for ev in events:
                try:
                    conn.execute('''
                        INSERT INTO events (uid, summary, description, start_time, end_time, location)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(uid) DO UPDATE SET
                            summary=excluded.summary,
                            description=excluded.description,
                            start_time=excluded.start_time,
                            end_time=excluded.end_time,
                            location=excluded.location
                    ''', (
                        ev.get("uid"), ev.get("summary"), ev.get("description"),
                        ev.get("start_time"), ev.get("end_time"), ev.get("location")
                    ))
                    imported_count += 1
                except sqlite3.Error:
                    pass
        return format_tool_result("OK", "import_calendar_ics", f"Successfully imported/updated {imported_count} events.")
    except Exception as e:
        return format_tool_result("ERROR", "import_calendar_ics failed", str(e))


CALENDAR_TOOLS: dict[str, dict[str, Any]] = {
    "import_calendar_ics": {
        "func": import_calendar_ics,
        "description": "Import a standard .ics calendar file into the native local calendar database.",
    },
}
