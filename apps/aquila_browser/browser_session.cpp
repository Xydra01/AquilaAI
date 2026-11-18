#include "browser_session.hpp"

#include <QDir>
#include <QFileInfo>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QPixmap>
#include <QSet>
#include <QTimer>
#include <QUrl>
#include <QUrlQuery>
#include <QWebEngineNewWindowRequest>
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QWebEngineSettings>
#include <QWebEngineView>

#include <algorithm>
#include <memory>

namespace aquila::browser {

namespace {

int clamp_timeout_ms(const QJsonObject& params, int fallback_ms = 20000) {
    const int raw = params.value("timeout_ms").toInt(fallback_ms);
    return std::clamp(raw, 1000, 60000);
}

int clamp_max_chars(const QJsonObject& params, int fallback_chars = 6000) {
    const int raw = params.value("max_chars").toInt(fallback_chars);
    return std::clamp(raw, 256, 32000);
}

QString js_extract_dom_snapshot_script(int max_chars, const QString& selector) {
    const QString escaped_sel = QString(selector)
        .replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', " ");
    return QStringLiteral(R"JS(
(() => {
  const maxChars = %1;
  const sel = '%2';
  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const cssPath = (el) => {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 4) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) {
        parts.unshift('#' + CSS.escape(cur.id));
        break;
      }
      const siblings = cur.parentElement ? Array.from(cur.parentElement.children).filter(c => c.tagName === cur.tagName) : [];
      if (siblings.length > 1) {
        part += ':nth-of-type(' + (siblings.indexOf(cur) + 1) + ')';
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  };

  let targetEl = null;
  if (sel.length > 0) {
    targetEl = document.querySelector(sel);
  }
  const pickMainContent = () => {
    const host = (window.location.hostname || '').toLowerCase();
    if (host.includes('wikipedia.org')) {
      return document.querySelector('#mw-content-text .mw-parser-output, #mw-content-text');
    }
    if (host.includes('github.com')) {
      return document.querySelector('article.markdown-body, #readme, main');
    }
    if (host.includes('reddit.com')) {
      if (document.querySelector('shreddit-comment')) {
        return document.querySelector('main, #main-content, [role="main"]');
      }
      return document.querySelector('shreddit-post, [data-testid="post-container"], shreddit-feed, main');
    }
    if (host.includes('arxiv.org')) {
      return document.querySelector('#abs, .ltx_page_main, main');
    }
    return document.querySelector('#mw-content-text .mw-parser-output, #mw-content-text, article.markdown-body, main article, article, main, [role="main"]');
  };
  const mainContentEl = !targetEl ? pickMainContent() : null;
  const textRoot = targetEl || document.body || document.documentElement;
  const safeText = (node) => {
    if (!node) return '';
    const inner = (node.innerText || '').trim();
    if (inner.length > 0) return inner;
    try {
      const clone = node.cloneNode(true);
      clone.querySelectorAll('script, style, noscript, template').forEach(n => n.remove());
      return (clone.textContent || '').trim();
    } catch (e) {
      return '';
    }
  };
  let text = '';
  if (!targetEl && (window.scrollY || 0) > 80 && document.body) {
    const leafChunks = [];
    const blockSel = 'h1, h2, h3, h4, h5, h6, p, li, pre, blockquote, div[id], footer';
    const pageBottom = (document.documentElement ? document.documentElement.scrollHeight : document.body.scrollHeight) || 0;
    const nearBottom = ((window.scrollY || 0) + (window.innerHeight || 800)) >= (pageBottom - 300);
    const scopeRoot = mainContentEl || document.body;
    const candidates = Array.from(scopeRoot.querySelectorAll(blockSel));
    for (const el of candidates) {
      if (!isVisible(el)) continue;
      if (el.closest('header, nav, #siteNotice, #centralNotice, #frb-mini-banner, .cn-fundraising, .frb-main, .vector-toc, .vector-page-toolbar, .mw-editsection')) continue;
      if (el.closest('footer') && !nearBottom) continue;
      const r = el.getBoundingClientRect();
      if (r.bottom < -40) continue;
      if ((el.tagName === 'DIV' || el.tagName === 'FOOTER') && el.querySelector('h1, h2, h3, h4, h5, h6, p, li, pre, blockquote')) continue;
      let chunk = safeText(el);
      if (r.top < -120 && r.height > 1200 && chunk.length > maxChars) {
        const ratio = Math.min(0.9, Math.max(0, (-r.top - 40) / Math.max(1, r.height)));
        chunk = chunk.slice(Math.floor(chunk.length * ratio));
      }
      if (chunk.length > 0) leafChunks.push(chunk);
      if (leafChunks.join('\n\n').length >= maxChars + 500) break;
    }
    text = leafChunks.join('\n\n');
    if (!text) {
      const full = safeText(mainContentEl || document.body);
      const scrollMax = Math.max(1, (document.documentElement ? document.documentElement.scrollHeight : 1) - (window.innerHeight || 800));
      const ratio = Math.min(0.9, Math.max(0, (window.scrollY || 0) / scrollMax));
      const startIdx = Math.min(Math.floor(full.length * ratio), Math.max(0, full.length - Math.min(maxChars, 400)));
      text = full.slice(startIdx);
    }
  }
  const rawFullText = safeText(mainContentEl || document.body)
    .replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  const fullTextLength = rawFullText.length;

  if (!text) {
    // Prefer primary content root when substantial so fundraising banners & nav chrome don't eat context.
    if (mainContentEl) {
      const mainText = safeText(mainContentEl);
      if (mainText.length >= 400) {
        const h1 = document.querySelector('h1');
        const h1Text = h1 ? safeText(h1) : '';
        text = (h1Text && !mainText.startsWith(h1Text)) ? (h1Text + '\n\n' + mainText) : mainText;
      }
    }
    if (!text) {
      text = safeText(textRoot);
    }
  }
  text = text.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  let truncated = false;
  if (text.length > maxChars) {
    text = text.slice(0, maxChars) + '\n... [truncated]';
    truncated = true;
  }

  const vpH = window.innerHeight || 800;
  const vpW = window.innerWidth || 1280;
  const isInViewport = (el) => {
    const r = el.getBoundingClientRect();
    return r.bottom >= 0 && r.top <= vpH && r.right >= 0 && r.left <= vpW;
  };

  const links = [];
  const seenUrls = new Set();
  const isChromeLink = (a, href) => {
    if (a.closest('#ca-nstab-main, #ca-view, #ca-talk, #ca-edit, #ca-viewsource, #ca-history, #ca-bookmark, .mw-editsection, #siteNotice, #centralNotice, #frb-mini-banner, .cn-fundraising, .frb-main, .vector-page-toolbar, #p-lang-btn')) return true;
    if (href.includes('action=edit') || href.includes('action=history') || href.includes('Wikipedia:Protection_policy') || href.includes('donate.wikimedia.org')) return true;
    return false;
  };
  const collectLinks = (nodes, requireInView, skipChrome) => {
    for (const a of nodes) {
      if (links.length >= 30) break;
      if (!isVisible(a)) continue;
      if (requireInView && !isInViewport(a)) continue;
      const href = a.href || '';
      if (!href || (!href.startsWith('http://') && !href.startsWith('https://'))) continue;
      if (isChromeLink(a, href)) continue;
      if (seenUrls.has(href)) continue;
      seenUrls.add(href);
      const label = (a.innerText || a.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
      if (skipChrome && label.length < 2) continue;
      links.push({ index: links.length + 1, text: label, url: href, selector: cssPath(a), in_viewport: isInViewport(a) });
    }
  };
  const mainLinks = Array.from(document.querySelectorAll('#mw-content-text a[href], main a[href], article a[href], [role="main"] a[href]'));
  const allLinks = Array.from(document.querySelectorAll('a[href]'));
  collectLinks(mainLinks, true, true);
  collectLinks(mainLinks, false, true);
  collectLinks(allLinks, true, true);
  collectLinks(allLinks, false, false);

  const interactive = [];
  const seenInteractive = new Set();
  const isSearchInput = (el) => {
    if (!el || el.tagName.toLowerCase() !== 'input') return false;
    const t = (el.getAttribute('type') || '').toLowerCase();
    const n = (el.getAttribute('name') || '').toLowerCase();
    const r = (el.getAttribute('role') || '').toLowerCase();
    const ph = (el.getAttribute('placeholder') || '').toLowerCase();
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    return t === 'search' || r === 'searchbox' || n === 'q' || n === 'search' || ph.includes('search') || al.includes('search');
  };
  const ctrlSel = 'button, input, textarea, select, summary, [role="button"], [role="tab"], [role="searchbox"], [aria-expanded]';
  const collectControls = (nodes, requireInView) => {
    for (const el of nodes) {
      if (interactive.length >= 25) break;
      if (seenInteractive.has(el) || !isVisible(el)) continue;
      if (requireInView && !isInViewport(el)) continue;
      seenInteractive.add(el);
      const r = el.getBoundingClientRect();
      interactive.push({
        tag: el.tagName.toLowerCase(),
        type: (el.getAttribute('type') || '').toLowerCase(),
        role: el.getAttribute('role') || '',
        expanded: el.getAttribute('aria-expanded') || '',
        is_search: isSearchInput(el),
        in_viewport: isInViewport(el),
        text: (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '')
                .trim().replace(/\s+/g, ' ').slice(0, 100),
        selector: cssPath(el),
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2)
      });
    }
  };
  const searchCtrls = Array.from(document.querySelectorAll('input[type="search"], input[name="q"], input[name="search"], [role="searchbox"], input[placeholder*="search" i]'));
  const mainCtrls = Array.from(document.querySelectorAll(
    'main ' + ctrlSel.split(', ').join(', main ') +
    ', article ' + ctrlSel.split(', ').join(', article ') +
    ', [role="main"] ' + ctrlSel.split(', ').join(', [role="main"] ')));
  const allCtrls = Array.from(document.querySelectorAll(ctrlSel));
  collectControls(searchCtrls, true);
  collectControls(mainCtrls, true);
  collectControls(allCtrls, true);
  collectControls(searchCtrls, false);
  collectControls(mainCtrls, false);
  collectControls(allCtrls, false);

  const captchaSel = 'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], .g-recaptcha, .h-captcha, .cf-turnstile, #cf-challenge-running';
  const hasCaptchaDom = !!document.querySelector(captchaSel);

  const titleLow = (document.title || '').toLowerCase();
  const sampleLow = (text || '').slice(0, 1200).toLowerCase();
  let soft404Reason = '';
  if (sampleLow.includes('wikipedia does not have an article with this exact name')) {
    soft404Reason = 'Wikipedia article does not exist (404)';
  } else if (titleLow.includes('404 not found') || titleLow.startsWith('404 ') || titleLow === 'page not found' ||
             (titleLow.includes('not found') && sampleLow.includes('404'))) {
    soft404Reason = 'Page not found (404)';
  } else if (titleLow.includes('this page isn\'t available') || sampleLow.includes('page not found · github')) {
    soft404Reason = 'Target page unavailable (404)';
  }

  return {
    url: window.location.href || '',
    title: document.title || '',
    text,
    full_text_length: fullTextLength,
    truncated,
    links,
    interactive,
    has_captcha_dom: hasCaptchaDom,
    soft_404: soft404Reason.length > 0,
    soft_404_reason: soft404Reason,
    scroll_y: Math.round(window.scrollY || 0),
    scroll_height: Math.round((document.documentElement && document.documentElement.scrollHeight) || 0),
    viewport_height: Math.round(vpH)
  };
})()
)JS").arg(max_chars).arg(escaped_sel);
}

QString js_extract_ddg_results_script() {
    return QStringLiteral(R"JS(
(() => {
  const results = [];
  const decodeDdgHref = (raw) => {
    try {
      const u = new URL(raw, window.location.href);
      const uddg = u.searchParams.get('uddg');
      if (uddg) return uddg;
      return u.href;
    } catch (e) {
      return raw || '';
    }
  };

  // Standard html.duckduckgo.com / local synthetic search DOM
  const cards = document.querySelectorAll('.result, article[data-testid="result"], li[data-layout="organic"]');
  for (const card of Array.from(cards)) {
    if (results.length >= 10) break;
    const a = card.querySelector('a.result__a, a[data-testid="result-title-a"], h2 a, a[href]');
    if (!a) continue;
    const url = decodeDdgHref(a.getAttribute('href') || a.href || '');
    if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) continue;
    const title = (a.innerText || a.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 200);
    const snEl = card.querySelector('.result__snippet, [data-result="snippet"], p');
    const snippet = snEl ? (snEl.innerText || snEl.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 320) : '';
    if (title.length === 0) continue;
    results.push({ title, url, snippet });
  }

  // Fallback for minimalist anchor-list pages
  if (results.length === 0) {
    for (const a of Array.from(document.querySelectorAll('a[href]'))) {
      if (results.length >= 10) break;
      const url = decodeDdgHref(a.getAttribute('href') || a.href || '');
      if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) continue;
      if (url.includes('duckduckgo.com')) continue;
      const title = (a.innerText || a.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 200);
      if (title.length < 4) continue;
      results.push({ title, url, snippet: '' });
    }
  }

  const bodyText = ((document.body && (document.body.innerText || document.body.textContent)) || '').slice(0, 3000);
  const hasCaptchaDom = !!document.querySelector(
    'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], .g-recaptcha, .h-captcha, .cf-turnstile, .anomaly-modal__puzzle');
  return {
    url: window.location.href || '',
    title: document.title || '',
    text: bodyText,
    has_captcha_dom: hasCaptchaDom,
    results
  };
})()
)JS");
}

} // namespace

