#pragma once

#include <sqlite3.h>

#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::storage {

class SqliteError : public std::runtime_error {
public:
  SqliteError(int code, int extended_code, std::string message,
              std::string sql = "");

  int code() const noexcept { return code_; }
  int extended_code() const noexcept { return extended_code_; }
  std::string_view sql() const noexcept { return sql_; }
  std::string_view raw_message() const noexcept { return message_; }

private:
  int code_{0};
  int extended_code_{0};
  std::string sql_;
  std::string message_;
};

class SqliteDb;

class SqliteStmt {
public:
  SqliteStmt() = default;
  explicit SqliteStmt(sqlite3_stmt *stmt, std::string sql = "");
  ~SqliteStmt();

  SqliteStmt(const SqliteStmt &) = delete;
  SqliteStmt &operator=(const SqliteStmt &) = delete;
  SqliteStmt(SqliteStmt &&other) noexcept;
  SqliteStmt &operator=(SqliteStmt &&other) noexcept;

  bool is_valid() const noexcept { return stmt_ != nullptr; }
  sqlite3_stmt *raw_handle() noexcept { return stmt_; }

  // 1-based index binding helpers
  SqliteStmt &bind(int index, int val);
  SqliteStmt &bind(int index, int64_t val);
  SqliteStmt &bind(int index, double val);
  SqliteStmt &bind(int index, std::string_view val);
  SqliteStmt &bind(int index, std::span<const uint8_t> blob);
  SqliteStmt &bind_null(int index);

  // Named parameter binding helpers (e.g. ":name", "@name", or "$name")
  int param_index(const char *name) const;
  SqliteStmt &bind(const char *name, int val);
  SqliteStmt &bind(const char *name, int64_t val);
  SqliteStmt &bind(const char *name, double val);
  SqliteStmt &bind(const char *name, std::string_view val);
  SqliteStmt &bind(const char *name, std::span<const uint8_t> blob);
  SqliteStmt &bind_null(const char *name);

  // Execution
  // Returns true when a row is available (SQLITE_ROW), false on completion
  // (SQLITE_DONE).
  bool step();
  void reset();
  void clear_bindings();

  // 0-based column accessors
  int column_int(int col) const;
  int64_t column_int64(int col) const;
  double column_double(int col) const;
  std::string_view column_text(int col) const;
  std::span<const uint8_t> column_blob(int col) const;
  bool is_null(int col) const;
  int column_type(int col) const;
  int column_count() const noexcept;
  std::string_view column_name(int col) const;

private:
  sqlite3_stmt *stmt_{nullptr};
  std::string sql_;
};

class SqliteDb {
public:
  SqliteDb() = default;
  ~SqliteDb();

  SqliteDb(const SqliteDb &) = delete;
  SqliteDb &operator=(const SqliteDb &) = delete;
  SqliteDb(SqliteDb &&other) noexcept;
  SqliteDb &operator=(SqliteDb &&other) noexcept;

  // Open a database on disk. Default flags: READWRITE | CREATE.
  static SqliteDb open(const std::filesystem::path &path, int flags = 0);
  // Open a pure in-memory private database.
  static SqliteDb open_memory();

  bool is_open() const noexcept { return handle_ != nullptr; }
  void close() noexcept;

  void execute(std::string_view sql);
  SqliteStmt prepare(std::string_view sql) const;

  int64_t last_insert_rowid() const noexcept;
  int changes() const noexcept;
  sqlite3 *raw_handle() noexcept { return handle_; }

private:
  explicit SqliteDb(sqlite3 *handle) noexcept : handle_(handle) {}
  sqlite3 *handle_{nullptr};
};

class SqliteTx {
public:
  explicit SqliteTx(SqliteDb &db, bool immediate = true);
  ~SqliteTx();

  SqliteTx(const SqliteTx &) = delete;
  SqliteTx &operator=(const SqliteTx &) = delete;
  SqliteTx(SqliteTx &&other) noexcept;
  SqliteTx &operator=(SqliteTx &&other) noexcept;

  void commit();
  void rollback();
  bool is_active() const noexcept { return active_; }

private:
  SqliteDb *db_{nullptr};
  bool active_{false};
};

} // namespace aquila::storage
