#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/workspace/path_firewall.hpp"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <regex>
#include <set>
#include <sstream>

namespace aquila::knowledge {

using aquila::path_to_utf8;

namespace {

std::string extract_url_host(std::string_view url) {
    const auto scheme_pos = url.find("://");
    if (scheme_pos == std::string_view::npos) {
        return std::string(url);
    }
    const auto rest = url.substr(scheme_pos + 3);
    const auto slash = rest.find('/');
    return std::string((slash == std::string_view::npos) ? rest : rest.substr(0, slash));
}

bool is_likely_pdf_url(std::string_view url) {
    const auto query_or_frag = url.find_first_of("?#");
    const std::string_view path_part =
        (query_or_frag == std::string_view::npos) ? url : url.substr(0, query_or_frag);
    std::string lower;
    lower.reserve(path_part.size());
    for (unsigned char c : path_part) {
        lower.push_back(static_cast<char>(std::tolower(c)));
    }
    return lower.ends_with(".pdf") || lower.find("arxiv.org/pdf/") != std::string::npos;
}

std::string build_pdf_guidance_message(std::string_view url) {
    std::string msg = "Cannot extract text from binary PDF URL '" + std::string(url) + "'. ";
    if (const auto pos = url.find("arxiv.org/pdf/"); pos != std::string_view::npos) {
        std::string tail(url.substr(pos + std::string_view("arxiv.org/pdf/").size()));
        if (tail.ends_with(".pdf")) {
            tail.resize(tail.size() - 4);
        }
        msg += "Fetch the HTML/abstract page instead: https://arxiv.org/abs/" + tail +
               " or https://arxiv.org/html/" + tail + ".";
    } else {
        msg += "Fetch an HTML webpage or abstract page instead, or synthesize findings from web_search snippets.";
    }
    return msg;
}

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
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Search query or natural language research topic"}})},
                    {"max_results", Json::object({{"type", "integer"}, {"description", "Maximum number of search results to return"}, {"default", 5}})},
                    {"auto_scrape", Json::object({{"type", "boolean"}, {"description", "Automatically scrape and extract clean substantive markdown from top authoritative results"}, {"default", true}})}
                })},
                {"required", Json::array({"query"})}
            })
        },
        ActionSchema{
            .action_name = "search_local_docs",
            .description = "Search local repository markdown documentation using hybrid dense vector and sparse lexical retrieval",
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Search query or natural language question"}})},
                    {"max_results", Json::object({{"type", "integer"}, {"description", "Maximum number of sections to return"}, {"default", 5}})}
                })},
                {"required", Json::array({"query"})}
            })
        },
        ActionSchema{
            .action_name = "fetch_and_clean_url",
            .description = "Fetch and extract clean readable text and title from a web page using persistent zero-I/O caching",
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"url", Json::object({{"type", "string"}, {"description", "HTTP or HTTPS URL to fetch"}})},
                    {"bypass_cache", Json::object({{"type", "boolean"}, {"description", "Force network refresh bypassing cache"}, {"default", false}})}
                })},
                {"required", Json::array({"url"})}
            })
        },
        ActionSchema{
            .action_name = "store_fact",
            .description = "Persist an established fact or lore item into long-term fact graph storage",
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"topic", Json::object({{"type", "string"}, {"description", "Topic category or entity name"}})},
                    {"fact", Json::object({{"type", "string"}, {"description", "The fact or knowledge string to store"}})}
                })},
                {"required", Json::array({"topic", "fact"})}
            })
        },
        ActionSchema{
            .action_name = "recall_experiences",
            .description = "Recall past task experiences and episodic memory using semantic vector similarity",
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Natural language query describing task or error"}})},
                    {"top_k", Json::object({{"type", "integer"}, {"description", "Maximum number of experiences to recall"}, {"default", 3}})},
                    {"instance_id", Json::object({{"type", "string"}, {"description", "Optional instance filter"}})}
                })},
                {"required", Json::array({"query"})}
            })
        },
        ActionSchema{
            .action_name = "get_all_facts",
            .description = "Retrieve all long-term facts formatted for LLM system prompt context",
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        },
        ActionSchema{
            .action_name = "verify_research_deliverable",
            .description = "Verify that a research report exists, meets substance and citation criteria, and facts are stored",
            .parameters_json_schema = Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"file", Json::object({{"type", "string"}, {"description", "Report filename, defaults to research_report.md"}})},
                    {"require_urls", Json::object({{"type", "boolean"}, {"description", "Require real http(s):// citation URLs (enabled for online web research)"}})},
                    {"grounded_urls", Json::object({{"type", "array"}, {"items", Json::object({{"type", "string"}})}, {"description", "Session-visited and discovered URLs for citation grounding verification"}})}
                })}
            })
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
        const int max_results = std::max(1, json_io::opt_int(args, "max_results", 5));
        const bool auto_scrape = json_io::opt_bool(args, "auto_scrape", true);

        auto results = search_engine_.search(query);
        if (results.empty()) {
            const int ddg_status = search_engine_.last_duckduckgo_status();
            std::string note;
            if (ddg_status != 200) {
                note = " (Note: DuckDuckGo search returned HTTP " + std::to_string(ddg_status) +
                       "/unavailable; try broader 1-2 word topic keywords, fetch a known URL, or rely on local docs/stored facts.)";
            }
            return ok("No search results found for query: '" + query + "'." + note);
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
                if (is_likely_pdf_url(res.url)) {
                    ss << "(OS Note: Skipped auto-scrape for binary PDF " << res.url
                       << "; use HTML/abstract pages instead.)\n\n";
                    continue;
                }
                const std::string host = extract_url_host(res.url);

                if (auto_scrape_visits_[host] >= 2) {
                    ss << "(OS Note: Auto-scrape budget reached for " << host << " [2 visits]. Use fetch_and_clean_url directly if needed.)\n\n";
                    continue;
                }
                ++auto_scrape_visits_[host];

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
        const int max_results = std::max(1, json_io::opt_int(args, "max_results", 5));
        if (doc_index_->chunk_count() == 0 && !ctx_.workspace_root.empty()) {
            namespace fs = std::filesystem;
            std::error_code ec;
            std::size_t indexed = 0;
            fs::recursive_directory_iterator it(ctx_.workspace_root, fs::directory_options::skip_permission_denied, ec);
            for (; !ec && it != fs::recursive_directory_iterator() && indexed < 40; it.increment(ec)) {
                if (it->is_directory(ec)) {
                    const auto name = path_to_utf8(it->path().filename());
                    if (name == ".git" || name == ".venv" || name == "build" || name == "node_modules" ||
                        name == "Agent-Logs" || name == "Agent-Drafts" || name == "Agent-Tasks" || name == ".aquila") {
                        it.disable_recursion_pending();
                    }
                    continue;
                }
                if (it->is_regular_file(ec) && it->path().extension() == ".md") {
                    std::ifstream in(it->path(), std::ios::binary);
                    if (!in.is_open()) continue;
                    std::ostringstream buf;
                    buf << in.rdbuf();
                    const std::string text = buf.str();
                    if (!text.empty() && text.size() <= 262144) {
                        doc_index_->index_document(path_to_utf8(fs::relative(it->path(), ctx_.workspace_root, ec)), text);
                        ++indexed;
                    }
                }
            }
        }
        auto matches = doc_index_->search_hybrid(query, static_cast<std::size_t>(max_results));
        return capped(ok(doc_index_->format_search_results(matches)));
    }

    if (action_name == "fetch_and_clean_url") {
        const auto url = args.at("url").get<std::string>();
        const bool bypass = json_io::opt_bool(args, "bypass_cache", false);

        if (is_likely_pdf_url(url)) {
            return fail("fetch_error", build_pdf_guidance_message(url));
        }

        const std::string host = extract_url_host(url);

        if (host_visits_[host] >= 5) {
            return fail("host_visit_cap",
                        "Host visit cap (5 visits) reached for " + host +
                            " to prevent crawler traps. Choose a different URL or synthesize from existing fetched sources.");
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
            std::string msg = e.what();
            if (msg.find("exceeded size limit") != std::string::npos) {
                msg += " (Target page exceeded 2MB HTML limit or may be a binary download; fetch a concise HTML/abstract page or use web_search snippets.)";
            }
            return fail("fetch_error", std::move(msg));
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
        const int top_k = std::max(1, json_io::opt_int(args, "top_k", 3));
        std::optional<std::string> inst;
        if (const auto s = json_io::opt_string(args, "instance_id"); !s.empty()) {
            inst = s;
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
    std::string report_file_name = json_io::opt_string(args, "file", "research_report.md");
    if (report_file_name.empty()) {
        report_file_name = "research_report.md";
    }
    auto report_path = base / report_file_name;
    std::error_code ec;

    if (!fs::exists(report_path, ec)) {
        for (const auto& entry : fs::directory_iterator(base, ec)) {
            if (entry.is_regular_file() && entry.path().extension() == ".md") {
                const auto fn = path_to_utf8(entry.path().filename());
                if (fn.find("report") != std::string::npos ||
                    fn.find("research") != std::string::npos ||
                    fn.find("synthesis") != std::string::npos ||
                    fn.find("summary") != std::string::npos ||
                    fn.find("findings") != std::string::npos) {
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

    // Reject obvious unexpanded placeholder tokens.
    {
        std::string lower = text;
        std::transform(lower.begin(), lower.end(), lower.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (lower.find("lorem ipsum") != std::string::npos ||
            lower.find("[tbd]") != std::string::npos ||
            lower.find("todo:") != std::string::npos) {
            return fail("placeholder_content",
                        "❌ Research report '" + report_file_name + "' contains unexpanded placeholder text (TODO / [TBD] / Lorem ipsum). Replace all placeholders with substantive evidence.");
        }
    }

    const bool require_urls = args.is_object() && args.value("require_urls", false);
    std::vector<std::string> grounded_urls;
    if (args.is_object() && args.contains("grounded_urls") && args["grounded_urls"].is_array()) {
        for (const auto& item : args["grounded_urls"]) {
            if (item.is_string()) {
                const std::string u = item.get<std::string>();
                if (u.starts_with("http://") || u.starts_with("https://")) {
                    grounded_urls.push_back(u);
                }
            }
        }
    }

    auto normalize_cite_url = [](std::string u) -> std::string {
        while (!u.empty() && (u.back() == ')' || u.back() == ']' || u.back() == '.' ||
                              u.back() == ',' || u.back() == ';' || u.back() == '>' ||
                              u.back() == '"' || u.back() == '\'' || u.back() == '`')) {
            u.pop_back();
        }
        if (const auto hash = u.find('#'); hash != std::string::npos) {
            u.resize(hash);
        }
        if (const auto scheme = u.find("://"); scheme != std::string::npos) {
            const auto path_pos = u.find('/', scheme + 3);
            const auto host_end = (path_pos == std::string::npos) ? u.size() : path_pos;
            for (std::size_t i = 0; i < host_end; ++i) {
                u[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(u[i])));
            }
            if (path_pos != std::string::npos && u.size() > path_pos + 1 && u.back() == '/') {
                u.pop_back();
            }
        }
        return u;
    };

    std::set<std::string> cited_urls;
    {
        static const std::regex url_re(R"(https?://[^\s<>\]\)\"']+)");
        for (auto it = std::sregex_iterator(text.begin(), text.end(), url_re);
             it != std::sregex_iterator(); ++it) {
            const std::string norm = normalize_cite_url((*it)[0].str());
            if (norm.size() > 10) {
                cited_urls.insert(norm);
            }
        }
    }

    const bool has_citations =
        (text.find('[') != std::string::npos && text.find(']') != std::string::npos) ||
        !cited_urls.empty();
    if (!has_citations) {
        return fail("missing_citations", "❌ Research report lacks citations or references. Cite retrieved sources (e.g. [1], [Source], or URLs) to ground claims.");
    }

    if (require_urls) {
        std::set<std::string> norm_grounded;
        for (const auto& gu : grounded_urls) {
            norm_grounded.insert(normalize_cite_url(gu));
        }
        const std::size_t min_urls = (norm_grounded.size() == 1) ? 1 : 2;
        if (cited_urls.size() < min_urls) {
            std::string msg = "❌ Research report '" + report_file_name + "' contains only " +
                              std::to_string(cited_urls.size()) + " real http(s):// URL(s) (minimum " +
                              std::to_string(min_urls) + " required for online research; generic placeholders like '[2] KnowledgeBase' are not accepted).";
            if (!grounded_urls.empty()) {
                msg += " Cite real URLs from your session such as: ";
                const std::size_t show = std::min<std::size_t>(5, grounded_urls.size());
                for (std::size_t i = 0; i < show; ++i) {
                    if (i > 0) msg += ", ";
                    msg += grounded_urls[i];
                }
            }
            return fail("ungrounded_citations", msg);
        }
        if (!norm_grounded.empty()) {
            bool any_match = false;
            for (const auto& cu : cited_urls) {
                for (const auto& gu : norm_grounded) {
                    if (cu == gu || cu.starts_with(gu) || gu.starts_with(cu)) {
                        any_match = true;
                        break;
                    }
                }
                if (any_match) break;
            }
            if (!any_match) {
                std::string msg = "❌ None of the URLs cited in '" + report_file_name +
                                  "' match any URL visited or retrieved during this research session. Ground your References section in real session URLs such as: ";
                const std::size_t show = std::min<std::size_t>(5, grounded_urls.size());
                for (std::size_t i = 0; i < show; ++i) {
                    if (i > 0) msg += ", ";
                    msg += grounded_urls[i];
                }
                return fail("ungrounded_citations", msg);
            }
        }
    }

    auto all_facts = fact_store_->get_all_facts();
    if (all_facts.empty() || all_facts.find("No permanent facts stored yet.") != std::string::npos) {
        return fail("empty_factstore", "❌ No verified facts were recorded. Store key findings into long-term knowledge using KnowledgeModule.store_fact before completing.");
    }

    return ok("✅ Verified research deliverable '" + report_file_name + "' verified successfully (" + std::to_string(text.size()) + " chars, " + std::to_string(cited_urls.size()) + " cited URL(s), facts recorded).");
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

