#include "aquila/knowledge/credential_store.hpp"
#include "aquila/json.hpp"

#include <sqlite3.h>

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <set>
#include <sstream>

namespace aquila::knowledge {

namespace {

std::filesystem::path get_home_dir() {
#ifdef _WIN32
    if (const char* userprofile = std::getenv("USERPROFILE")) {
        return std::filesystem::path(userprofile);
    }
    if (const char* drive = std::getenv("HOMEDRIVE")) {
        if (const char* path = std::getenv("HOMEPATH")) {
            return std::filesystem::path(std::string(drive) + std::string(path));
        }
    }
#else
    if (const char* home = std::getenv("HOME")) {
        return std::filesystem::path(home);
    }
#endif
    return std::filesystem::current_path();
}

std::string trim(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return std::string(s);
}

} // namespace

std::string CredentialStore::normalize_domain(const std::string& domain_or_url) {
    std::string s = trim(domain_or_url);
    if (s.empty()) {
        return {};
    }

    // Strip URL scheme if present (e.g. "https://", "http://")
    constexpr std::string_view https_prefix = "https://";
    constexpr std::string_view http_prefix = "http://";
    if (s.rfind(https_prefix, 0) == 0) {
        s = s.substr(https_prefix.size());
    } else if (s.rfind(http_prefix, 0) == 0) {
        s = s.substr(http_prefix.size());
    }

    // Strip credentials if present (e.g. "user:pass@host")
    const auto at_pos = s.find('@');
    if (at_pos != std::string::npos) {
        s = s.substr(at_pos + 1);
    }

    // Strip path, query, fragment, and port
    const auto end_pos = s.find_first_of("/?#:");
    if (end_pos != std::string::npos) {
        s = s.substr(0, end_pos);
    }

    // Lowercase
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });

    // Strip leading "www."
    constexpr std::string_view www_prefix = "www.";
    if (s.rfind(www_prefix, 0) == 0 && s.size() > www_prefix.size()) {
        s = s.substr(www_prefix.size());
    }

    return s;
}

std::filesystem::path CredentialStore::default_credentials_path() {
    return get_home_dir() / ".aquila" / "credentials.json";
}

CredentialStore& CredentialStore::default_store() {
    static CredentialStore store(default_credentials_path());
    static std::once_flag init_flag;
    std::call_once(init_flag, [&]() {
        store.load();
    });
    return store;
}

CredentialStore::CredentialStore(std::filesystem::path storage_path)
    : storage_path_(std::move(storage_path)) {}

bool CredentialStore::load(const std::filesystem::path& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::filesystem::path target = path.empty() ? (storage_path_.empty() ? default_credentials_path() : storage_path_) : path;
    if (storage_path_.empty()) {
        storage_path_ = target;
    }

    std::error_code ec;
    if (!std::filesystem::exists(target, ec)) {
        // Not an error: fresh installation or no credentials saved yet.
        return true;
    }

    std::ifstream file(target, std::ios::in | std::ios::binary);
    if (!file.is_open()) {
        return false;
    }

    std::stringstream buffer;
    buffer << file.rdbuf();
    file.close();

    try {
        const auto root = Json::parse(buffer.str());
        if (!root.is_object()) {
            return false;
        }

        entries_.clear();
        if (root.contains("credentials") && root["credentials"].is_array()) {
            for (const auto& item : root["credentials"]) {
                if (!item.is_object()) continue;
                Credential c;
                c.domain = normalize_domain(item.value("domain", ""));
                c.username = item.value("username", "");
                c.password = item.value("password", "");
                c.login_url = item.value("login_url", "");
                c.auth_type = item.value("auth_type", "form");
                c.notes = item.value("notes", "");
                if (!c.domain.empty()) {
                    entries_[c.domain] = std::move(c);
                }
            }
        }
        return true;
    } catch (...) {
        return false;
    }
}

