#include "aquila/knowledge/credential_store.hpp"

#include <catch2/catch_test_macros.hpp>

#include <filesystem>

using namespace aquila::knowledge;

TEST_CASE("CredentialStore domain normalization rules", "[credential_store]") {
    CHECK(CredentialStore::normalize_domain("https://www.reddit.com/login") == "reddit.com");
    CHECK(CredentialStore::normalize_domain("http://sub.university.edu:8080/path?query=1") == "sub.university.edu");
    CHECK(CredentialStore::normalize_domain("  REDDIT.COM  ") == "reddit.com");
    CHECK(CredentialStore::normalize_domain("user:pass@example.org/auth") == "example.org");
    CHECK(CredentialStore::normalize_domain("https://jstor.org") == "jstor.org");
    CHECK(CredentialStore::normalize_domain("") == "");
}

TEST_CASE("CredentialStore in-memory CRUD operations", "[credential_store]") {
    CredentialStore store;

    Credential cred;
    cred.domain = "reddit.com";
    cred.username = "researcher_1";
    cred.password = "SuperSecretPassword!123";
    cred.login_url = "https://www.reddit.com/login";
    cred.auth_type = "form";
    cred.notes = "Test account";

    store.set(cred);

    SECTION("Exact match lookup") {
        auto found = store.get("reddit.com");
        REQUIRE(found.has_value());
        CHECK(found->username == "researcher_1");
        CHECK(found->password == "SuperSecretPassword!123");
        CHECK(found->login_url == "https://www.reddit.com/login");
    }

    SECTION("Subdomain / URL resolution via suffix matching") {
        auto sub_match = store.get("login.reddit.com");
        REQUIRE(sub_match.has_value());
        CHECK(sub_match->domain == "reddit.com");
        CHECK(sub_match->username == "researcher_1");

        auto url_match = store.get("https://www.reddit.com/r/science");
        REQUIRE(url_match.has_value());
        CHECK(url_match->domain == "reddit.com");
    }

    SECTION("Password masking in list_safe") {
        auto list = store.list_safe();
        REQUIRE(list.size() == 1);
        CHECK(list[0].domain == "reddit.com");
        CHECK(list[0].username == "researcher_1");
        CHECK(list[0].password == "********");
    }

    SECTION("Removal") {
        CHECK(store.remove("reddit.com"));
        CHECK_FALSE(store.get("reddit.com").has_value());
        CHECK_FALSE(store.remove("reddit.com"));
    }
}

TEST_CASE("CredentialStore file persistence roundtrip", "[credential_store]") {
    const std::filesystem::path temp_dir = std::filesystem::temp_directory_path() / "aquila_cred_test";
    std::filesystem::create_directories(temp_dir);
    const std::filesystem::path cred_file = temp_dir / "test_credentials.json";

    // Clean up any stale file from prior runs
    std::error_code ec;
    std::filesystem::remove(cred_file, ec);

    {
        CredentialStore store(cred_file);
        // Loading non-existent file succeeds (initializes empty store)
        CHECK(store.load());
        CHECK(store.list_domains().empty());

        Credential c1{"university.edu", "student@univ.edu", "Pass1", "https://auth.university.edu", "sso_2fa", "University SSO"};
        Credential c2{"jstor.org", "scholar", "Pass2", "", "form", "Library Access"};
        store.set(c1);
        store.set(c2);

        CHECK(store.save());
    }

    {
        CredentialStore loaded_store(cred_file);
        CHECK(loaded_store.load());

        auto univ = loaded_store.get("auth.university.edu");
        REQUIRE(univ.has_value());
        CHECK(univ->username == "student@univ.edu");
        CHECK(univ->password == "Pass1");
        CHECK(univ->auth_type == "sso_2fa");

        auto jstor = loaded_store.get("jstor.org");
        REQUIRE(jstor.has_value());
        CHECK(jstor->username == "scholar");
        CHECK(jstor->password == "Pass2");
    }

    std::filesystem::remove_all(temp_dir, ec);
}