BrowserSession::BrowserSession(QObject* parent) : QObject(parent) {
    profile_ = new QWebEngineProfile(this);
    profile_->setHttpCacheType(QWebEngineProfile::MemoryHttpCache);
    profile_->setPersistentCookiesPolicy(QWebEngineProfile::NoPersistentCookies);

    page_ = new QWebEnginePage(profile_, nullptr);
    QWebEngineSettings* s = page_->settings();
    s->setAttribute(QWebEngineSettings::JavascriptEnabled, true);
    s->setAttribute(QWebEngineSettings::LocalContentCanAccessRemoteUrls, false);
    s->setAttribute(QWebEngineSettings::ErrorPageEnabled, true);
    s->setAttribute(QWebEngineSettings::PluginsEnabled, false);
    s->setAttribute(QWebEngineSettings::AutoLoadImages, true);

    view_ = new QWebEngineView();
    view_->setPage(page_);
    view_->setAttribute(Qt::WA_DontShowOnScreen, true);
    view_->resize(1280, 800);
    view_->show();

    // Redirect target="_blank" / popup links into the active offscreen page so clicks never vanish.
    QObject::connect(page_, &QWebEnginePage::newWindowRequested, this, [this](QWebEngineNewWindowRequest& req) {
        const QUrl target = req.requestedUrl();
        QString err;
        if (target.isValid() && is_allowed_http_url(target.toString(), err)) {
            view_->setUrl(target);
        }
    });
}

