#include "aquila/canvas/canvas_buffer.hpp"

#include "aquila/canvas/diff.hpp"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <system_error>

namespace aquila {

namespace fs = std::filesystem;

namespace {

constexpr std::string_view kBom = "\xEF\xBB\xBF";

bool valid_utf8(std::string_view s) {
    std::size_t i = 0;
    while (i < s.size()) {
        const auto c = static_cast<unsigned char>(s[i]);
        if (c == 0) return false;  // NUL: binary
        std::size_t len = 0;
        std::uint32_t cp = 0;
        if (c < 0x80) {
            ++i;
            continue;
        }
        if ((c & 0xE0) == 0xC0) {
            len = 2;
            cp = c & 0x1F;
        } else if ((c & 0xF0) == 0xE0) {
            len = 3;
            cp = c & 0x0F;
        } else if ((c & 0xF8) == 0xF0) {
            len = 4;
            cp = c & 0x07;
        } else {
            return false;
        }
        if (i + len > s.size()) return false;
        for (std::size_t k = 1; k < len; ++k) {
            const auto cc = static_cast<unsigned char>(s[i + k]);
            if ((cc & 0xC0) != 0x80) return false;
            cp = (cp << 6) | (cc & 0x3F);
        }
        // Overlong forms, surrogates and out-of-range code points.
        if ((len == 2 && cp < 0x80) || (len == 3 && cp < 0x800) || (len == 4 && cp < 0x10000) || cp > 0x10FFFF ||
            (cp >= 0xD800 && cp <= 0xDFFF)) {
            return false;
        }
        i += len;
    }
    return true;
}

std::string read_bytes(const fs::path& p) {
    std::ifstream in(p, std::ios::binary);
    if (!in) throw CanvasError("not_found", "cannot read " + path_to_utf8(p));
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

std::string to_hex(std::uint64_t v) {
    char buf[17];
    std::snprintf(buf, sizeof buf, "%016llx", static_cast<unsigned long long>(v));
    return buf;
}

std::uint64_t from_hex(const std::string& s, const std::string& path) {
    if (s.size() != 16 || s.find_first_not_of("0123456789abcdef") != std::string::npos) {
        throw SchemaError(path, "expected 16 hex digits");
    }
    return std::stoull(s, nullptr, 16);
}

}  // namespace

std::uint64_t fnv1a(std::string_view bytes) noexcept {
    std::uint64_t h = 0xcbf29ce484222325ULL;
    for (const char c : bytes) {
        h ^= static_cast<unsigned char>(c);
        h *= 0x100000001b3ULL;
    }
    return h;
}

CanvasBuffer::CanvasBuffer(PathFirewall firewall) : firewall_(std::move(firewall)) {}

const CanvasDocument* CanvasBuffer::find(const std::string& path) const {
    const auto it = docs_.find(path);
    return it == docs_.end() ? nullptr : &it->second;
}

CanvasDocument& CanvasBuffer::doc(const std::string& path) {
    const auto it = docs_.find(path);
    if (it == docs_.end()) throw CanvasError("not_open", "'" + path + "' is not open in the buffer");
    return it->second;
}

const CanvasDocument& CanvasBuffer::open(const std::string& input) {
    const auto resolved = firewall_.resolve(input, Access::read);
    if (const auto it = docs_.find(resolved.relative); it != docs_.end()) return it->second;
    std::error_code ec;
    if (!fs::is_regular_file(resolved.absolute, ec)) throw CanvasError("not_found", "no such file: " + resolved.relative);

    std::string bytes = read_bytes(resolved.absolute);
    CanvasDocument d;
    d.path = resolved.relative;
    d.disk_hash = fnv1a(bytes);
    std::string_view body(bytes);
    if (body.substr(0, kBom.size()) == kBom) {
        d.bom = true;
        body.remove_prefix(kBom.size());
    }
    if (!valid_utf8(body)) throw CanvasError("unsupported_encoding", "'" + d.path + "' is not UTF-8 text");

    // CRLF only when every '\n' is preceded by '\r'; mixed files keep '\r' as content.
    const auto lf = static_cast<std::size_t>(std::count(body.begin(), body.end(), '\n'));
    std::size_t crlf = 0;
    for (std::size_t i = 1; i < body.size(); ++i) crlf += body[i] == '\n' && body[i - 1] == '\r';
    std::string text;
    if (lf > 0 && crlf == lf) {
        d.eol = Eol::crlf;
        text.reserve(body.size());
        for (std::size_t i = 0; i < body.size(); ++i) {
            if (body[i] == '\r' && i + 1 < body.size() && body[i + 1] == '\n') continue;
            text += body[i];
        }
    } else {
        text.assign(body);
    }
    d.versions.push_back(std::move(text));
    return docs_.emplace(d.path, std::move(d)).first->second;
}

const CanvasDocument& CanvasBuffer::create(const std::string& input) {
    const auto resolved = firewall_.resolve(input, Access::write);
    std::error_code ec;
    if (docs_.count(resolved.relative) != 0 || fs::exists(resolved.absolute, ec)) {
        throw CanvasError("exists", "'" + resolved.relative + "' already exists");
    }
    CanvasDocument d;
    d.path = resolved.relative;
    d.exists_on_disk = false;
    d.versions.emplace_back();
    return docs_.emplace(d.path, std::move(d)).first->second;
}

std::string CanvasBuffer::propose(const std::string& path, std::string new_text, std::string origin) {
    auto& d = doc(path);
    (void)firewall_.resolve(d.path, Access::write);
    PendingPatch p;
    p.id = "p" + std::to_string(next_patch_++);
    p.path = d.path;
    p.base_version = d.current;
    p.unified_diff = diff::unified(d.text(), new_text, d.exists_on_disk ? "a/" + d.path : "/dev/null", "b/" + d.path);
    p.new_text = std::move(new_text);
    p.origin = std::move(origin);
    pending_.push_back(p);
    return p.id;
}

void CanvasBuffer::accept(const std::string& id) {
    const auto it = std::find_if(pending_.begin(), pending_.end(), [&](const PendingPatch& p) { return p.id == id; });
    if (it == pending_.end()) throw CanvasError("no_such_patch", "no pending patch '" + id + "'");
    auto& d = doc(it->path);
    if (it->base_version != d.current) {
        throw CanvasError("stale_patch", "patch " + id + " was made against version " + std::to_string(it->base_version) +
                                             " of '" + d.path + "', now at version " + std::to_string(d.current));
    }
    d.versions.resize(d.current + 1);
    d.versions.push_back(it->new_text);
    try {
        write_through(d, d.current + 1);
    } catch (...) {
        d.versions.pop_back();
        throw;
    }
    d.current += 1;
    pending_.erase(it);
}

void CanvasBuffer::reject(const std::string& id) {
    const auto it = std::find_if(pending_.begin(), pending_.end(), [&](const PendingPatch& p) { return p.id == id; });
    if (it == pending_.end()) throw CanvasError("no_such_patch", "no pending patch '" + id + "'");
    const auto path = it->path;
    pending_.erase(it);
    discard(path);  // a rejected creation leaves nothing behind
}

void CanvasBuffer::discard(const std::string& path) {
    const auto d = docs_.find(path);
    const bool has_pending = std::any_of(pending_.begin(), pending_.end(), [&](const PendingPatch& p) { return p.path == path; });
    if (d != docs_.end() && !d->second.exists_on_disk && d->second.versions.size() == 1 && !has_pending) {
        docs_.erase(d);
    }
}

void CanvasBuffer::undo(const std::string& path) {
    auto& d = doc(path);
    if (d.current == 0) throw CanvasError("nothing_to_undo", "'" + d.path + "' has no earlier version");
    write_through(d, d.current - 1);
    d.current -= 1;
}

void CanvasBuffer::redo(const std::string& path) {
    auto& d = doc(path);
    if (d.current + 1 >= d.versions.size()) throw CanvasError("nothing_to_redo", "'" + d.path + "' has no later version");
    write_through(d, d.current + 1);
    d.current += 1;
}

void CanvasBuffer::revert(const std::string& path) {
    auto& d = doc(path);
    d.versions.resize(d.current + 1);
    d.versions.push_back(d.versions.front());
    try {
        write_through(d, d.current + 1);
    } catch (...) {
        d.versions.pop_back();
        throw;
    }
    d.current += 1;
}

std::string CanvasBuffer::to_disk(const CanvasDocument& d, const std::string& text) const {
    std::string out;
    if (d.bom) out += kBom;
    if (d.eol == Eol::crlf) {
        out.reserve(text.size() + text.size() / 16);
        for (const char c : text) {
            if (c == '\n') out += '\r';
            out += c;
        }
    } else {
        out += text;
    }
    return out;
}

std::string CanvasBuffer::disk_diff(const PendingPatch& patch) const {
    const auto* d = find(patch.path);
    if (d == nullptr) throw CanvasError("not_open", "'" + patch.path + "' is not open in the buffer");
    return diff::unified(to_disk(*d, d->versions.at(patch.base_version)), to_disk(*d, patch.new_text),
                         d->exists_on_disk ? "a/" + d->path : "/dev/null", "b/" + d->path);
}

void CanvasBuffer::write_through(CanvasDocument& d, std::size_t version) {
    const auto resolved = firewall_.resolve(d.path, Access::write);
    std::error_code ec;
    const bool exists = fs::exists(resolved.absolute, ec);
    if (exists != d.exists_on_disk || (exists && fnv1a(read_bytes(resolved.absolute)) != d.disk_hash)) {
        throw CanvasError("disk_changed", "'" + d.path + "' changed on disk since it was read; reopen it before editing");
    }

    const std::string bytes = to_disk(d, d.versions.at(version));
    fs::create_directories(resolved.absolute.parent_path(), ec);
    auto tmp = resolved.absolute;
    tmp += ".aquila-tmp";
    {
        std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
        out.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        out.flush();
        if (!out) {
            fs::remove(tmp, ec);
            throw CanvasError("write_failed", "cannot write '" + d.path + "'");
        }
    }
    fs::rename(tmp, resolved.absolute, ec);
    if (ec) {
        fs::remove(tmp, ec);
        throw CanvasError("write_failed", "cannot replace '" + d.path + "': " + ec.message());
    }
    d.exists_on_disk = true;
    d.disk_hash = fnv1a(bytes);
}

Json CanvasBuffer::snapshot() const {
    Json docs = Json::array();
    for (const auto& [path, d] : docs_) {
        docs.push_back(Json{{"path", d.path},
                            {"eol", d.eol == Eol::crlf ? "crlf" : "lf"},
                            {"bom", d.bom},
                            {"exists_on_disk", d.exists_on_disk},
                            {"disk_hash", to_hex(d.disk_hash)},
                            {"current", d.current},
                            {"versions", d.versions}});
    }
    Json pend = Json::array();
    for (const auto& p : pending_) {
        pend.push_back(Json{{"id", p.id}, {"path", p.path}, {"base_version", p.base_version},
                            {"new_text", p.new_text}, {"unified_diff", p.unified_diff}, {"origin", p.origin}});
    }
    return Json{{"documents", docs}, {"pending", pend}, {"next_patch", next_patch_}};
}

void CanvasBuffer::restore(const Json& s) {
    using namespace json_io;
    expect_object(s, "");
    reject_unknown(s, "", {"documents", "pending", "next_patch"});
    std::map<std::string, CanvasDocument> docs;
    const auto& jd = require(s, "", "documents");
    const auto docs_list = read_array<CanvasDocument>(jd, "/documents", [](const Json& e, const std::string& p) {
        expect_object(e, p);
        reject_unknown(e, p, {"path", "eol", "bom", "exists_on_disk", "disk_hash", "current", "versions"});
        CanvasDocument d;
        d.path = read_string(require(e, p, "path"), child_path(p, "path"));
        const auto eol = read_string(require(e, p, "eol"), child_path(p, "eol"));
        if (eol != "lf" && eol != "crlf") throw SchemaError(child_path(p, "eol"), "expected lf or crlf");
        d.eol = eol == "crlf" ? Eol::crlf : Eol::lf;
        d.bom = read_bool(require(e, p, "bom"), child_path(p, "bom"));
        d.exists_on_disk = read_bool(require(e, p, "exists_on_disk"), child_path(p, "exists_on_disk"));
        d.disk_hash = from_hex(read_string(require(e, p, "disk_hash"), child_path(p, "disk_hash")), child_path(p, "disk_hash"));
        d.current = static_cast<std::size_t>(read_u64(require(e, p, "current"), child_path(p, "current")));
        d.versions = read_string_array(require(e, p, "versions"), child_path(p, "versions"));
        if (d.versions.empty() || d.current >= d.versions.size()) {
            throw SchemaError(child_path(p, "current"), "must index into versions");
        }
        return d;
    });
    for (auto& d : docs_list) {
        (void)firewall_.resolve(d.path, Access::read);
        docs.emplace(d.path, std::move(d));
    }
    const auto pend = read_array<PendingPatch>(require(s, "", "pending"), "/pending", [&](const Json& e, const std::string& p) {
        expect_object(e, p);
        reject_unknown(e, p, {"id", "path", "base_version", "new_text", "unified_diff", "origin"});
        PendingPatch pp;
        pp.id = read_string(require(e, p, "id"), child_path(p, "id"));
        pp.path = read_string(require(e, p, "path"), child_path(p, "path"));
        pp.base_version = static_cast<std::size_t>(read_u64(require(e, p, "base_version"), child_path(p, "base_version")));
        pp.new_text = read_string(require(e, p, "new_text"), child_path(p, "new_text"));
        pp.unified_diff = read_string(require(e, p, "unified_diff"), child_path(p, "unified_diff"));
        pp.origin = read_string(require(e, p, "origin"), child_path(p, "origin"));
        const auto d = docs.find(pp.path);
        if (d == docs.end() || pp.base_version >= d->second.versions.size()) {
            throw SchemaError(child_path(p, "base_version"), "does not match a restored document version");
        }
        return pp;
    });
    const auto next = read_u64(require(s, "", "next_patch"), "/next_patch");
    docs_ = std::move(docs);
    pending_ = pend;
    next_patch_ = next;
}

}  // namespace aquila
