import index from "./index.html";

const server = Bun.serve({
  port: 5173,
  routes: { "/": index },
  development: {
    hmr: true,
    console: true,
  },
});

console.log(`Web dev server: http://${server.hostname}:${server.port}`);