BrowserSession::~BrowserSession() {
    if (view_) {
        view_->setPage(nullptr);
    }
    delete page_;
    page_ = nullptr;
    delete view_;
    view_ = nullptr;
    delete profile_;
    profile_ = nullptr;
}

bool BrowserSession::is_allowed_http_url(const QString& url_str, QString& error_out) {
    const QUrl url(url_str.trimmed());
    if (!url.isValid()) {
        error_out = "Invalid URL syntax";
        return false;
    }
    const QString scheme = url.scheme().toLower();
    if (scheme != QStringLiteral("http") && scheme != QStringLiteral("https")) {
        error_out = QStringLiteral("Rejected non-HTTP(S) URL scheme '%1'").arg(scheme);
        return false;
    }
    if (url.host().isEmpty()) {
        error_out = "URL must include a non-empty host";
        return false;
    }
    return true;
}

QJsonObject BrowserSession::detect_challenge(const QString& url,
                                             const QString& title,
                                             const QString& text,
                                             bool has_captcha_dom) {
    const QString url_low = url.toLower();
    const QString combined = (title + "\n" + text.left(2000)).toLower();
    QString reason;
    if (has_captcha_dom) {
        reason = "CAPTCHA / challenge widget detected in page DOM";
    } else if (url_low.contains("js_challenge=1") || url_low.contains("jsc_token=")) {
        reason = "Anti-bot JS challenge redirect detected in URL";
    } else if (combined.contains("awswafintegration") ||
               combined.contains("verify you are human") ||
               combined.contains("verify that you're not a robot") ||
               combined.contains("verify that you are not a robot") ||
               combined.contains("are you a robot") ||
               combined.contains("attention required! | cloudflare") ||
               combined.contains("just a moment...") ||
               combined.contains("enable javascript and cookies to continue") ||
               combined.contains("enable javascript and then reload the page") ||
               combined.contains("please complete the captcha") ||
               (url_low.contains("duckduckgo.com/anomaly") || combined.contains("anomaly-modal"))) {
        reason = "Anti-bot / human-verification challenge text detected";
    }

    QJsonObject out;
    out.insert("challenge_detected", !reason.isEmpty());
    out.insert("challenge_reason", reason);
    return out;
}

