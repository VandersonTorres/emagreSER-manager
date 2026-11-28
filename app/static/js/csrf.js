/**
 * Adds the CSRF token header to same-origin state-changing fetch calls.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Name of the request header that carries the CSRF token.
     * @type {string}
     */
    const HEADER_NAME = "X-CSRFToken";

    /**
     * Selector of the meta tag that holds the CSRF token of the page.
     * @type {string}
     */
    const META_SELECTOR = 'meta[name="csrf-token"]';

    /**
     * Methods that change state on the server and therefore need the token.
     * @type {ReadonlyArray<string>}
     */
    const PROTECTED_METHODS = ["POST", "PUT", "PATCH", "DELETE"];

    /**
     * Key that marks the wrapper, so loading this script twice wraps fetch only once.
     * @type {symbol}
     */
    const WRAPPED_KEY = Symbol.for("emagreser.csrfFetch");

    /**
     * Original fetch function of the browser.
     * @type {typeof window.fetch}
     */
    const nativeFetch = window.fetch;

    /**
     * Reads the CSRF token of the page at the time of the request.
     * @returns {string} The token, or an empty string when the page has none.
     */
    function readToken() {
        const meta = document.querySelector(META_SELECTOR);
        return (meta && meta.getAttribute("content")) || "";
    }

    /**
     * Tells whether a fetch input is a Request object.
     * @param {RequestInfo | URL} input First argument of fetch.
     * @returns {boolean} True for a Request.
     */
    function isRequest(input) {
        return typeof Request !== "undefined" && input instanceof Request;
    }

    /**
     * Finds the HTTP method a fetch call will use, in upper case.
     * @param {RequestInfo | URL} input First argument of fetch.
     * @param {RequestInit | undefined} init Second argument of fetch.
     * @returns {string} The method; GET when nothing sets another one.
     */
    function methodOf(input, init) {
        const own = init && init.method;
        const method = own || (isRequest(input) ? /** @type {Request} */ (input).method : "GET");
        return String(method).toUpperCase();
    }

    /**
     * Tells whether a fetch input points to the origin of the page.
     * @param {RequestInfo | URL} input First argument of fetch.
     * @returns {boolean} True when the address resolves to the same origin as the page.
     */
    function isSameOrigin(input) {
        try {
            const address = isRequest(input) ? /** @type {Request} */ (input).url : String(input);
            const origin = new URL(address, document.baseURI).origin;
            return origin !== "null" && origin === window.location.origin;
        } catch {
            return false;
        }
    }

    /**
     * Builds the headers of a call with the token added, unless the caller already set it.
     * @param {RequestInfo | URL} input First argument of fetch.
     * @param {RequestInit | undefined} init Second argument of fetch.
     * @param {string} token CSRF token to send.
     * @returns {Headers | null} The headers to send, or null when the caller already sent the token header.
     */
    function headersWithToken(input, init, token) {
        const hasOwnHeaders = Boolean(init) && init.headers !== undefined;
        const requestHeaders = isRequest(input) ? /** @type {Request} */ (input).headers : undefined;
        const headers = new Headers(hasOwnHeaders ? init.headers : requestHeaders);
        if (headers.has(HEADER_NAME)) {
            return null;
        }
        headers.set(HEADER_NAME, token);
        return headers;
    }

    /**
     * Calls the original fetch, adding the token header to state-changing requests to the page's own origin.
     * The body and every other option of the call are passed on untouched.
     * @param {RequestInfo | URL} input Resource to request.
     * @param {RequestInit} [init] Options of the request.
     * @returns {Promise<Response>} The pending response.
     */
    function fetchWithToken(input, init) {
        const token = readToken();
        if (!token || !PROTECTED_METHODS.includes(methodOf(input, init)) || !isSameOrigin(input)) {
            return nativeFetch.call(window, input, init);
        }
        let headers = null;
        try {
            headers = headersWithToken(input, init, token);
        } catch {
            headers = null;
        }
        if (headers === null) {
            return nativeFetch.call(window, input, init);
        }
        return nativeFetch.call(window, input, Object.assign({}, init, { headers }));
    }

    if (typeof nativeFetch !== "function" || nativeFetch[WRAPPED_KEY]) {
        return;
    }
    fetchWithToken[WRAPPED_KEY] = true;
    window.fetch = fetchWithToken;
})();
