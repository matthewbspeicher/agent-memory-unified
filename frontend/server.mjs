/**
 * Production frontend server — proxies API paths to the trading backend,
 * serves the Vite-built SPA for everything else.
 *
 * Solves the "remembr.dev/* returns HTML for every path" problem: prior
 * setup used `serve -s dist` which falls through everything to index.html,
 * so API calls against remembr.dev silently served the SPA instead of
 * reaching the trading service. This server reverse-proxies the known
 * API path prefixes upstream and only falls through for genuine SPA
 * routes.
 *
 * Env:
 *   PORT                 — listen port (Railway sets this)
 *   TRADING_UPSTREAM_URL — where to proxy API traffic. Defaults to the
 *                         Railway private hostname; override with the
 *                         public *.up.railway.app domain for local dev
 *                         or if private networking isn't available.
 *   STATIC_DIR           — directory with built SPA. Defaults to ./dist.
 *
 * Keep it small. Drop-in replacement for `serve -s dist -l $PORT`.
 */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
// http-proxy is CommonJS — import the default and destructure.
import httpProxy from "http-proxy";
const { createProxyServer } = httpProxy;

const PORT = Number(process.env.PORT || 3000);
const STATIC_DIR = path.resolve(process.env.STATIC_DIR || "./dist");

// Default upstream: Railway private DNS (same-project inter-service).
// `trading.railway.internal` resolves only from inside Railway; from a
// local machine, override with the public *.up.railway.app host.
const UPSTREAM = (
  process.env.TRADING_UPSTREAM_URL || "http://trading.railway.internal:8080"
).replace(/\/+$/, "");

// Path prefixes that must proxy upstream to the trading backend.
// Anything not matched falls through to static file serving (SPA).
// Keep this list aligned with app.py router registrations.
const API_PREFIXES = [
  "/api/",           // all /api/v1/* routes (feeds, orders, risk, etc.)
  "/engine/",        // /engine/v1/bittensor/* canonical bittensor path
  "/agents/",        // agents router (prefix=/agents in the APIRouter)
  "/shadow/",        // shadow execution read API
  "/stripe/",        // /stripe/webhooks (disabled behind STA_STRIPE_ENABLED)
  "/ready",          // readiness probe
  "/health",         // /health + /health-internal
  "/metrics",        // Prometheus scrape endpoint
];

const shouldProxy = (urlPath) =>
  API_PREFIXES.some((prefix) =>
    prefix.endsWith("/") ? urlPath.startsWith(prefix) : urlPath === prefix || urlPath.startsWith(prefix + "?")
  );

// http-proxy handles keep-alive, streaming, websockets, and header
// rewrites for us. `changeOrigin: true` rewrites the Host header to the
// upstream's value — required when the upstream checks Host (some
// reverse-proxy hygiene).
const proxy = createProxyServer({
  target: UPSTREAM,
  changeOrigin: true,
  // Preserve the original Host in X-Forwarded-Host so the upstream can
  // log it; Railway's edge already sets X-Forwarded-Proto + For.
  xfwd: true,
  // Don't follow redirects — let the client handle them.
  followRedirects: false,
  // Reasonable timeout to avoid hanging sockets. The trading backend's
  // /agents/{name}/scan can run 30s; keep some headroom above that.
  proxyTimeout: 60_000,
  timeout: 60_000,
});

proxy.on("error", (err, _req, res) => {
  console.error(`[proxy] upstream error: ${err.message} (target=${UPSTREAM})`);
  if (res && !res.headersSent) {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        detail: "Upstream trading service unreachable",
        upstream_error: err.code || err.message,
      })
    );
  }
});

// Static-file handler. Small, no dependencies. Returns index.html for
// anything that isn't a file on disk — standard SPA fallback.
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
};

const serveStatic = (req, res) => {
  // Strip query string, decode, prevent path traversal.
  const rawPath = req.url.split("?")[0];
  let decoded;
  try {
    decoded = decodeURIComponent(rawPath);
  } catch {
    decoded = rawPath;
  }
  const safePath = path.posix.normalize(decoded).replace(/^\/+/, "");
  let filePath = path.join(STATIC_DIR, safePath);
  if (!filePath.startsWith(STATIC_DIR)) {
    filePath = path.join(STATIC_DIR, "index.html");
  }

  // If not a real file, fall back to index.html for the SPA router.
  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      filePath = path.join(STATIC_DIR, "index.html");
    }
    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME[ext] || "application/octet-stream";
    // Long-cache hashed assets under /assets/, no-cache for HTML entry.
    const cacheControl =
      path.posix.normalize(rawPath).startsWith("/assets/") && ext !== ".html"
        ? "public, max-age=31536000, immutable"
        : "no-cache";
    res.writeHead(200, {
      "Content-Type": contentType,
      "Cache-Control": cacheControl,
    });
    fs.createReadStream(filePath).pipe(res);
  });
};

const server = http.createServer((req, res) => {
  if (shouldProxy(req.url)) {
    proxy.web(req, res);
  } else {
    serveStatic(req, res);
  }
});

// Handle websocket upgrades for any proxied path (not currently used by
// the trading backend, but future-proof for streaming APIs).
server.on("upgrade", (req, socket, head) => {
  if (shouldProxy(req.url)) {
    proxy.ws(req, socket, head);
  } else {
    socket.destroy();
  }
});

server.listen(PORT, () => {
  console.log(
    `[frontend] listening on :${PORT}  upstream=${UPSTREAM}  static=${STATIC_DIR}`
  );
  console.log(`[frontend] proxy prefixes: ${API_PREFIXES.join(", ")}`);
});