QJsonObject BrowserSession::capture_screenshot(const QString& screenshot_path) {
    QJsonObject info;
    if (screenshot_path.isEmpty()) {
        info.insert("screenshot_ok", false);
        return info;
    }
    const QFileInfo fi(screenshot_path);
    QDir().mkpath(fi.absolutePath());
    const QPixmap pixmap = view_->grab();
    if (pixmap.isNull()) {
        info.insert("screenshot_ok", false);
        info.insert("screenshot_error", "QWebEngineView::grab returned null pixmap");
        return info;
    }
    const QImage img = pixmap.toImage();
    if (!img.save(screenshot_path, "PNG")) {
        info.insert("screenshot_ok", false);
        info.insert("screenshot_error", "Failed to save PNG screenshot");
        return info;
    }
    QSet<QRgb> sample_colors;
    const int step_x = std::max(1, img.width() / 16);
    const int step_y = std::max(1, img.height() / 12);
    for (int y = step_y / 2; y < img.height(); y += step_y) {
        for (int x = step_x / 2; x < img.width(); x += step_x) {
            sample_colors.insert(img.pixel(x, y));
        }
    }
    info.insert("screenshot_ok", true);
    info.insert("screenshot_path", QDir::toNativeSeparators(fi.absoluteFilePath()));
    info.insert("screenshot_width", img.width());
    info.insert("screenshot_height", img.height());
    info.insert("screenshot_unique_colors", sample_colors.size());
    return info;
}

void BrowserSession::finish_with_snapshot(const QString& id,
                                          const QString& screenshot_path,
                                          int max_chars,
                                          const ReplyFn& reply,
                                          const QJsonObject& extra) {
    view_->page()->runJavaScript(js_extract_dom_snapshot_script(max_chars, QString{}),
        [this, id, screenshot_path, reply, extra](const QVariant& res) {
            QJsonObject out = QJsonObject::fromVariantMap(res.toMap());
            for (auto it = extra.constBegin(); it != extra.constEnd(); ++it) {
                out.insert(it.key(), it.value());
            }
            const QJsonObject challenge = detect_challenge(
                out.value("url").toString(),
                out.value("title").toString(),
                out.value("text").toString(),
                out.value("has_captcha_dom").toBool(false));
            out.insert("challenge_detected", challenge.value("challenge_detected"));
            out.insert("challenge_reason", challenge.value("challenge_reason"));

            if (!screenshot_path.isEmpty()) {
                const QJsonObject shot = capture_screenshot(screenshot_path);
                for (auto it = shot.constBegin(); it != shot.constEnd(); ++it) {
                    out.insert(it.key(), it.value());
                }
            }
            out.insert("id", id);
            out.insert("ok", !out.value("challenge_detected").toBool(false));
            if (out.value("challenge_detected").toBool(false)) {
                out.insert("error_code", "challenge_detected");
                out.insert("error", out.value("challenge_reason").toString());
            }
            reply(out);
        });
}

void BrowserSession::handle_request(const QJsonObject& req, std::function<void(const QJsonObject&)> reply) {
    const QString id = req.value("id").toString();
    const QString action = req.value("action").toString();
    const QJsonObject params = req.value("params").toObject();

    if (action == QStringLiteral("ping")) {
        cmd_ping(id, reply);
    } else if (action == QStringLiteral("navigate")) {
        cmd_navigate(id, params, reply);
    } else if (action == QStringLiteral("search")) {
        cmd_search(id, params, reply);
    } else if (action == QStringLiteral("click")) {
        cmd_click(id, params, reply);
    } else if (action == QStringLiteral("type")) {
        cmd_type(id, params, reply);
    } else if (action == QStringLiteral("scroll")) {
        cmd_scroll(id, params, reply);
    } else if (action == QStringLiteral("extract_text")) {
        cmd_extract_text(id, params, reply);
    } else if (action == QStringLiteral("screenshot")) {
        cmd_screenshot(id, params, reply);
    } else {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "unknown_action");
        err.insert("error", QStringLiteral("Unknown browser action: '%1'").arg(action));
        reply(err);
    }
}

void BrowserSession::cmd_ping(const QString& id, const ReplyFn& reply) {
    QJsonObject res;
    res.insert("id", id);
    res.insert("ok", true);
    res.insert("engine", QStringLiteral("QtWebEngine %1").arg(qVersion()));
    reply(res);
}

