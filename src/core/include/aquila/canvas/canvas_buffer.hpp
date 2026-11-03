#pragma once

#include "aquila/json.hpp"
#include "aquila/workspace/path_firewall.hpp"

#include <cstddef>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace aquila {

// code(): not_found, unsupported_encoding, exists, no_such_patch, stale_patch,
// disk_changed, nothing_to_undo, nothing_to_redo, write_failed, not_open
class CanvasError : public std::runtime_error {
public:
    CanvasError(std::string code, const std::string& detail) : std::runtime_error(detail), code_(std::move(code)) {}
    [[nodiscard]] const std::string& code() const noexcept { return code_; }

private:
    std::string code_;
};

enum class Eol { lf, crlf };

// One file in RAM. Text is kept with '\n' line ends; the on-disk style (CRLF,
// BOM) is restored on every write. versions[0] is the text when loaded.
struct CanvasDocument {
    std::string path;  // workspace-relative, '/'-separated
    std::vector<std::string> versions;
    std::size_t current = 0;
    Eol eol = Eol::lf;
    bool bom = false;
    bool exists_on_disk = true;  // false for a created file not yet written
    std::uint64_t disk_hash = 0;  // FNV-1a of the bytes last read or written

    [[nodiscard]] const std::string& text() const { return versions[current]; }
};

struct PendingPatch {
    std::string id;  // "p1", "p2", ...
    std::string path;
    std::size_t base_version = 0;
    std::string new_text;
    std::string unified_diff;  // '\n' form, for display
    std::string origin;        // "agent" or "user"
};

// In-memory editing buffer shared by the code and writing canvases (D10/D11).
// Every accepted change is written through to disk atomically, refusing to
// overwrite a file that changed on disk since it was read.
class CanvasBuffer {
public:
    explicit CanvasBuffer(PathFirewall firewall);

    [[nodiscard]] const PathFirewall& firewall() const noexcept { return firewall_; }

    // Loads a file (once) and returns it.
    const CanvasDocument& open(const std::string& path);
    // A new, not-yet-written document with empty text; throws `exists` if the file exists.
    const CanvasDocument& create(const std::string& path);
    [[nodiscard]] const CanvasDocument* find(const std::string& path) const;
    // Forgets a created document that was never written and has no pending patch.
    void discard(const std::string& path);

    // Queues a change against the document's current version; returns its id.
    std::string propose(const std::string& path, std::string new_text, std::string origin);
    void accept(const std::string& patch_id);
    void reject(const std::string& patch_id);
    [[nodiscard]] const std::vector<PendingPatch>& pending() const noexcept { return pending_; }

    void undo(const std::string& path);
    void redo(const std::string& path);
    // Restores the loaded text (recorded as a new version, so it can be undone).
    void revert(const std::string& path);

    // The pending patch as a diff of on-disk bytes (CRLF/BOM applied), for git apply.
    [[nodiscard]] std::string disk_diff(const PendingPatch& patch) const;

    [[nodiscard]] Json snapshot() const;
    void restore(const Json& snapshot);  // throws SchemaError

private:
    CanvasDocument& doc(const std::string& path);
    void write_through(CanvasDocument& d, std::size_t version);
    [[nodiscard]] std::string to_disk(const CanvasDocument& d, const std::string& text) const;

    PathFirewall firewall_;
    std::map<std::string, CanvasDocument> docs_;
    std::vector<PendingPatch> pending_;
    std::uint64_t next_patch_ = 1;
};

// FNV-1a 64-bit (change detection, not security).
std::uint64_t fnv1a(std::string_view bytes) noexcept;

}  // namespace aquila
