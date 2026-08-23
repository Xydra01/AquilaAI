"use strict";

/*
 * Tiny, dependency-free Markdown + JSON renderer for the Aquila PWA.
 * Everything is HTML-escaped first, so output is safe to inject. Supports
 * headings, bold/italic, inline + fenced code, lists, links, tables,
 * blockquotes, horizontal rules, and pretty-printed JSON blocks.
 */
const AquilaMarkdown = (function () {
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function prettyJson(text) {
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch (e) {
      return text;
    }
  }

  function looksLikeJson(text) {
    const t = (text || "").trim();
    if (!(t.startsWith("{") && t.endsWith("}")) && !(t.startsWith("[") && t.endsWith("]"))) {
      return false;
    }
    try {
      JSON.parse(t);
      return true;
    } catch (e) {
      return false;
    }
  }

  function inline(escaped) {
    // Pull out inline code spans so other rules don't touch their contents.
    const codes = [];
    let s = escaped.replace(/`([^`]+)`/g, (m, c) => {
      codes.push(c);
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
    // Links [text](url) — url is already escaped; restrict schemes.
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => {
      const safe = /^(https?:|mailto:|\/|#)/i.test(u) ? u : "#";
      return '<a href="' + safe + '" target="_blank" rel="noopener noreferrer">' + t + "</a>";
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, "$1<em>$2</em>");
    s = s.replace(/(^|[^\w])_(?!\s)([^_]+?)_/g, "$1<em>$2</em>");
    s = s.replace(/\u0000(\d+)\u0000/g, (m, idx) => "<code>" + codes[+idx] + "</code>");
    return s;
  }

  function splitRow(line) {
    let l = line.trim();
    if (l.startsWith("|")) l = l.slice(1);
    if (l.endsWith("|")) l = l.slice(0, -1);
    return l.split("|").map((c) => c.trim());
  }

  function renderTable(header, rows) {
    let h = "<table><thead><tr>";
    header.forEach((c) => (h += "<th>" + inline(escapeHtml(c)) + "</th>"));
    h += "</tr></thead><tbody>";
    rows.forEach((r) => {
      h += "<tr>";
      for (let j = 0; j < header.length; j++) {
        h += "<td>" + inline(escapeHtml(r[j] || "")) + "</td>";
      }
      h += "</tr>";
    });
    h += "</tbody></table>";
    return h;
  }

  function isBlockStart(line) {
    return (
      /^```/.test(line) ||
      /^(#{1,6})\s+/.test(line) ||
      /^>\s?/.test(line) ||
      /^(\s*[-*_]){3,}\s*$/.test(line) ||
      /^(\s*)[-*+]\s+/.test(line) ||
      /^(\s*)\d+\.\s+/.test(line)
    );
  }

  function render(src) {
    src = String(src == null ? "" : src).replace(/\r\n?/g, "\n");
    const lines = src.split("\n");
    let html = "";
    let i = 0;
    const listStack = [];

    function closeLists() {
      while (listStack.length) html += listStack.pop() === "ul" ? "</ul>" : "</ol>";
    }

    while (i < lines.length) {
      const line = lines[i];

      const fence = line.match(/^```\s*([\w-]*)\s*$/);
      if (fence) {
        closeLists();
        const lang = (fence[1] || "").toLowerCase();
        const buf = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) {
          buf.push(lines[i]);
          i++;
        }
        i++;
        const code = buf.join("\n");
        if (lang === "json") {
          html += '<pre class="json-block"><code>' + escapeHtml(prettyJson(code)) + "</code></pre>";
        } else {
          html += '<pre class="code-block"><code>' + escapeHtml(code) + "</code></pre>";
        }
        continue;
      }

      if (
        /\|/.test(line) &&
        i + 1 < lines.length &&
        /\|/.test(lines[i + 1]) &&
        /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])
      ) {
        closeLists();
        const header = splitRow(line);
        i += 2;
        const rows = [];
        while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim() !== "") {
          rows.push(splitRow(lines[i]));
          i++;
        }
        html += renderTable(header, rows);
        continue;
      }

      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        closeLists();
        const lvl = h[1].length;
        html += "<h" + lvl + ">" + inline(escapeHtml(h[2])) + "</h" + lvl + ">";
        i++;
        continue;
      }

      if (/^>\s?/.test(line)) {
        closeLists();
        const buf = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) {
          buf.push(lines[i].replace(/^>\s?/, ""));
          i++;
        }
        html += "<blockquote>" + render(buf.join("\n")) + "</blockquote>";
        continue;
      }

      if (/^(\s*[-*_]){3,}\s*$/.test(line)) {
        closeLists();
        html += "<hr/>";
        i++;
        continue;
      }

      const ul = line.match(/^(\s*)[-*+]\s+(.*)$/);
      const ol = line.match(/^(\s*)\d+\.\s+(.*)$/);
      if (ul || ol) {
        const type = ul ? "ul" : "ol";
        if (listStack[listStack.length - 1] !== type) {
          closeLists();
          html += type === "ul" ? "<ul>" : "<ol>";
          listStack.push(type);
        }
        html += "<li>" + inline(escapeHtml(ul ? ul[2] : ol[2])) + "</li>";
        i++;
        continue;
      }

      if (line.trim() === "") {
        closeLists();
        i++;
        continue;
      }

      closeLists();
      const buf = [line];
      i++;
      while (i < lines.length && lines[i].trim() !== "" && !isBlockStart(lines[i])) {
        buf.push(lines[i]);
        i++;
      }
      html += "<p>" + inline(escapeHtml(buf.join("\n"))).replace(/\n/g, "<br/>") + "</p>";
    }
    closeLists();
    return html;
  }

  // Render text that might be pure JSON (pretty-print) or markdown prose.
  function renderSmart(text) {
    if (looksLikeJson(text)) {
      return '<pre class="json-block"><code>' + escapeHtml(prettyJson(text)) + "</code></pre>";
    }
    return render(text);
  }

  return { render: render, renderSmart: renderSmart, escapeHtml: escapeHtml, prettyJson: prettyJson };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AquilaMarkdown;
}
