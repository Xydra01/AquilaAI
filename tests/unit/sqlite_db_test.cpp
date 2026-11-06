#include "aquila/storage/sqlite_db.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck/catch.h>

#include <cstdint>
#include <string>
#include <vector>

using namespace aquila::storage;

TEST_CASE("SqliteDb in-memory lifecycle and basic execution") {
    auto db = SqliteDb::open_memory();
    REQUIRE(db.is_open());

    db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT, val REAL);");
    db.execute("INSERT INTO test (name, val) VALUES ('alice', 3.14159);");
    REQUIRE(db.last_insert_rowid() == 1);
    REQUIRE(db.changes() == 1);

    auto stmt = db.prepare("SELECT id, name, val FROM test WHERE id = ?;");
    stmt.bind(1, 1);
    REQUIRE(stmt.step() == true);
    CHECK(stmt.column_int(0) == 1);
    CHECK(stmt.column_text(1) == "alice");
    CHECK(stmt.column_double(2) == 3.14159);
    REQUIRE(stmt.step() == false);  // SQLITE_DONE
}

TEST_CASE("SqliteDb named parameter binding and null handling") {
    auto db = SqliteDb::open_memory();
    db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, note TEXT);");

    auto stmt = db.prepare("INSERT INTO items (id, note) VALUES (:id, :note);");
    stmt.bind(":id", 42);
    stmt.bind_null(":note");
    REQUIRE(stmt.step() == false);

    auto query = db.prepare("SELECT id, note FROM items WHERE id = :id;");
    query.bind(":id", 42);
    REQUIRE(query.step() == true);
    CHECK(query.column_int(0) == 42);
    CHECK(query.is_null(1));
    CHECK(query.column_text(1).empty());
}

TEST_CASE("SqliteDb throws typed SqliteError on syntax or constraint errors") {
    auto db = SqliteDb::open_memory();
    CHECK_THROWS_AS(db.execute("SYNTAX ERROR NOT A VALID SQL;"), SqliteError);

    db.execute("CREATE TABLE unique_items (val TEXT UNIQUE);");
    db.execute("INSERT INTO unique_items VALUES ('dup');");
    CHECK_THROWS_AS(db.execute("INSERT INTO unique_items VALUES ('dup');"), SqliteError);
}

// Feature: m6-knowledge-module, Property 2: Transaction Atomicity
// Uncommitted transactions roll back automatically on unwind; committed transactions persist.
TEST_CASE("SqliteTx transaction rollback and commit atomicity") {
    auto db = SqliteDb::open_memory();
    db.execute("CREATE TABLE counts (id INTEGER PRIMARY KEY, val INTEGER);");
    db.execute("INSERT INTO counts (id, val) VALUES (1, 100);");

    // Case A: Uncommitted transaction rolls back on destruction
    {
        SqliteTx tx(db);
        db.execute("UPDATE counts SET val = 200 WHERE id = 1;");
        // tx goes out of scope without commit() -> rollback
    }

    {
        auto stmt = db.prepare("SELECT val FROM counts WHERE id = 1;");
        REQUIRE(stmt.step() == true);
        CHECK(stmt.column_int(0) == 100);  // Unchanged
    }

    // Case B: Committed transaction persists
    {
        SqliteTx tx(db);
        db.execute("UPDATE counts SET val = 300 WHERE id = 1;");
        tx.commit();
    }

    {
        auto stmt = db.prepare("SELECT val FROM counts WHERE id = 1;");
        REQUIRE(stmt.step() == true);
        CHECK(stmt.column_int(0) == 300);  // Updated
    }
}

// Feature: m6-knowledge-module, Property 3: Type Round-Trip
// Integers, 64-bit ints, doubles, strings, and binary blobs round-trip byte-for-byte.
TEST_CASE("Property 3: SqliteStmt typed values round-trip exactly", "[rapidcheck]") {
    rc::prop("Integer and text round trip", [](int64_t int_val, const std::string& str_val) {
        auto db = SqliteDb::open_memory();
        db.execute("CREATE TABLE prop_test (i INTEGER, s TEXT);");

        auto insert = db.prepare("INSERT INTO prop_test (i, s) VALUES (?, ?);");
        insert.bind(1, int_val);
        insert.bind(2, str_val);
        RC_ASSERT(!insert.step());

        auto query = db.prepare("SELECT i, s FROM prop_test;");
        RC_ASSERT(query.step());
        RC_ASSERT(query.column_int64(0) == int_val);
        RC_ASSERT(std::string(query.column_text(1)) == str_val);
        RC_ASSERT(!query.step());
    });

    rc::prop("Binary blob round trip", [](const std::vector<uint8_t>& blob) {
        auto db = SqliteDb::open_memory();
        db.execute("CREATE TABLE blob_test (b BLOB);");

        auto insert = db.prepare("INSERT INTO blob_test (b) VALUES (?);");
        insert.bind(1, std::span<const uint8_t>(blob));
        RC_ASSERT(!insert.step());

        auto query = db.prepare("SELECT b FROM blob_test;");
        RC_ASSERT(query.step());
        auto res_blob = query.column_blob(0);
        RC_ASSERT(std::vector<uint8_t>(res_blob.begin(), res_blob.end()) == blob);
        RC_ASSERT(!query.step());
    });
}

