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
  var _csrfFetchInProgress = false;
  var _csrfTokenPromise = null;

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

  function shouldAttachCsrfHeader(input, init) {
    var csrfTok = window.__csrfToken;
    if (!csrfTok) {
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
      return resolvedUrl.origin === window.location.href.origin;
    } catch (_) {
      return true;
    }
  }

  // Fetch a fresh CSRF token from the server
  function fetchCsrfToken() {
    if (_csrfTokenPromise) {
      return _csrfTokenPromise;
    }
    if (_csrfFetchInProgress) {
      return Promise.reject(new Error("CSRF token fetch already in progress"));
    }
    _csrfFetchInProgress = true;
    _csrfTokenPromise = fetch("/api/csrf-token", { method: "GET" })
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
        _csrfFetchInProgress = false;
        _csrfTokenPromise = null;
      });
    return _csrfTokenPromise;
  }

  // Override global fetch to attach CSRF token automatically
  var nativeFetch = typeof globalThis.fetch === "function" ? globalThis.fetch.bind(globalThis) : null;
  if (nativeFetch) {
    globalThis.fetch = function (input, init) {
      // Determine if this request needs CSRF protection
      var needsCsrf = shouldAttachCsrfHeader(input, init);

      // If CSRF token is missing but needed, fetch a fresh one first
      if (needsCsrf && !window.__csrfToken) {
        var _self = this;
        return fetchCsrfToken().then(function () {
          // Retry the original request with the new token
          var headers = new Headers(
            init && init.headers ? init.headers : (input instanceof Request ? input.headers : undefined)
          );
          if (!headers.has("X-CSRF-Token")) {
            headers.set("X-CSRF-Token", window.__csrfToken);
          }
          return nativeFetch(input, Object.assign({}, init || {}, { headers: headers }));
        }).catch(function () {
          // If token fetch fails, proceed without CSRF (will fail on server but at least we tried)
          return nativeFetch(input, init);
        });
      }

      if (!needsCsrf) {
        return nativeFetch(input, init);
      }
      var headers = new Headers(
        init && init.headers ? init.headers : (input instanceof Request ? input.headers : undefined)
      );
      if (!headers.has("X-CSRF-Token")) {
        headers.set("X-CSRF-Token", window.__csrfToken);
      }
      return nativeFetch(input, Object.assign({}, init || {}, { headers: headers }));
    };
  }

  // Export bootstrap data for shared use if needed
  window.__bootstrapData = bootstrapData;
})();