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

  // Export csrfToken globally for CSRF header injection
  window.__csrfToken = String(bootstrapData.csrf_token || "").trim();

  // CSRF-safe HTTP methods that don't need CSRF token
  var CSRF_SAFE_HTTP_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

  // Track if we're currently fetching a token to avoid infinite loops
  var _csrfFetchPromise = null;

  function resolveFetchMethod(input, init) {
    var explicitMethod = String(init && init.method || "").trim();
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

  function isSameOriginUrl(rawUrl) {
    if (!rawUrl) {
      return true;
    }
    try {
      var resolvedUrl = new URL(rawUrl, window.location.href);
      return resolvedUrl.origin === window.location.href.origin;
    } catch (_) {
      return true;
    }
  }

  function shouldAttachCsrfHeader(input, init) {
    var method = resolveFetchMethod(input, init);
    if (CSRF_SAFE_HTTP_METHODS.has(method)) {
      return false;
    }
    return isSameOriginUrl(resolveFetchUrl(input));
  }

  // Fetch a fresh CSRF token from the server
  function fetchCsrfToken() {
    if (_csrfFetchPromise) {
      return _csrfFetchPromise;
    }
    _csrfFetchPromise = fetch("/api/csrf-token", { method: "GET" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Failed to fetch CSRF token");
        }
        return response.json();
      })
      .then(function (data) {
        if (data && data.csrf_token) {
          window.__csrfToken = String(data.csrf_token).trim();
        }
        return window.__csrfToken;
      })
      .catch(function (err) {
        console.error("Error fetching CSRF token:", err);
        throw err;
      })
      .finally(function () {
        _csrfFetchPromise = null;
      });
    return _csrfFetchPromise;
  }

  // Override global fetch to attach CSRF token automatically
  var nativeFetch = typeof globalThis.fetch === "function" ? globalThis.fetch.bind(globalThis) : null;
  if (nativeFetch) {
    globalThis.fetch = function (input, init) {
      var method = resolveFetchMethod(input, init);

      // Safe methods don't need CSRF
      if (CSRF_SAFE_HTTP_METHODS.has(method)) {
        return nativeFetch(input, init);
      }

      // Non-same-origin requests don't need CSRF (browser handles CORS)
      if (!isSameOriginUrl(resolveFetchUrl(input))) {
        return nativeFetch(input, init);
      }

      // If we have a token, use it
      if (window.__csrfToken) {
        var headers = new Headers(
          init && init.headers ? init.headers : (input instanceof Request ? input.headers : undefined)
        );
        if (!headers.has("X-CSRF-Token")) {
          headers.set("X-CSRF-Token", window.__csrfToken);
        }
        return nativeFetch(input, Object.assign({}, init || {}, { headers: headers }));
      }

      // No token available - fetch one first, then retry the request
      var _self = this;
      return fetchCsrfToken().then(function () {
        var headers = new Headers(
          init && init.headers ? init.headers : (input instanceof Request ? input.headers : undefined)
        );
        if (!headers.has("X-CSRF-Token")) {
          headers.set("X-CSRF-Token", window.__csrfToken);
        }
        return nativeFetch(input, Object.assign({}, init || {}, { headers: headers }));
      }).catch(function (err) {
        console.error("CSRF token fetch failed, proceeding without token:", err);
        // Fallback: proceed without CSRF token (will likely fail with 403, but at least we tried)
        return nativeFetch(input, init);
      });
    };
  }

  // Export bootstrap data for shared use if needed
  window.__bootstrapData = bootstrapData;
})();