bool CredentialStore::save(const std::filesystem::path& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::filesystem::path target = path.empty() ? (storage_path_.empty() ? default_credentials_path() : storage_path_) : path;
    if (storage_path_.empty()) {
        storage_path_ = target;
    }

    std::error_code ec;
    if (target.has_parent_path()) {
        std::filesystem::create_directories(target.parent_path(), ec);
    }

    Json creds = Json::array();
    for (const auto& [domain, c] : entries_) {
        Json item = Json::object();
        item["domain"] = c.domain;
        item["username"] = c.username;
        item["password"] = c.password;
        if (!c.login_url.empty()) item["login_url"] = c.login_url;
        item["auth_type"] = c.auth_type.empty() ? "form" : c.auth_type;
        if (!c.notes.empty()) item["notes"] = c.notes;
        creds.push_back(std::move(item));
    }

    Json root = Json::object();
    root["version"] = 1;
    root["credentials"] = std::move(creds);

    std::ofstream file(target, std::ios::out | std::ios::trunc | std::ios::binary);
    if (!file.is_open()) {
        return false;
    }

    file << root.dump(2) << "\n";
    file.close();

#ifndef _WIN32
    // Restrict permissions to owner read/write only (0600) on POSIX
    std::filesystem::permissions(target,
        std::filesystem::perms::owner_read | std::filesystem::perms::owner_write,
        std::filesystem::perm_options::replace, ec);
#endif

    return true;
}

std::optional<Credential> CredentialStore::get(const std::string& domain_or_url) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::string normalized = normalize_domain(domain_or_url);
    if (normalized.empty()) {
        return std::nullopt;
    }

    // 1. Exact match
    auto it = entries_.find(normalized);
    if (it != entries_.end()) {
        return it->second;
    }

    // 2. Suffix match (e.g. "auth.university.edu" matches "university.edu")
    // Find the longest matching stored domain
    const Credential* best_match = nullptr;
    std::size_t best_len = 0;
    for (const auto& [stored_domain, cred] : entries_) {
        if (normalized.size() > stored_domain.size()) {
            const std::size_t offset = normalized.size() - stored_domain.size();
            if (normalized[offset - 1] == '.' &&
                normalized.compare(offset, stored_domain.size(), stored_domain) == 0) {
                if (stored_domain.size() > best_len) {
                    best_match = &cred;
                    best_len = stored_domain.size();
                }
            }
        }
    }

    if (best_match) {
        return *best_match;
    }

    return std::nullopt;
}

void CredentialStore::set(Credential cred) {
    std::lock_guard<std::mutex> lock(mutex_);
    cred.domain = normalize_domain(cred.domain);
    if (cred.domain.empty()) {
        return;
    }
    if (cred.auth_type.empty()) {
        cred.auth_type = "form";
    }
    entries_[cred.domain] = std::move(cred);
}

bool CredentialStore::remove(const std::string& domain_or_url) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::string normalized = normalize_domain(domain_or_url);
    if (normalized.empty()) {
        return false;
    }
    return entries_.erase(normalized) > 0;
}

std::vector<std::string> CredentialStore::list_domains() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::string> domains;
    domains.reserve(entries_.size());
    for (const auto& [domain, _] : entries_) {
        domains.push_back(domain);
    }
    return domains;
}

std::vector<Credential> CredentialStore::list_safe() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<Credential> result;
    result.reserve(entries_.size());
    for (const auto& [_, cred] : entries_) {
        Credential safe = cred;
        safe.password = "********";
        result.push_back(std::move(safe));
    }
    return result;
}

void CredentialStore::clear() {
    std::lock_guard<std::mutex> lock(mutex_);
    entries_.clear();
}

std::vector<std::string> CredentialStore::list_browser_session_domains() {
    const std::filesystem::path cookies_db = get_home_dir() / ".aquila" / "browser_profile" / "Cookies";
    std::error_code ec;
    if (!std::filesystem::exists(cookies_db, ec) || !std::filesystem::is_regular_file(cookies_db, ec)) {
        return {};
    }

    sqlite3* db = nullptr;
    const std::string u8path = cookies_db.string();
    if (sqlite3_open_v2(u8path.c_str(), &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, nullptr) != SQLITE_OK) {
        if (db) sqlite3_close(db);
        return {};
    }

    const char* sql =
        "SELECT DISTINCT host_key FROM cookies "
        "WHERE host_key NOT LIKE '%doubleclick%' "
        "  AND host_key NOT LIKE '%analytics%' "
        "  AND host_key NOT LIKE '%telemetry%' "
        "  AND host_key NOT LIKE '%scorecardresearch%';";
    sqlite3_stmt* stmt = nullptr;
    std::set<std::string> domains;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* text = sqlite3_column_text(stmt, 0);
            if (text != nullptr) {
                std::string host = reinterpret_cast<const char*>(text);
                while (!host.empty() && host.front() == '.') {
                    host.erase(host.begin());
                }
                if (!host.empty()) {
                    domains.insert(normalize_domain(host));
                }
            }
        }
        sqlite3_finalize(stmt);
    }
    sqlite3_close(db);

    return std::vector<std::string>(domains.begin(), domains.end());
}

} // namespace aquila::knowledge