void BrowserSession::cmd_navigate(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString url_str = params.value("url").toString();
    QString url_err;
    if (!is_allowed_http_url(url_str, url_err)) {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "invalid_url");
        err.insert("error", url_err);
        reply(err);
        return;
    }

    const int vp_w = std::clamp(params.value("viewport_width").toInt(1280), 320, 1920);
    const int vp_h = std::clamp(params.value("viewport_height").toInt(800), 240, 1200);
    view_->resize(vp_w, vp_h);

    const QString screenshot_path = params.value("screenshot_path").toString();
    const int max_chars = clamp_max_chars(params);
    const int timeout_ms = clamp_timeout_ms(params);
    const QUrl target_url(url_str.trimmed());
    const QUrl prev_url = view_->url();

    // Same-document #fragment navigation never emits loadFinished in Chromium;
    // scroll straight to the anchor element via JS and snapshot cleanly.
    if (prev_url.isValid() && target_url.hasFragment() &&
        prev_url.adjusted(QUrl::RemoveFragment) == target_url.adjusted(QUrl::RemoveFragment)) {
        const QString frag = target_url.fragment();
        const QString escaped_frag = QString(frag).replace('\\', "\\\\").replace('\'', "\\'");
        const QString js = QStringLiteral(R"JS(
(() => {
  const raw = '%1';
  let decoded = raw;
  try { decoded = decodeURIComponent(raw); } catch (e) {}
  window.location.hash = raw;
  const el = document.getElementById(decoded) ||
             document.getElementById(raw) ||
             document.querySelector('[name="' + decoded.replace(/"/g, '\\"') + '"]');
  if (el && el.scrollIntoView) {
    el.scrollIntoView({ block: 'start', inline: 'nearest' });
    return { anchor_found: true, anchor: decoded };
  }
  return { anchor_found: false, anchor: decoded };
})()
)JS").arg(escaped_frag);
        view_->page()->runJavaScript(js, [this, id, screenshot_path, max_chars, reply](const QVariant& res) {
            const QJsonObject extra = QJsonObject::fromVariantMap(res.toMap());
            QTimer::singleShot(150, this, [this, id, screenshot_path, max_chars, reply, extra]() {
                finish_with_snapshot(id, screenshot_path, max_chars, reply, extra);
            });
        });
        return;
    }

    auto done = std::make_shared<bool>(false);
    auto conn = std::make_shared<QMetaObject::Connection>();
    auto timer = new QTimer(this);
    timer->setSingleShot(true);

    auto complete = [this, done, conn, timer, id, screenshot_path, max_chars, reply, url_str](
                        bool ok, const QString& err_code, const QString& err_msg) {
        if (*done) {
            return;
        }
        *done = true;
        timer->stop();
        timer->deleteLater();
        QObject::disconnect(*conn);
        if (!ok) {
            QJsonObject err;
            err.insert("id", id);
            err.insert("ok", false);
            err.insert("error_code", err_code);
            err.insert("error", err_msg);
            err.insert("url", url_str);
            reply(err);
            return;
        }
        // Allow initial client-side JS / paint frame to settle briefly before capture.
        QTimer::singleShot(150, this, [this, id, screenshot_path, max_chars, reply]() {
            finish_with_snapshot(id, screenshot_path, max_chars, reply);
        });
    };

    *conn = QObject::connect(view_->page(), &QWebEnginePage::loadFinished, this, [complete, url_str](bool load_ok) {
        complete(load_ok,
                 QStringLiteral("navigation_failed"),
                 load_ok ? QString{}
                         : QStringLiteral("Failed to load URL: %1 (If this URL is a PDF or file download, try its HTML landing page instead.)").arg(url_str));
    });

    QObject::connect(timer, &QTimer::timeout, this,
                     [this, done, conn, timer, id, screenshot_path, max_chars, reply, url_str, target_url, prev_url, timeout_ms]() {
        if (*done) {
            return;
        }
        *done = true;
        timer->stop();
        timer->deleteLater();
        QObject::disconnect(*conn);
        view_->stop();

        // Partial-DOM recovery: ad-heavy blogs often render full article text in < 2s while
        // slow third-party trackers prevent loadFinished. Snapshot if target page already rendered.
        QTimer::singleShot(80, this, [this, id, screenshot_path, max_chars, reply, url_str, target_url, prev_url, timeout_ms]() {
            view_->page()->runJavaScript(js_extract_dom_snapshot_script(max_chars, QString{}),
                [this, id, screenshot_path, reply, url_str, target_url, prev_url, timeout_ms](const QVariant& res) {
                    QJsonObject out = QJsonObject::fromVariantMap(res.toMap());
                    const QString cur_url_str = out.value("url").toString();
                    const QUrl cur_url(cur_url_str);
                    const QString text = out.value("text").toString().trimmed();
                    const QJsonObject challenge = detect_challenge(
                        cur_url_str,
                        out.value("title").toString(),
                        text,
                        out.value("has_captcha_dom").toBool(false));
                    if (challenge.value("challenge_detected").toBool(false)) {
                        QJsonObject err;
                        err.insert("id", id);
                        err.insert("ok", false);
                        err.insert("challenge_detected", true);
                        err.insert("challenge_reason", challenge.value("challenge_reason"));
                        err.insert("error_code", "challenge_detected");
                        err.insert("error", challenge.value("challenge_reason").toString());
                        err.insert("url", cur_url_str.isEmpty() ? url_str : cur_url_str);
                        reply(err);
                        return;
                    }

                    const bool host_matches = cur_url.isValid() &&
                        !cur_url.host().isEmpty() &&
                        (cur_url.host().compare(target_url.host(), Qt::CaseInsensitive) == 0 ||
                         cur_url.host().endsWith("." + target_url.host(), Qt::CaseInsensitive) ||
                         target_url.host().endsWith("." + cur_url.host(), Qt::CaseInsensitive));
                    const bool moved_off_prev = !prev_url.isValid() ||
                        prev_url.adjusted(QUrl::RemoveFragment) != cur_url.adjusted(QUrl::RemoveFragment);

                    if ((host_matches || (moved_off_prev && cur_url.scheme().startsWith("http"))) && text.size() >= 300) {
                        out.insert("challenge_detected", false);
                        out.insert("challenge_reason", QString{});
                        out.insert("partial_load", true);
                        out.insert("partial_load_timeout_ms", timeout_ms);
                        if (!screenshot_path.isEmpty()) {
                            const QJsonObject shot = capture_screenshot(screenshot_path);
                            for (auto it = shot.constBegin(); it != shot.constEnd(); ++it) {
                                out.insert(it.key(), it.value());
                            }
                        }
                        out.insert("id", id);
                        out.insert("ok", true);
                        reply(out);
                        return;
                    }

                    QJsonObject err;
                    err.insert("id", id);
                    err.insert("ok", false);
                    err.insert("error_code", "navigation_timeout");
                    err.insert("error", QStringLiteral("Navigation timed out after %1 ms for %2").arg(timeout_ms).arg(url_str));
                    err.insert("url", url_str);
                    reply(err);
                });
        });
    });

    timer->start(timeout_ms);
    view_->setUrl(target_url);
}

void BrowserSession::cmd_search(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString query = params.value("query").toString().trimmed();
    if (query.isEmpty()) {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "invalid_args");
        err.insert("error", "Search query must be non-empty");
        reply(err);
        return;
    }

    QString base_url = params.value("search_base_url").toString().trimmed();
    if (base_url.isEmpty()) {
        base_url = QStringLiteral("https://html.duckduckgo.com/html/");
    }
    QString url_err;
    if (!is_allowed_http_url(base_url, url_err)) {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "invalid_url");
        err.insert("error", url_err);
        reply(err);
        return;
    }

    QUrl search_url(base_url);
    QUrlQuery uq(search_url);
    uq.addQueryItem(QStringLiteral("q"), query);
    search_url.setQuery(uq);

    const QString screenshot_path = params.value("screenshot_path").toString();
    const int timeout_ms = clamp_timeout_ms(params);

    auto done = std::make_shared<bool>(false);
    auto conn = std::make_shared<QMetaObject::Connection>();
    auto timer = new QTimer(this);
    timer->setSingleShot(true);

    auto complete = [this, done, conn, timer, id, screenshot_path, query, reply, search_url](bool ok, const QString& err_msg) {
        if (*done) {
            return;
        }
        *done = true;
        timer->stop();
        timer->deleteLater();
        QObject::disconnect(*conn);
        if (!ok) {
            QJsonObject err;
            err.insert("id", id);
            err.insert("ok", false);
            err.insert("error_code", "search_failed");
            err.insert("error", err_msg);
            reply(err);
            return;
        }
        QTimer::singleShot(150, this, [this, id, screenshot_path, query, reply]() {
            view_->page()->runJavaScript(js_extract_ddg_results_script(),
                [this, id, screenshot_path, query, reply](const QVariant& res) {
                    QJsonObject out = QJsonObject::fromVariantMap(res.toMap());
                    out.insert("query", query);
                    const QJsonObject challenge = detect_challenge(
                        out.value("url").toString(),
                        out.value("title").toString(),
                        out.value("text").toString(),
                        out.value("has_captcha_dom").toBool(false));
                    out.insert("challenge_detected", challenge.value("challenge_detected"));
                    out.insert("challenge_reason", challenge.value("challenge_reason"));
                    if (!screenshot_path.isEmpty()) {
                        const QJsonObject shot = capture_screenshot(screenshot_path);
                        for (auto it = shot.constBegin(); it != shot.constEnd(); ++it) {
                            out.insert(it.key(), it.value());
                        }
                    }
                    out.insert("id", id);
                    out.insert("ok", !out.value("challenge_detected").toBool(false));
                    if (out.value("challenge_detected").toBool(false)) {
                        out.insert("error_code", "challenge_detected");
                        out.insert("error", out.value("challenge_reason").toString());
                    }
                    reply(out);
                });
        });
    };

    *conn = QObject::connect(view_->page(), &QWebEnginePage::loadFinished, this, [complete, search_url](bool load_ok) {
        complete(load_ok, load_ok ? QString{} : QStringLiteral("Search page failed to load: %1").arg(search_url.toString()));
    });

    QObject::connect(timer, &QTimer::timeout, this, [this, complete, timeout_ms]() {
        view_->stop();
        complete(false, QStringLiteral("Search timed out after %1 ms").arg(timeout_ms));
    });

    timer->start(timeout_ms);
    view_->setUrl(search_url);
}

