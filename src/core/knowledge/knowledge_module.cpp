#include "aquila/knowledge/knowledge_module.hpp"

#include <filesystem>
#include <sstream>

namespace aquila::knowledge {

namespace {

std::string format_experiences(const std::vector<ScoredMatch>& matches) {
    if (matches.empty()) {
        return "No relevant past experiences found.";
    }
    std::ostringstream oss;
    oss << "### Recalled Experiences (" << matches.size() << "):\n\n";
    for (std::size_t i = 0; i < matches.size(); ++i) {
        const auto& m = matches[i];
        oss << "**[" << (i + 1) << "] ID: " << m.id << "** *(similarity: " << m.score << ")*\n";
        if (m.metadata.is_object()) {
            if (m.metadata.contains("task") && m.metadata["task"].is_string()) {
                oss << "*Task:* " << m.metadata["task"].get<std::string>() << "\n";
            }
            if (m.metadata.contains("date") && m.metadata["date"].is_string()) {
                oss << "*Date:* " << m.metadata["date"].get<std::string>() << "\n";
            }
        }
        oss << m.content << "\n\n";
    }
    return oss.str();
}

} // namespace

KnowledgeModule::KnowledgeModule(const ModuleContext& ctx)
    : ctx_(ctx), max_output_chars_(ctx.max_output_chars) {
    if (ctx.workspace_root.empty()) {
        init_db(":memory:");
    } else {
        auto db_dir = ctx.workspace_root / ".aquila";
        std::filesystem::create_directories(db_dir);
        init_db((db_dir / "knowledge.db").string());
    }
}

void KnowledgeModule::init_db(const std::string& db_path_str) {
    if (db_path_str == ":memory:") {
        fact_store_ = std::make_unique<storage::FactStore>(storage::FactStore::open_memory());
    } else {
        fact_store_ = std::make_unique<storage::FactStore>(storage::FactStore::open(db_path_str));
    }

    embedder_ = std::make_shared<HashingEmbedder>(384);
    vector_index_ = std::make_unique<VectorIndex>(fact_store_->db(), embedder_);
    page_cache_ = std::make_unique<PageCache>(fact_store_->db());
    doc_index_ = std::make_unique<LocalDocIndex>(fact_store_->db(), embedder_);
}

std::vector<ActionSchema> KnowledgeModule::get_actions() const {
    return {
        ActionSchema{
            .action_name = "search_local_docs",
            .description = "Search local repository markdown documentation using hybrid dense vector and sparse lexical retrieval",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", {
                    {"query", {{"type", "string"}, {"description", "Search query or natural language question"}}},
                    {"max_results", {{"type", "integer"}, {"description", "Maximum number of sections to return", "default", 5}}}
                }},
                {"required", {"query"}}
            }
        },
        ActionSchema{
            .action_name = "fetch_and_clean_url",
            .description = "Fetch and extract clean readable text and title from a web page using persistent zero-I/O caching",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", {
                    {"url", {{"type", "string"}, {"description", "HTTP or HTTPS URL to fetch"}}},
                    {"bypass_cache", {{"type", "boolean"}, {"description", "Force network refresh bypassing cache", "default", false}}}
                }},
                {"required", {"url"}}
            }
        },
        ActionSchema{
            .action_name = "store_fact",
            .description = "Persist an established fact or lore item into long-term fact graph storage",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", {
                    {"topic", {{"type", "string"}, {"description", "Topic category or entity name"}}},
                    {"fact", {{"type", "string"}, {"description", "The fact or knowledge string to store"}}}
                }},
                {"required", {"topic", "fact"}}
            }
        },
        ActionSchema{
            .action_name = "recall_experiences",
            .description = "Recall past task experiences and episodic memory using semantic vector similarity",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", {
                    {"query", {{"type", "string"}, {"description", "Natural language query describing task or error"}}},
                    {"top_k", {{"type", "integer"}, {"description", "Maximum number of experiences to recall", "default", 3}}},
                    {"instance_id", {{"type", "string"}, {"description", "Optional instance filter"}}}
                }},
                {"required", {"query"}}
            }
        },
        ActionSchema{
            .action_name = "get_all_facts",
            .description = "Retrieve all long-term facts formatted for LLM system prompt context",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", Json::object()}
            }
        }
    };
}

void KnowledgeModule::configure(const Json& initial_state) {
    if (initial_state.is_null()) return;

    if (initial_state.contains("max_output_chars")) {
        max_output_chars_ = initial_state["max_output_chars"].get<std::size_t>();
    }

    if (initial_state.contains("db_path")) {
        auto p = initial_state["db_path"].get<std::string>();
        init_db(p);
    }
}

