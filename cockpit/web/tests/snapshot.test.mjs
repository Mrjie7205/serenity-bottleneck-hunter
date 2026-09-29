import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { setImmediate as settle } from "node:timers/promises";

const bundle = await build({
  stdin: { contents: 'export { createSnapshotStore } from "./snapshotStore"; export { ApiError } from "./request";', resolveDir: fileURLToPath(new URL("../src", import.meta.url)), loader: "ts" },
  bundle: true, format: "esm", platform: "node", write: false,
});
const { createSnapshotStore, ApiError } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);
const status = (running, extra = {}) => ({ exists: true, progress: { running, done: 0, total: 2, phase: "", ...extra } });

async function fixture(t, api, options = {}) {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const store = createSnapshotStore(api, options);
  const unsubscribe = store.subscribe(() => {});
  t.after(unsubscribe);
  await settle();
  return store;
}

test("HTTP 500 stops immediately without entering polling", async (t) => {
  let reads = 0;
  const store = await fixture(t, {
    snapshotStatus: async () => { reads++; return status(false); },
    runSnapshot: async () => { throw new ApiError("disk unavailable", 500); },
  });
  await store.rebuild();
  assert.match(store.getSnapshot().error, /disk unavailable/);
  assert.equal(store.getSnapshot().starting, false);
  t.mock.timers.tick(60_000);
  await settle();
  assert.equal(reads, 1);
});

test("only HTTP 409 resumes the existing task and stops on completion", async (t) => {
  let reads = 0;
  const store = await fixture(t, {
    snapshotStatus: async () => status(++reads === 2),
    runSnapshot: async () => { throw new ApiError("already running", 409); },
  });
  await store.rebuild();
  assert.equal(store.getSnapshot().snap.progress.running, true);
  assert.equal(store.getSnapshot().error, "");
  t.mock.timers.tick(2500);
  await settle();
  assert.equal(store.getSnapshot().snap.progress.running, false);
  t.mock.timers.tick(60_000);
  await settle();
  assert.equal(reads, 3);
});

test("HTTP success without a started task is displayed as a failure", async (t) => {
  const store = await fixture(t, {
    snapshotStatus: async () => status(false),
    runSnapshot: async () => ({ started: false }),
  });
  await store.rebuild();
  assert.match(store.getSnapshot().error, /未确认启动/);
});

test("status failure preserves the last valid snapshot and ends polling", async (t) => {
  let reads = 0;
  const store = await fixture(t, {
    snapshotStatus: async () => {
      reads++;
      if (reads === 3) throw new Error("offline");
      return status(reads === 2);
    },
    runSnapshot: async () => ({ started: true }),
  });
  await store.rebuild();
  const last = store.getSnapshot().snap;
  t.mock.timers.tick(2500);
  await settle();
  assert.match(store.getSnapshot().error, /offline/);
  assert.equal(store.getSnapshot().snap, last);
  t.mock.timers.tick(60_000);
  await settle();
  assert.equal(reads, 3);
});

test("backend task error is visible; partial price misses remain usable", async (t) => {
  let next = status(false, { error: "snapshot write failed" });
  const store = await fixture(t, {
    snapshotStatus: async () => next,
    runSnapshot: async () => ({ started: true }),
  });
  assert.match(store.getSnapshot().error, /snapshot write failed/);
  next = { ...status(false), error_count: 4, partial: false };
  await store.rebuild();
  assert.equal(store.getSnapshot().error, "");
  assert.equal(store.getSnapshot().snap.error_count, 4);
});

test("a running task has a bounded polling window", async (t) => {
  let now = 0;
  let reads = 0;
  const store = await fixture(t, {
    snapshotStatus: async () => { reads++; return status(true); },
    runSnapshot: async () => ({ started: true }),
  }, { maxPollingMs: 5000, now: () => now });
  now = 2500;
  t.mock.timers.tick(2500);
  await settle();
  assert.equal(reads, 2);
  now = 5000;
  t.mock.timers.tick(2500);
  await settle();
  assert.match(store.getSnapshot().error, /停止自动查询/);
  now = 50_000;
  t.mock.timers.tick(45_000);
  await settle();
  assert.equal(reads, 2);
});

test("unsubscribing aborts the status request and prevents late state writes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let resolveStatus;
  let signal;
  const store = createSnapshotStore({
    snapshotStatus: (options) => {
      signal = options.signal;
      return new Promise((resolve) => { resolveStatus = resolve; });
    },
    runSnapshot: async () => ({ started: true }),
  });
  const unsubscribe = store.subscribe(() => {});
  unsubscribe();
  assert.equal(signal.aborted, true);
  resolveStatus(status(true));
  await settle();
  assert.equal(store.getSnapshot().snap, null);
});

test("a cancelled polling response cannot stop a newer subscriber's polling", async (t) => {
  let reads = 0;
  let resolveOld;
  const store = await fixture(t, {
    snapshotStatus: async () => {
      reads++;
      if (reads === 2) return new Promise((resolve) => { resolveOld = resolve; });
      return status(reads < 4);
    },
    runSnapshot: async () => ({ started: true }),
  });
  t.mock.timers.tick(2500);
  await settle();
  const unsubscribe = store.subscribe(() => {});
  t.after(unsubscribe);
  await settle();
  resolveOld(status(false));
  await settle();
  assert.equal(store.getSnapshot().snap.progress.running, true);
  t.mock.timers.tick(2500);
  await settle();
  assert.equal(reads, 4);
  assert.equal(store.getSnapshot().snap.progress.running, false);
});