void BrowserSession::cmd_click(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString selector = params.value("selector").toString();
    const bool has_xy = params.contains("x") && params.contains("y");
    if (selector.isEmpty() && !has_xy) {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "invalid_args");
        err.insert("error", "click requires either 'selector' or integer 'x' and 'y'");
        reply(err);
        return;
    }

    const int x = params.value("x").toInt(0);
    const int y = params.value("y").toInt(0);
    const QString escaped_sel = QString(selector).replace('\\', "\\\\").replace('\'', "\\'");
    const QString js = QStringLiteral(R"JS(
(() => {
  const sel = '%1';
  const useXy = %2;
  let el = null;
  if (sel.length > 0) {
    try {
      el = document.querySelector(sel);
    } catch (e) {}
  }
  if (!el && useXy) {
    el = document.elementFromPoint(%3, %4);
  }
  if (!el) return { clicked: false, error: 'Element not found for click target' };
  if (el.scrollIntoView) el.scrollIntoView({ block: 'center', inline: 'center' });
  const label = (el.innerText || el.value || el.tagName || '').trim().slice(0, 100);
  el.click();
  return { clicked: true, target_label: label };
})()
)JS")
        .arg(escaped_sel)
        .arg(has_xy ? "true" : "false")
        .arg(x)
        .arg(y);

    const QString screenshot_path = params.value("screenshot_path").toString();
    const int max_chars = clamp_max_chars(params);

    // Watch for navigation triggered by clicking an <a href> link or submit button so we
    // don't snapshot the old or half-loaded page after a blind 250ms delay.
    struct ClickNavState {
        bool nav_started = false;
        bool nav_finished = false;
        bool finished = false;
        bool js_done = false;
        QJsonObject click_res;
        QMetaObject::Connection start_conn;
        QMetaObject::Connection finish_conn;
        QTimer* nav_timeout = nullptr;
    };
    auto state = std::make_shared<ClickNavState>();

    auto finalize = [this, state, id, screenshot_path, max_chars, reply](int settle_ms) {
        if (state->finished) return;
        state->finished = true;
        QObject::disconnect(state->start_conn);
        QObject::disconnect(state->finish_conn);
        if (state->nav_timeout) {
            state->nav_timeout->stop();
            state->nav_timeout->deleteLater();
            state->nav_timeout = nullptr;
        }
        QTimer::singleShot(settle_ms, this, [this, id, screenshot_path, max_chars, reply, extra = state->click_res]() {
            finish_with_snapshot(id, screenshot_path, max_chars, reply, extra);
        });
    };

    state->start_conn = QObject::connect(view_->page(), &QWebEnginePage::loadStarted, this, [this, state, finalize]() {
        if (state->finished) return;
        state->nav_started = true;
        state->nav_finished = false;
        if (!state->nav_timeout) {
            state->nav_timeout = new QTimer(this);
            state->nav_timeout->setSingleShot(true);
            QObject::connect(state->nav_timeout, &QTimer::timeout, this, [finalize]() {
                finalize(100);
            });
            state->nav_timeout->start(12000);
        }
    });

    state->finish_conn = QObject::connect(view_->page(), &QWebEnginePage::loadFinished, this, [state, finalize](bool) {
        if (state->nav_started) {
            state->nav_finished = true;
            if (state->js_done) {
                finalize(150);
            }
        }
    });

    view_->page()->runJavaScript(js, [this, state, finalize, id, reply](const QVariant& res) {
        state->click_res = QJsonObject::fromVariantMap(res.toMap());
        state->js_done = true;
        if (!state->click_res.value("clicked").toBool(false)) {
            state->finished = true;
            QObject::disconnect(state->start_conn);
            QObject::disconnect(state->finish_conn);
            if (state->nav_timeout) {
                state->nav_timeout->stop();
                state->nav_timeout->deleteLater();
                state->nav_timeout = nullptr;
            }
            QJsonObject err;
            err.insert("id", id);
            err.insert("ok", false);
            err.insert("error_code", "element_not_found");
            err.insert("error", state->click_res.value("error").toString("Click failed"));
            reply(err);
            return;
        }
        if (state->nav_finished) {
            finalize(150);
            return;
        }
        QTimer::singleShot(300, this, [state, finalize]() {
            if (!state->nav_started) {
                finalize(50);
            }
        });
    });
}

