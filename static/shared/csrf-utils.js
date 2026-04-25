// CSRF utilities - shared between app.js and settings.js
(function () {
  "use strict";

  // ── Bootstrap data parsing ───────────────────────────────────────
  var bootstrapEl = document.getElementById("app-bootstrap");
  var bootstrapData;
  if (!bootstrapEl) {
    bootstrapData = { settings: {} };
  } else {
    try {
      bootstrapData = JSON.parse(bootstrapEl.textContent || "{}") || { settings: {} };
    } catch (_) {
      bootstrapData = { settings: {} };
    }
  }

  // Export globally so app.js / settings.js can use them without duplication
  window.__bootstrapData = bootstrapData;
  window.__appSettings = bootstrapData.settings || {};
  window.__csrfToken = String(bootstrapData.csrf_token || "").trim();
  window.__featureFlags = bootstrapData.features || window.__appSettings.features || {};

  // ── Fetch override ───────────────────────────────────────────────
  var nativeFetch = typeof globalThis.fetch === "function" ? globalThis.fetch.bind(globalThis) : null;
  var CSRF_SAFE_HTTP_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

  function resolveFetchMethod(input, init) {
    var explicitMethod = String(init?.method || "").trim();
    if (explicitMethod) {
      return explicitMethod.toUpperCase();
    }
    if (input instanceof Request) {
      return String(input.method || "GET").trim().toUpperCase() || "GET";
    }
    return "GET";
  }

  function resolveFetchUrl(input) {
    if (input instanceof Request) {
      return input.url;
    }
    return String(input || "").trim();
  }

  function shouldAttachCsrfHeader(input, init) {
    if (!nativeFetch || !window.__csrfToken) {
      return false;
    }
    var method = resolveFetchMethod(input, init);
    if (CSRF_SAFE_HTTP_METHODS.has(method)) {
      return false;
    }
    var rawUrl = resolveFetchUrl(input);
    if (!rawUrl) {
      return true;
    }
    try {
      var resolvedUrl = new URL(rawUrl, window.location.href);
      return resolvedUrl.origin === window.location.origin;
    } catch (_) {
      return true;
    }
  }

  if (nativeFetch) {
    globalThis.fetch = function (input, init) {
      if (!shouldAttachCsrfHeader(input, init)) {
        return nativeFetch(input, init);
      }
      var headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
      if (!headers.has("X-CSRF-Token")) {
        headers.set("X-CSRF-Token", window.__csrfToken);
      }
      return nativeFetch(input, { ...(init || {}), headers });
    };
  }
})();