Json KnowledgeModule::export_state_snapshot() const {
    Json facts_arr = Json::array();
    auto fact_stmt = fact_store_->db().prepare("SELECT topic, fact FROM facts ORDER BY topic ASC, id ASC");
    while (fact_stmt.step()) {
        facts_arr.push_back(Json{
            {"topic", std::string(fact_stmt.column_text(0))},
            {"fact", std::string(fact_stmt.column_text(1))}
        });
    }

    Json notes_arr = Json::array();
    auto note_stmt = fact_store_->db().prepare("SELECT task_name, note FROM scratchpad ORDER BY id ASC");
    while (note_stmt.step()) {
        notes_arr.push_back(Json{
            {"task_name", std::string(note_stmt.column_text(0))},
            {"note", std::string(note_stmt.column_text(1))}
        });
    }

    return Json{
        {"facts", std::move(facts_arr)},
        {"scratchpad", std::move(notes_arr)},
        {"cached_pages_count", page_cache_->size()},
        {"doc_chunks_count", doc_index_->chunk_count()}
    };
}

void KnowledgeModule::restore_state_snapshot(const Json& snapshot) {
    if (!snapshot.is_object()) {
        throw SchemaError("", "KnowledgeModule state snapshot must be a JSON object");
    }

    storage::SqliteTx tx(fact_store_->db());

    if (snapshot.contains("facts") && snapshot["facts"].is_array()) {
        for (const auto& item : snapshot["facts"]) {
            if (item.contains("topic") && item.contains("fact")) {
                fact_store_->store_fact(item["topic"].get<std::string>(), item["fact"].get<std::string>());
            }
        }
    }

    if (snapshot.contains("scratchpad") && snapshot["scratchpad"].is_array()) {
        for (const auto& item : snapshot["scratchpad"]) {
            if (item.contains("task_name") && item.contains("note")) {
                fact_store_->save_scratchpad_note(
                    item["task_name"].get<std::string>(),
                    item["note"].get<std::string>()
                );
            }
        }
    }

    tx.commit();
}

ActionResult KnowledgeModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "search_local_docs") {
        const auto query = args.at("query").get<std::string>();
        const int max_results = args.value("max_results", 5);
        auto matches = doc_index_->search_hybrid(query, static_cast<std::size_t>(max_results));
        return capped(ok(doc_index_->format_search_results(matches)));
    }

    if (action_name == "fetch_and_clean_url") {
        const auto url = args.at("url").get<std::string>();
        const bool bypass = args.value("bypass_cache", false);
        try {
            auto page = page_cache_->fetch_and_clean(url, bypass);
            std::string out = "Title: " + page.title + "\nSource: " + page.url +
                              (page.from_cache ? " (cached)\n\n" : "\n\n") + page.clean_text;
            return capped(ok(out));
        } catch (const FetchError& e) {
            return fail("fetch_error", e.what());
        } catch (const std::exception& e) {
            return fail("fetch_error", e.what());
        }
    }

    if (action_name == "store_fact") {
        const auto topic = args.at("topic").get<std::string>();
        const auto fact = args.at("fact").get<std::string>();
        auto confirm = fact_store_->store_fact(topic, fact);
        return ok(confirm);
    }

    if (action_name == "recall_experiences") {
        const auto query = args.at("query").get<std::string>();
        const int top_k = args.value("top_k", 3);
        std::optional<std::string> inst;
        if (args.contains("instance_id") && !args["instance_id"].is_null()) {
            inst = args["instance_id"].get<std::string>();
        }

        auto matches = vector_index_->search_dense("episodic_experiences", query, static_cast<std::size_t>(top_k), inst);
        return capped(ok(format_experiences(matches)));
    }

    if (action_name == "get_all_facts") {
        auto lore = fact_store_->get_all_facts();
        return capped(ok(lore));
    }

    return fail("unknown_action", "KnowledgeModule does not support action: " + action_name);
}

ActionResult KnowledgeModule::capped(ActionResult r) const {
    if (r.llm_facing_output.size() > max_output_chars_) {
        r.llm_facing_output.resize(max_output_chars_);
        r.llm_facing_output.append("\n[... output truncated ...]");
        r.token_estimate = estimate_tokens(r.llm_facing_output);
    }
    return r;
}

} // namespace aquila::knowledge