void BrowserSession::cmd_type(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString selector = params.value("selector").toString();
    const QString text = params.value("text").toString();
    const bool submit = params.value("submit").toBool(false);
    if (selector.isEmpty()) {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "invalid_args");
        err.insert("error", "type requires non-empty 'selector'");
        reply(err);
        return;
    }

    const QString escaped_sel = QString(selector).replace('\\', "\\\\").replace('\'', "\\'");
    const QString escaped_txt = QString(text).replace('\\', "\\\\").replace('\'', "\\'").replace('\n', "\\n").replace('\r', "");
    const QString js = QStringLiteral(R"JS(
(() => {
  const el = document.querySelector('%1');
  if (!el) return { typed: false, error: 'Input element not found' };
  el.focus();
  const proto = el instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype
    : (el instanceof HTMLInputElement ? window.HTMLInputElement.prototype : null);
  const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
  if (desc && desc.set) {
    desc.set.call(el, '%2');
  } else {
    el.value = '%2';
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  if (%3) {
    if (el.form && typeof el.form.requestSubmit === 'function') {
      el.form.requestSubmit();
    } else if (el.form) {
      el.form.submit();
    } else {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
    }
  }
  return { typed: true, value_length: (el.value || '').length };
})()
)JS")
        .arg(escaped_sel, escaped_txt, submit ? "true" : "false");

    const QString screenshot_path = params.value("screenshot_path").toString();
    const int max_chars = clamp_max_chars(params);

    if (!submit) {
        view_->page()->runJavaScript(js, [this, id, screenshot_path, max_chars, reply](const QVariant& res) {
            const QJsonObject type_res = QJsonObject::fromVariantMap(res.toMap());
            if (!type_res.value("typed").toBool(false)) {
                QJsonObject err;
                err.insert("id", id);
                err.insert("ok", false);
                err.insert("error_code", "element_not_found");
                err.insert("error", type_res.value("error").toString("Type failed"));
                reply(err);
                return;
            }
            QTimer::singleShot(150, this, [this, id, screenshot_path, max_chars, reply, type_res]() {
                finish_with_snapshot(id, screenshot_path, max_chars, reply, type_res);
            });
        });
        return;
    }

    // Wait for form-submission navigation cleanly when submit == true (matching cmd_click).
    struct TypeNavState {
        bool nav_started = false;
        bool nav_finished = false;
        bool finished = false;
        bool js_done = false;
        QJsonObject type_res;
        QMetaObject::Connection start_conn;
        QMetaObject::Connection finish_conn;
        QTimer* nav_timeout = nullptr;
    };
    auto state = std::make_shared<TypeNavState>();

    auto finalize = [this, state, id, screenshot_path, max_chars, reply](int settle_ms) {
        if (state->finished) return;
        state->finished = true;
        QObject::disconnect(state->start_conn);
        QObject::disconnect(state->finish_conn);
        if (state->nav_timeout) {
            state->nav_timeout->stop();
            state->nav_timeout->deleteLater();
            state->nav_timeout = nullptr;
        }
        QTimer::singleShot(settle_ms, this, [this, id, screenshot_path, max_chars, reply, extra = state->type_res]() {
            finish_with_snapshot(id, screenshot_path, max_chars, reply, extra);
        });
    };

    state->start_conn = QObject::connect(view_->page(), &QWebEnginePage::loadStarted, this, [this, state, finalize]() {
        if (state->finished) return;
        state->nav_started = true;
        state->nav_finished = false;
        if (!state->nav_timeout) {
            state->nav_timeout = new QTimer(this);
            state->nav_timeout->setSingleShot(true);
            QObject::connect(state->nav_timeout, &QTimer::timeout, this, [finalize]() {
                finalize(100);
            });
            state->nav_timeout->start(12000);
        }
    });

    state->finish_conn = QObject::connect(view_->page(), &QWebEnginePage::loadFinished, this, [state, finalize](bool) {
        if (state->nav_started) {
            state->nav_finished = true;
            if (state->js_done) {
                finalize(150);
            }
        }
    });

    view_->page()->runJavaScript(js, [this, state, finalize, id, reply](const QVariant& res) {
        state->type_res = QJsonObject::fromVariantMap(res.toMap());
        state->js_done = true;
        if (!state->type_res.value("typed").toBool(false)) {
            state->finished = true;
            QObject::disconnect(state->start_conn);
            QObject::disconnect(state->finish_conn);
            if (state->nav_timeout) {
                state->nav_timeout->stop();
                state->nav_timeout->deleteLater();
                state->nav_timeout = nullptr;
            }
            QJsonObject err;
            err.insert("id", id);
            err.insert("ok", false);
            err.insert("error_code", "element_not_found");
            err.insert("error", state->type_res.value("error").toString("Type failed"));
            reply(err);
            return;
        }
        if (state->nav_finished) {
            finalize(150);
            return;
        }
        QTimer::singleShot(400, this, [state, finalize]() {
            if (!state->nav_started) {
                finalize(50);
            }
        });
    });
}

