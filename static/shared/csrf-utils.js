// CSRF utilities - shared between app.js and settings.js
(function () {
  "use strict";

  // Parse bootstrap data from the page
  var bootstrapEl = document.getElementById("app-bootstrap");
  var bootstrapData;
  if (!bootstrapEl) {
    bootstrapData = {};
  } else {
    try {
      bootstrapData = JSON.parse(bootstrapEl.textContent || "{}") || {};
    } catch (_) {
      bootstrapData = {};
    }
  }

  // Export csrfToken globally
  window.__csrfToken = String(bootstrapData.csrf_token || "").trim();

  // CSRF-safe HTTP methods that don't need CSRF token
  var CSRF_SAFE_HTTP_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

  // Store native fetch before overriding
  var nativeFetch = window.fetch;

  // Override fetch to automatically add CSRF token to mutations
  window.fetch = function (input, init) {
    var method = "GET";
    if (init && init.method) {
      method = String(init.method).toUpperCase();
    } else if (input && typeof input === "object" && input.method) {
      method = String(input.method).toUpperCase();
    }

    // Safe methods: pass through directly
    if (CSRF_SAFE_HTTP_METHODS.has(method)) {
      return nativeFetch.call(window, input, init);
    }

    // If no token, pass through without token (let server handle error)
    if (!window.__csrfToken) {
      return nativeFetch.call(window, input, init);
    }

    // Build new headers with CSRF token
    var headers = {};
    if (init && init.headers) {
      if (init.headers instanceof Headers) {
        init.headers.forEach(function (value, key) {
          headers[key] = value;
        });
      } else if (typeof init.headers === "object") {
        Object.assign(headers, init.headers);
      }
    }
    headers["X-CSRF-Token"] = window.__csrfToken;

    var newInit = Object.assign({}, init || {}, { headers: headers });
    return nativeFetch.call(window, input, newInit);
  };

  // Export bootstrap data
  window.__bootstrapData = bootstrapData;
})();