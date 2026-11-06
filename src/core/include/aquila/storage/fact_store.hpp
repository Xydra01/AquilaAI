#pragma once

#include "aquila/storage/sqlite_db.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::storage {

struct FactEntry {
    int64_t id{0};
    std::string topic;
    std::string fact;
    std::string timestamp;
};

class FactStore {
public:
    explicit FactStore(SqliteDb db);
    ~FactStore() = default;

    FactStore(const FactStore&) = delete;
    FactStore& operator=(const FactStore&) = delete;
    FactStore(FactStore&&) noexcept = default;
    FactStore& operator=(FactStore&&) noexcept = default;

    static FactStore open(const std::filesystem::path& db_path);
    static FactStore open_memory();

    SqliteDb& db() noexcept { return db_; }
    const SqliteDb& db() const noexcept { return db_; }

    void init_tables();

    // Semantic Facts
    std::string store_fact(std::string_view topic, std::string_view fact);
    std::string get_all_facts() const;
    std::vector<FactEntry> query_facts(std::string_view topic) const;

    // Scratchpad Notes
    std::string save_scratchpad_note(std::string_view task_name,
                                     std::string_view note,
                                     std::string_view instance_id = "");
    std::string get_scratchpad_notes(std::string_view task_name,
                                     std::string_view instance_id = "") const;

    // Workspace Summaries
    void save_workspace_summary(std::string_view instance_id,
                                std::string_view task_name,
                                std::string_view summary_text);
    std::string get_workspace_summary(std::string_view instance_id,
                                      std::string_view task_name) const;

private:
    SqliteDb db_;

    static std::string scratchpad_key(std::string_view task_name, std::string_view instance_id);
};

}  // namespace aquila::storage

