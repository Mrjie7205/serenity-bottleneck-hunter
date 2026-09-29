import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/request.ts", import.meta.url))],
  bundle: true, format: "esm", platform: "node", write: false,
});
const { request, ApiError } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);

test("HTTP errors preserve status and server detail", async (t) => {
  for (const status of [409, 500]) {
    t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ error: "specific failure" }), { status }));
    await assert.rejects(request("/api/test", "POST"), (error) =>
      error instanceof ApiError && error.status === status && error.message.includes("specific failure"));
    t.mock.restoreAll();
  }
});

test("non-JSON failure still preserves HTTP status", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("upstream failed", { status: 502 }));
  await assert.rejects(request("/api/test", "GET"), (error) => error instanceof ApiError && error.status === 502);
});

test("cancelled old response cannot be returned after the new request", async (t) => {
  let resolveOld;
  t.mock.method(globalThis, "fetch", (url) => url.includes("old")
    ? new Promise((resolve) => { resolveOld = resolve; })
    : Promise.resolve(new Response(JSON.stringify({ rows: ["new"] }))));
  const controller = new AbortController();
  const old = request("/api/picks?q=old", "GET", { signal: controller.signal });
  controller.abort();
  assert.deepEqual(await request("/api/picks?q=new", "GET"), { rows: ["new"] });
  const cancelled = assert.rejects(old, { name: "AbortError" });
  resolveOld(new Response(JSON.stringify({ rows: ["old"] })));
  await cancelled;
});

test("timeout stops waiting and reports a timeout", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  t.mock.method(globalThis, "fetch", (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  }));
  const pending = request("/api/test", "GET", { timeoutMs: 50 });
  const timedOut = assert.rejects(pending, /请求超时/);
  t.mock.timers.tick(50);
  await timedOut;
});

test("an already cancelled request never reaches the server", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response("{}"));
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(request("/api/test", "GET", { signal: controller.signal }), { name: "AbortError" });
  assert.equal(fetch.mock.callCount(), 0);
});
