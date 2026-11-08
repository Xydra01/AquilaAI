#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/workspace/path_firewall.hpp"

#include <filesystem>
#include <fstream>
#include <sstream>

namespace aquila::knowledge {

using aquila::path_to_utf8;

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
            .action_name = "web_search",
            .description = "Search the web using DuckDuckGo, SearXNG, or Wikipedia, with automatic relevance and authority scoring, anti-trap defense, and deep page scraping",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", {
                    {"query", {{"type", "string"}, {"description", "Search query or natural language research topic"}}},
                    {"max_results", {{"type", "integer"}, {"description", "Maximum number of search results to return"}, {"default", 5}}},
                    {"auto_scrape", {{"type", "boolean"}, {"description", "Automatically scrape and extract clean substantive markdown from top authoritative results"}, {"default", true}}}
                }},
                {"required", {"query"}}
            }
        },
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
        },
        ActionSchema{
            .action_name = "verify_research_deliverable",
            .description = "Verify that a research report exists, meets substance and citation criteria, and facts are stored",
            .parameters_json_schema = Json{
                {"type", "object"},
                {"properties", {
                    {"file", {{"type", "string"}, {"description", "Report filename, defaults to research_report.md"}}}
                }}
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
    auto fact_stmt = fact_store_->db().prepare("SELECT topic, fact FROM facts ORDER BY id DESC LIMIT 15");
    while (fact_stmt.step()) {
        facts_arr.push_back(Json{
            {"topic", std::string(fact_stmt.column_text(0))},
            {"fact", std::string(fact_stmt.column_text(1))}
        });
    }

    Json notes_arr = Json::array();
    auto note_stmt = fact_store_->db().prepare("SELECT task_name, note FROM scratchpad ORDER BY id DESC LIMIT 10");
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
    if (action_name == "web_search") {
        const auto query = args.at("query").get<std::string>();
        const int max_results = args.value("max_results", 5);
        const bool auto_scrape = args.value("auto_scrape", true);

        auto results = search_engine_.search(query);
        if (results.empty()) {
            return ok("No search results found for query: '" + query + "'.");
        }

        std::ostringstream ss;
        ss << "Web Search Results for '" << query << "':\n\n";
        for (std::size_t i = 0; i < results.size() && static_cast<int>(i) < max_results; ++i) {
            const auto& res = results[i];
            ss << (i + 1) << ". " << res.title << "\n";
            ss << "   URL: " << res.url << "\n";
            ss << "   Engine: " << res.engine << " (Relevance & Authority: " << std::fixed << std::setprecision(1) << res.score << ")\n";
            if (!res.snippet.empty()) {
                ss << "   Snippet: " << res.snippet << "\n";
            }
            ss << "\n";
        }

        if (auto_scrape) {
            int scraped_count = 0;
            for (std::size_t i = 0; i < results.size() && scraped_count < 2; ++i) {
                const auto& res = results[i];
                std::string host;
                auto scheme_pos = res.url.find("://");
                if (scheme_pos != std::string::npos) {
                    auto rest = res.url.substr(scheme_pos + 3);
                    auto slash = rest.find('/');
                    host = (slash == std::string::npos) ? rest : rest.substr(0, slash);
                } else {
                    host = res.url;
                }

                if (host_visits_[host] >= 3) {
                    ss << "(OS Note: Host budget reached for " << host << " [3 visits]. Skipping deep scrape.)\n\n";
                    continue;
                }
                ++host_visits_[host];

                try {
                    auto page = page_cache_->fetch_and_clean(res.url, false);
                    auto analysis = PageScorer::analyze_page(res.url, page.clean_text);
                    std::string formatted = PageScorer::format_tool_result_for_quality(res.url, page.clean_text, analysis);
                    ss << "--- OS SMART-SCRAPED PAGE: " << res.url << " ---\n"
                       << "Title: " << page.title << "\n"
                       << formatted << "\n"
                       << "--- END SMART-SCRAPE ---\n\n";
                    ++scraped_count;
                } catch (const std::exception& e) {
                    ss << "(OS Note: Auto-scrape failed for " << res.url << ": " << e.what() << ")\n\n";
                }
            }
        }

        return capped(ok(ss.str()));
    }

    if (action_name == "search_local_docs") {
        const auto query = args.at("query").get<std::string>();
        const int max_results = args.value("max_results", 5);
        auto matches = doc_index_->search_hybrid(query, static_cast<std::size_t>(max_results));
        return capped(ok(doc_index_->format_search_results(matches)));
    }

    if (action_name == "fetch_and_clean_url") {
        const auto url = args.at("url").get<std::string>();
        const bool bypass = args.value("bypass_cache", false);

        std::string host;
        auto scheme_pos = url.find("://");
        if (scheme_pos != std::string::npos) {
            auto rest = url.substr(scheme_pos + 3);
            auto slash = rest.find('/');
            host = (slash == std::string::npos) ? rest : rest.substr(0, slash);
        } else {
            host = url;
        }

        if (host_visits_[host] >= 3) {
            return ok("⚠️ OS Note: Host visit cap (3 visits) reached for " + host + " to prevent crawler traps. Full body withheld.");
        }
        ++host_visits_[host];

        try {
            auto page = page_cache_->fetch_and_clean(url, bypass);
            auto analysis = PageScorer::analyze_page(url, page.clean_text);
            std::string formatted = PageScorer::format_tool_result_for_quality(url, page.clean_text, analysis);
            std::string out = "Title: " + page.title + "\nSource: " + page.url +
                              (page.from_cache ? " (cached)\n\n" : "\n\n") + formatted;
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
        return ok(confirm + " Once key findings are stored and report files are written, call OrchestratorModule.complete_recipe to finish.");
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

    if (action_name == "verify_research_deliverable") {
        return verify_research_deliverable_action(args);
    }

    return fail("unknown_action", "KnowledgeModule does not support action: " + action_name);
}

ActionResult KnowledgeModule::verify_research_deliverable_action(const Json& args) {
    namespace fs = std::filesystem;
    const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    std::string report_file_name = args.value("file", "research_report.md");
    auto report_path = base / report_file_name;
    std::error_code ec;

    if (!fs::exists(report_path, ec)) {
        for (const auto& entry : fs::directory_iterator(base, ec)) {
            if (entry.is_regular_file() && entry.path().extension() == ".md") {
                const auto fn = path_to_utf8(entry.path().filename());
                if (fn.find("report") != std::string::npos || fn.find("research") != std::string::npos) {
                    report_path = entry.path();
                    report_file_name = fn;
                    break;
                }
            }
        }
    }

    if (!fs::exists(report_path, ec)) {
        return fail("missing_report", "❌ Research deliverable '" + report_file_name + "' was not found. Write the research findings into research_report.md using WorkspaceModule.create_file before completing.");
    }

    std::ifstream in(report_path, std::ios::binary);
    if (!in.is_open()) {
        return fail("unreadable_report", "❌ Could not open research report '" + report_file_name + "'.");
    }
    std::stringstream ss;
    ss << in.rdbuf();
    const std::string text = ss.str();
    in.close();

    if (text.size() < 350) {
        return fail("shallow_report", "❌ Research report '" + report_file_name + "' is too brief (" + std::to_string(text.size()) + " chars, minimum is 350). Expand findings with detailed technical analysis and evidence.");
    }

    const bool has_headings = text.find("# ") != std::string::npos || text.find("## ") != std::string::npos;
    if (!has_headings) {
        return fail("unstructured_report", "❌ Research report '" + report_file_name + "' lacks markdown section headings. Organize into sections (e.g. Summary, Findings, Citations).");
    }

    const bool has_citations = text.find('[') != std::string::npos && text.find(']') != std::string::npos;
    if (!has_citations) {
        return fail("missing_citations", "❌ Research report lacks citations or references. Cite retrieved sources (e.g. [1] or [Source]) to ground claims.");
    }

    auto all_facts = fact_store_->get_all_facts();
    if (all_facts.empty() || all_facts.find("No permanent facts stored yet.") != std::string::npos) {
        return fail("empty_factstore", "❌ No verified facts were recorded. Store key findings into long-term knowledge using KnowledgeModule.store_fact before completing.");
    }

    return ok("✅ Verified research deliverable '" + report_file_name + "' verified successfully (" + std::to_string(text.size()) + " chars, facts recorded).");
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

