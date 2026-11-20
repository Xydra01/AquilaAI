#pragma once

#include <filesystem>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace aquila::knowledge {

struct Credential {
    std::string domain;      // e.g. "reddit.com", "jstor.org"
    std::string username;    // username, email, or client ID
    std::string password;    // raw password or secret token (kept private locally)
    std::string login_url;   // optional direct login page URL
    std::string auth_type;   // "form" (default), "sso_2fa", "cookie", etc.
    std::string notes;       // optional metadata or notes
};

// Thread-safe credential manager that safely stores and retrieves credentials
// for web services and academic portals. Passwords are kept locally in ~/.aquila/credentials.json
// and are never exposed in user logs, LLM context, or debug traces.
class CredentialStore final {
public:
    static CredentialStore& default_store();

    CredentialStore() = default;
    explicit CredentialStore(std::filesystem::path storage_path);

    // Loads credentials from JSON file. If path is empty, uses configured or default path.
    // Returns true on success (or if file does not exist yet).
    bool load(const std::filesystem::path& path = {});

    // Saves credentials to JSON file with restricted file permissions.
    bool save(const std::filesystem::path& path = {});

    // Retrieves credentials for a domain. Matches exact domain or domain suffix
    // (e.g. "auth.university.edu" matches "university.edu", or "https://www.reddit.com/login" matches "reddit.com").
    [[nodiscard]] std::optional<Credential> get(const std::string& domain_or_url) const;

    // Sets (inserts or updates) credentials for a domain.
    void set(Credential cred);

    // Removes credentials for a domain. Returns true if removed, false if not found.
    bool remove(const std::string& domain_or_url);

    // Lists all stored domains.
    [[nodiscard]] std::vector<std::string> list_domains() const;

    // Queries ~/.aquila/browser_profile/Cookies to discover domains with active authenticated sessions.
    [[nodiscard]] static std::vector<std::string> list_browser_session_domains();

    // Lists all credentials with passwords masked as "********" for safe display.
    [[nodiscard]] std::vector<Credential> list_safe() const;

    // Clears all entries in memory.
    void clear();

    // Resolves default ~/.aquila/credentials.json path.
    [[nodiscard]] static std::filesystem::path default_credentials_path();

    // Normalizes a domain or URL to a clean lowercase domain string
    // (e.g. "https://www.Reddit.com/login" -> "reddit.com").
    [[nodiscard]] static std::string normalize_domain(const std::string& domain_or_url);

private:
    std::filesystem::path storage_path_;
    mutable std::mutex mutex_;
    std::map<std::string, Credential> entries_;
};

} // namespace aquila::knowledge

