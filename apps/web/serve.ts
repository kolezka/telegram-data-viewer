import index from "./index.html";

const FASTAPI = "http://127.0.0.1:5000";

function shouldProxy(pathname: string): boolean {
  return (
    pathname.startsWith("/api/") ||
    pathname === "/docs" ||
    pathname.startsWith("/docs/") ||
    pathname === "/redoc" ||
    pathname.startsWith("/redoc/") ||
    pathname === "/openapi.json"
  );
}

const server = Bun.serve({
  port: 5173,
  routes: { "/": index },
  async fetch(req) {
    const url = new URL(req.url);
    if (shouldProxy(url.pathname)) {
      const upstream = `${FASTAPI}${url.pathname}${url.search}`;
      try {
        return await fetch(upstream, {
          method: req.method,
          headers: req.headers,
          body: req.body,
        });
      } catch (err) {
        return new Response(`Proxy error: cannot reach ${FASTAPI}\n${err}`, { status: 502 });
      }
    }
    return new Response("Not found", { status: 404 });
  },
  development: { hmr: true, console: true },
});

console.log(`Web dev server: http://${server.hostname}:${server.port}`);
console.log(`Proxying /api/*, /docs, /redoc, /openapi.json → ${FASTAPI}`);
