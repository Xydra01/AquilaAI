#include "aquila/storage/fact_store.hpp"

#include <fmt/format.h>

#include <algorithm>
#include <cctype>
#include <utility>

namespace aquila::storage {

namespace {

std::string to_lower_string(std::string_view sv) {
    std::string res;
    res.reserve(sv.size());
    for (char c : sv) {
        res.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return res;
}

std::string to_upper_string(std::string_view sv) {
    std::string res;
    res.reserve(sv.size());
    for (char c : sv) {
        res.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return res;
}

}  // namespace

FactStore::FactStore(SqliteDb db) : db_(std::move(db)) {}

FactStore FactStore::open(const std::filesystem::path& db_path) {
    auto db = SqliteDb::open(db_path);
    FactStore store(std::move(db));
    store.init_tables();
    return store;
}

FactStore FactStore::open_memory() {
    auto db = SqliteDb::open_memory();
    FactStore store(std::move(db));
    store.init_tables();
    return store;
}

void FactStore::init_tables() {
    db_.execute(
        "CREATE TABLE IF NOT EXISTS facts ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    topic TEXT,"
        "    fact TEXT,"
        "    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
        ");");

    db_.execute(
        "CREATE TABLE IF NOT EXISTS scratchpad ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    task_name TEXT,"
        "    note TEXT,"
        "    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
        ");");

    db_.execute(
        "CREATE TABLE IF NOT EXISTS workspace_summaries ("
        "    instance_id TEXT NOT NULL,"
        "    task_name TEXT NOT NULL,"
        "    summary_text TEXT NOT NULL,"
        "    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
        "    PRIMARY KEY (instance_id, task_name)"
        ");");
}

std::string FactStore::scratchpad_key(std::string_view task_name, std::string_view instance_id) {
    if (instance_id.empty() || instance_id == "default") {
        return std::string(task_name);
    }
    return fmt::format("{}::{}", instance_id, task_name);
}

std::string FactStore::store_fact(std::string_view topic, std::string_view fact) {
    const std::string lower_topic = to_lower_string(topic);
    auto stmt = db_.prepare("INSERT INTO facts (topic, fact) VALUES (?, ?);");
    stmt.bind(1, lower_topic);
    stmt.bind(2, fact);
    stmt.step();
    return fmt::format("✅ Fact securely stored under topic '{}'.", topic);
}

std::string FactStore::get_all_facts() const {
    auto stmt = db_.prepare("SELECT topic, fact FROM facts ORDER BY topic;");

    std::string formatted_facts;
    while (stmt.step()) {
        if (formatted_facts.empty()) {
            formatted_facts = "=== PERMANENT SYSTEM FACTS & LORE ===\n";
        }
        const auto topic = stmt.column_text(0);
        const auto fact = stmt.column_text(1);
        formatted_facts += fmt::format("- [{}]: {}\n", to_upper_string(topic), fact);
    }

    if (formatted_facts.empty()) {
        return "No permanent facts stored yet.";
    }
    return formatted_facts;
}

std::vector<FactEntry> FactStore::query_facts(std::string_view topic) const {
    const std::string lower_topic = to_lower_string(topic);
    auto stmt = db_.prepare("SELECT id, topic, fact, timestamp FROM facts WHERE topic = ? ORDER BY id ASC;");
    stmt.bind(1, lower_topic);

    std::vector<FactEntry> entries;
    while (stmt.step()) {
        FactEntry entry;
        entry.id = stmt.column_int64(0);
        entry.topic = std::string(stmt.column_text(1));
        entry.fact = std::string(stmt.column_text(2));
        entry.timestamp = std::string(stmt.column_text(3));
        entries.push_back(std::move(entry));
    }
    return entries;
}

std::string FactStore::save_scratchpad_note(std::string_view task_name,
                                           std::string_view note,
                                           std::string_view instance_id) {
    const std::string key = scratchpad_key(task_name, instance_id);
    auto stmt = db_.prepare("INSERT INTO scratchpad (task_name, note) VALUES (?, ?);");
    stmt.bind(1, key);
    stmt.bind(2, note);
    stmt.step();
    return fmt::format("✅ Data securely saved to SQLite scratchpad for task: {}", task_name);
}

std::string FactStore::get_scratchpad_notes(std::string_view task_name,
                                           std::string_view instance_id) const {
    const std::string key = scratchpad_key(task_name, instance_id);
    auto stmt = db_.prepare("SELECT note FROM scratchpad WHERE task_name = ? ORDER BY timestamp ASC;");
    stmt.bind(1, key);

    std::vector<std::string> notes;
    while (stmt.step()) {
        notes.emplace_back(stmt.column_text(0));
    }

    if (notes.empty() && !instance_id.empty()) {
        // Fallback to task_name without instance_id
        stmt.reset();
        stmt.clear_bindings();
        stmt.bind(1, task_name);
        while (stmt.step()) {
            notes.emplace_back(stmt.column_text(0));
        }
    }

    if (notes.empty()) {
        return "No research notes found for this task.";
    }

    std::string compiled = fmt::format("=== SCRATCHPAD NOTES FOR {} ===\n", task_name);
    for (std::size_t i = 0; i < notes.size(); ++i) {
        compiled += fmt::format("--- Note {} ---\n{}\n\n", i + 1, notes[i]);
    }
    return compiled;
}

void FactStore::save_workspace_summary(std::string_view instance_id,
                                      std::string_view task_name,
                                      std::string_view summary_text) {
    const std::string inst = instance_id.empty() ? "default" : std::string(instance_id);
    auto stmt = db_.prepare(
        "INSERT INTO workspace_summaries (instance_id, task_name, summary_text, updated_at)"
        " VALUES (?, ?, ?, CURRENT_TIMESTAMP)"
        " ON CONFLICT(instance_id, task_name) DO UPDATE SET"
        "    summary_text=excluded.summary_text,"
        "    updated_at=CURRENT_TIMESTAMP;");
    stmt.bind(1, inst);
    stmt.bind(2, task_name);
    stmt.bind(3, summary_text);
    stmt.step();
}

std::string FactStore::get_workspace_summary(std::string_view instance_id,
                                            std::string_view task_name) const {
    const std::string inst = instance_id.empty() ? "default" : std::string(instance_id);
    auto stmt = db_.prepare(
        "SELECT summary_text FROM workspace_summaries WHERE instance_id = ? AND task_name = ?;");
    stmt.bind(1, inst);
    stmt.bind(2, task_name);

    if (stmt.step()) {
        return std::string(stmt.column_text(0));
    }
    return "";
}

}  // namespace aquila::storage
