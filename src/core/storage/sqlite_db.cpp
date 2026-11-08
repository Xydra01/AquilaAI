#include "aquila/storage/sqlite_db.hpp"

#include <fmt/format.h>

#include <utility>

namespace aquila::storage {

namespace {

std::string format_error(int code, int extended_code, std::string_view message, std::string_view sql) {
    if (sql.empty()) {
        return fmt::format("SQLite error [code: {}, ext: {}]: {}", code, extended_code, message);
    }
    return fmt::format("SQLite error [code: {}, ext: {}]: {} (in: \"{}\")", code, extended_code, message, sql);
}

}  // namespace

SqliteError::SqliteError(int code, int extended_code, std::string message, std::string sql)
    : std::runtime_error(format_error(code, extended_code, message, sql)),
      code_(code),
      extended_code_(extended_code),
      sql_(std::move(sql)),
      message_(std::move(message)) {}

// -----------------------------------------------------------------------------
// SqliteStmt
// -----------------------------------------------------------------------------

SqliteStmt::SqliteStmt(sqlite3_stmt* stmt, std::string sql) : stmt_(stmt), sql_(std::move(sql)) {}

SqliteStmt::~SqliteStmt() {
    if (stmt_) {
        sqlite3_finalize(stmt_);
        stmt_ = nullptr;
    }
}

SqliteStmt::SqliteStmt(SqliteStmt&& other) noexcept : stmt_(other.stmt_), sql_(std::move(other.sql_)) {
    other.stmt_ = nullptr;
}

SqliteStmt& SqliteStmt::operator=(SqliteStmt&& other) noexcept {
    if (this != &other) {
        if (stmt_) {
            sqlite3_finalize(stmt_);
        }
        stmt_ = other.stmt_;
        sql_ = std::move(other.sql_);
        other.stmt_ = nullptr;
    }
    return *this;
}

int SqliteStmt::param_index(const char* name) const {
    if (!stmt_) {
        throw SqliteError(SQLITE_MISUSE, SQLITE_MISUSE, "Cannot lookup parameter on null statement");
    }
    const int idx = sqlite3_bind_parameter_index(stmt_, name);
    if (idx == 0) {
        throw SqliteError(SQLITE_NOTFOUND, SQLITE_NOTFOUND, fmt::format("Parameter \"{}\" not found in statement", name), sql_);
    }
    return idx;
}

SqliteStmt& SqliteStmt::bind(int index, int val) {
    const int rc = sqlite3_bind_int(stmt_, index, val);
    if (rc != SQLITE_OK) {
        auto* db = sqlite3_db_handle(stmt_);
        throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
    }
    return *this;
}

SqliteStmt& SqliteStmt::bind(int index, int64_t val) {
    const int rc = sqlite3_bind_int64(stmt_, index, val);
    if (rc != SQLITE_OK) {
        auto* db = sqlite3_db_handle(stmt_);
        throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
    }
    return *this;
}

SqliteStmt& SqliteStmt::bind(int index, double val) {
    const int rc = sqlite3_bind_double(stmt_, index, val);
    if (rc != SQLITE_OK) {
        auto* db = sqlite3_db_handle(stmt_);
        throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
    }
    return *this;
}

SqliteStmt& SqliteStmt::bind(int index, std::string_view val) {
    const int rc = sqlite3_bind_text(stmt_, index, val.data(), static_cast<int>(val.size()), SQLITE_TRANSIENT);
    if (rc != SQLITE_OK) {
        auto* db = sqlite3_db_handle(stmt_);
        throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
    }
    return *this;
}

SqliteStmt& SqliteStmt::bind(int index, std::span<const uint8_t> blob) {
    const int rc = sqlite3_bind_blob(stmt_, index, blob.data(), static_cast<int>(blob.size()), SQLITE_TRANSIENT);
    if (rc != SQLITE_OK) {
        auto* db = sqlite3_db_handle(stmt_);
        throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
    }
    return *this;
}

SqliteStmt& SqliteStmt::bind_null(int index) {
    const int rc = sqlite3_bind_null(stmt_, index);
    if (rc != SQLITE_OK) {
        auto* db = sqlite3_db_handle(stmt_);
        throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
    }
    return *this;
}

SqliteStmt& SqliteStmt::bind(const char* name, int val) {
    return bind(param_index(name), val);
}

SqliteStmt& SqliteStmt::bind(const char* name, int64_t val) {
    return bind(param_index(name), val);
}

SqliteStmt& SqliteStmt::bind(const char* name, double val) {
    return bind(param_index(name), val);
}

SqliteStmt& SqliteStmt::bind(const char* name, std::string_view val) {
    return bind(param_index(name), val);
}

SqliteStmt& SqliteStmt::bind(const char* name, std::span<const uint8_t> blob) {
    return bind(param_index(name), blob);
}

SqliteStmt& SqliteStmt::bind_null(const char* name) {
    return bind_null(param_index(name));
}

bool SqliteStmt::step() {
    if (!stmt_) {
        throw SqliteError(SQLITE_MISUSE, SQLITE_MISUSE, "Cannot step null statement");
    }
    const int rc = sqlite3_step(stmt_);
    if (rc == SQLITE_ROW) {
        return true;
    }
    if (rc == SQLITE_DONE) {
        return false;
    }
    auto* db = sqlite3_db_handle(stmt_);
    throw SqliteError(rc, sqlite3_extended_errcode(db), sqlite3_errmsg(db), sql_);
}

void SqliteStmt::reset() {
    if (stmt_) {
        sqlite3_reset(stmt_);
    }
}

void SqliteStmt::clear_bindings() {
    if (stmt_) {
        sqlite3_clear_bindings(stmt_);
    }
}

int SqliteStmt::column_int(int col) const {
    return sqlite3_column_int(stmt_, col);
}

int64_t SqliteStmt::column_int64(int col) const {
    return sqlite3_column_int64(stmt_, col);
}

double SqliteStmt::column_double(int col) const {
    return sqlite3_column_double(stmt_, col);
}

std::string_view SqliteStmt::column_text(int col) const {
    if (is_null(col)) {
        return {};
    }
    const auto* text = sqlite3_column_text(stmt_, col);
    const int bytes = sqlite3_column_bytes(stmt_, col);
    return std::string_view(reinterpret_cast<const char*>(text), static_cast<std::size_t>(bytes));
}

std::span<const uint8_t> SqliteStmt::column_blob(int col) const {
    if (is_null(col)) {
        return {};
    }
    const auto* blob = sqlite3_column_blob(stmt_, col);
    const int bytes = sqlite3_column_bytes(stmt_, col);
    return std::span<const uint8_t>(reinterpret_cast<const uint8_t*>(blob), static_cast<std::size_t>(bytes));
}

bool SqliteStmt::is_null(int col) const {
    return sqlite3_column_type(stmt_, col) == SQLITE_NULL;
}

int SqliteStmt::column_type(int col) const {
    return sqlite3_column_type(stmt_, col);
}

int SqliteStmt::column_count() const noexcept {
    return stmt_ ? sqlite3_column_count(stmt_) : 0;
}

std::string_view SqliteStmt::column_name(int col) const {
    if (!stmt_) {
        return {};
    }
    const char* name = sqlite3_column_name(stmt_, col);
    return name ? std::string_view(name) : std::string_view{};
}

// -----------------------------------------------------------------------------
// SqliteDb
// -----------------------------------------------------------------------------

SqliteDb::~SqliteDb() {
    close();
}

SqliteDb::SqliteDb(SqliteDb&& other) noexcept : handle_(other.handle_) {
    other.handle_ = nullptr;
}

SqliteDb& SqliteDb::operator=(SqliteDb&& other) noexcept {
    if (this != &other) {
        close();
        handle_ = other.handle_;
        other.handle_ = nullptr;
    }
    return *this;
}

SqliteDb SqliteDb::open(const std::filesystem::path& path, int flags) {
    if (flags == 0) {
        flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE;
    }

    sqlite3* handle = nullptr;
    const auto u = path.generic_u8string();
    const std::string path_str(u.begin(), u.end());
    const int rc = sqlite3_open_v2(path_str.c_str(), &handle, flags, nullptr);
    if (rc != SQLITE_OK) {
        const std::string err = handle ? sqlite3_errmsg(handle) : "Cannot allocate sqlite3 handle";
        if (handle) {
            sqlite3_close_v2(handle);
        }
        throw SqliteError(rc, rc, err, path_str);
    }

    sqlite3_busy_timeout(handle, 5000);

    SqliteDb db(handle);
    if (!(flags & SQLITE_OPEN_READONLY) && path_str != ":memory:") {
        // Enable WAL mode for enhanced concurrency and crash-resilience
        db.execute("PRAGMA journal_mode=WAL;");
    }
    return db;
}

SqliteDb SqliteDb::open_memory() {
    sqlite3* handle = nullptr;
    const int rc = sqlite3_open_v2(":memory:", &handle,
                                   SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_MEMORY,
                                   nullptr);
    if (rc != SQLITE_OK) {
        const std::string err = handle ? sqlite3_errmsg(handle) : "Cannot allocate in-memory sqlite3 handle";
        if (handle) {
            sqlite3_close_v2(handle);
        }
        throw SqliteError(rc, rc, err, ":memory:");
    }
    sqlite3_busy_timeout(handle, 5000);
    return SqliteDb(handle);
}

void SqliteDb::close() noexcept {
    if (handle_) {
        sqlite3_close_v2(handle_);
        handle_ = nullptr;
    }
}

void SqliteDb::execute(std::string_view sql) {
    if (!handle_) {
        throw SqliteError(SQLITE_MISUSE, SQLITE_MISUSE, "Database handle is closed", std::string(sql));
    }
    char* errmsg = nullptr;
    const std::string sql_str(sql);
    const int rc = sqlite3_exec(handle_, sql_str.c_str(), nullptr, nullptr, &errmsg);
    if (rc != SQLITE_OK) {
        std::string err = errmsg ? errmsg : sqlite3_errmsg(handle_);
        if (errmsg) {
            sqlite3_free(errmsg);
        }
        throw SqliteError(rc, sqlite3_extended_errcode(handle_), err, sql_str);
    }
}

SqliteStmt SqliteDb::prepare(std::string_view sql) const {
    if (!handle_) {
        throw SqliteError(SQLITE_MISUSE, SQLITE_MISUSE, "Database handle is closed", std::string(sql));
    }
    sqlite3_stmt* stmt = nullptr;
    const int rc = sqlite3_prepare_v3(handle_, sql.data(), static_cast<int>(sql.size()), 0, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        throw SqliteError(rc, sqlite3_extended_errcode(handle_), sqlite3_errmsg(handle_), std::string(sql));
    }
    return SqliteStmt(stmt, std::string(sql));
}

int64_t SqliteDb::last_insert_rowid() const noexcept {
    return handle_ ? sqlite3_last_insert_rowid(handle_) : 0;
}

int SqliteDb::changes() const noexcept {
    return handle_ ? sqlite3_changes(handle_) : 0;
}

// -----------------------------------------------------------------------------
// SqliteTx
// -----------------------------------------------------------------------------

SqliteTx::SqliteTx(SqliteDb& db, bool immediate) : db_(&db), active_(false) {
    db_->execute(immediate ? "BEGIN IMMEDIATE;" : "BEGIN DEFERRED;");
    active_ = true;
}

SqliteTx::~SqliteTx() {
    if (active_ && db_ && db_->is_open()) {
        try {
            db_->execute("ROLLBACK;");
        } catch (...) {
            // Destructors must never throw
        }
        active_ = false;
    }
}

SqliteTx::SqliteTx(SqliteTx&& other) noexcept : db_(other.db_), active_(other.active_) {
    other.db_ = nullptr;
    other.active_ = false;
}

SqliteTx& SqliteTx::operator=(SqliteTx&& other) noexcept {
    if (this != &other) {
        if (active_ && db_ && db_->is_open()) {
            try {
                db_->execute("ROLLBACK;");
            } catch (...) {
            }
        }
        db_ = other.db_;
        active_ = other.active_;
        other.db_ = nullptr;
        other.active_ = false;
    }
    return *this;
}

void SqliteTx::commit() {
    if (!active_) {
        throw SqliteError(SQLITE_MISUSE, SQLITE_MISUSE, "Cannot commit inactive transaction");
    }
    db_->execute("COMMIT;");
    active_ = false;
}

void SqliteTx::rollback() {
    if (!active_) {
        throw SqliteError(SQLITE_MISUSE, SQLITE_MISUSE, "Cannot rollback inactive transaction");
    }
    db_->execute("ROLLBACK;");
    active_ = false;
}

}  // namespace aquila::storage