void BrowserSession::cmd_scroll(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString direction = params.value("direction").toString("down").toLower();
    const int requested_pixels = params.value("pixels").toInt(700);
    const int pixels = std::clamp(requested_pixels, -1600, 1600);
    const bool was_clamped = (direction == QStringLiteral("down") || direction == QStringLiteral("up")) &&
                             (std::abs(requested_pixels) > 1600);
    QString js;
    if (direction == QStringLiteral("top")) {
        js = QStringLiteral("window.scrollTo(0, 0); ({ scrolled: 'top' });");
    } else if (direction == QStringLiteral("bottom")) {
        js = QStringLiteral("window.scrollTo(0, document.documentElement.scrollHeight || document.body.scrollHeight); ({ scrolled: 'bottom' });");
    } else if (direction == QStringLiteral("up")) {
        js = QStringLiteral("window.scrollBy(0, -%1); ({ scrolled: 'up' });").arg(std::abs(pixels));
    } else {
        js = QStringLiteral("window.scrollBy(0, %1); ({ scrolled: 'down' });").arg(pixels);
    }

    const QString screenshot_path = params.value("screenshot_path").toString();
    const int max_chars = clamp_max_chars(params);

    view_->page()->runJavaScript(js, [this, id, screenshot_path, max_chars, reply, was_clamped, requested_pixels, pixels](const QVariant& res) {
        QJsonObject extra = QJsonObject::fromVariantMap(res.toMap());
        if (was_clamped) {
            extra.insert("clamped_from", std::abs(requested_pixels));
            extra.insert("clamped_to", std::abs(pixels));
        }
        QTimer::singleShot(120, this, [this, id, screenshot_path, max_chars, reply, extra]() {
            finish_with_snapshot(id, screenshot_path, max_chars, reply, extra);
        });
    });
}

void BrowserSession::cmd_extract_text(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString selector = params.value("selector").toString();
    const QString screenshot_path = params.value("screenshot_path").toString();
    const int max_chars = clamp_max_chars(params);

    view_->page()->runJavaScript(js_extract_dom_snapshot_script(max_chars, selector),
        [this, id, screenshot_path, reply](const QVariant& res) {
            QJsonObject out = QJsonObject::fromVariantMap(res.toMap());
            const QJsonObject challenge = detect_challenge(
                out.value("url").toString(),
                out.value("title").toString(),
                out.value("text").toString(),
                out.value("has_captcha_dom").toBool(false));
            out.insert("challenge_detected", challenge.value("challenge_detected"));
            out.insert("challenge_reason", challenge.value("challenge_reason"));
            if (!screenshot_path.isEmpty()) {
                const QJsonObject shot = capture_screenshot(screenshot_path);
                for (auto it = shot.constBegin(); it != shot.constEnd(); ++it) {
                    out.insert(it.key(), it.value());
                }
            }
            out.insert("id", id);
            out.insert("ok", true);
            reply(out);
        });
}

void BrowserSession::cmd_screenshot(const QString& id, const QJsonObject& params, const ReplyFn& reply) {
    const QString screenshot_path = params.value("screenshot_path").toString();
    if (screenshot_path.isEmpty()) {
        QJsonObject err;
        err.insert("id", id);
        err.insert("ok", false);
        err.insert("error_code", "invalid_args");
        err.insert("error", "screenshot requires 'screenshot_path'");
        reply(err);
        return;
    }
    const QJsonObject shot = capture_screenshot(screenshot_path);
    QJsonObject res = shot;
    res.insert("id", id);
    res.insert("url", view_->url().toString());
    res.insert("title", view_->title());
    res.insert("ok", shot.value("screenshot_ok").toBool(false));
    if (!res.value("ok").toBool()) {
        res.insert("error_code", "screenshot_failed");
        res.insert("error", shot.value("screenshot_error").toString("Screenshot failed"));
    }
    reply(res);
}

} // namespace aquila::browser
