import { ApiError, errorMessage, isAbortError, type RequestOptions } from "./request";
import type { SnapshotStatus } from "./types";

type SnapshotApi = {
  snapshotStatus: (options?: RequestOptions) => Promise<SnapshotStatus>;
  runSnapshot: (limit?: number, options?: RequestOptions) => Promise<{ started: boolean }>;
};

export type SnapshotView = { snap: SnapshotStatus | null; error: string; starting: boolean };
type PollOptions = {
  intervalMs?: number;
  maxPollingMs?: number;
  now?: () => number;
};

// 可注入 API 的单例实现:请求失败和等待上限均会结束轮询,保留最后有效快照。
export function createSnapshotStore(api: SnapshotApi, options: PollOptions = {}) {
  const { intervalMs = 2500, maxPollingMs = 20 * 60_000, now = Date.now } = options;
  let view: SnapshotView = { snap: null, error: "", starting: false };
  const listeners = new Set<() => void>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let deadline = 0;
  let generation = 0;
  let statusRequest: AbortController | undefined;

  const publish = (next: Partial<SnapshotView>) => {
    view = { ...view, ...next };
    listeners.forEach((fn) => fn());
  };
  const stopPolling = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    deadline = 0;
  };

  async function refresh(): Promise<SnapshotStatus | null> {
    const current = ++generation;
    statusRequest?.abort();
    const request = new AbortController();
    statusRequest = request;
    try {
      const snap = await api.snapshotStatus({ signal: request.signal });
      if (current !== generation || request.signal.aborted) return null;
      const error = snap.progress.error ? `快照构建失败：${snap.progress.error}` : "";
      publish({ snap, error });
      if (error) stopPolling();
      return snap;
    } catch (error) {
      if (current !== generation || request.signal.aborted || isAbortError(error)) return null;
      stopPolling();
      publish({ error: `同步状态读取失败：${errorMessage(error)} 点击「同步股价」可重新检查。` });
      return null;
    } finally {
      if (current === generation) statusRequest = undefined;
    }
  }

  function startPolling() {
    if (timer !== undefined || !listeners.size || view.error) return;
    if (!deadline) deadline = now() + maxPollingMs;
    timer = setTimeout(async () => {
      timer = undefined;
      if (now() >= deadline) {
        stopPolling();
        publish({ error: "等待同步超过 20 分钟，已停止自动查询；后台任务可能仍在继续。点击「同步股价」可重新检查。" });
        return;
      }
      const snap = await refresh();
      // 取消的旧查询不能停掉新订阅或重试刚启动的轮询。
      if (!snap) return;
      if (snap.progress.running && !view.error) startPolling();
      else stopPolling();
    }, intervalMs);
  }

  async function rebuild() {
    if (view.starting) return;
    stopPolling();
    ++generation;
    statusRequest?.abort();
    publish({ starting: true, error: "" });
    try {
      try {
        const result = await api.runSnapshot(0);
        if (!result.started) throw new Error("服务未确认启动快照任务，请稍后重试。");
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 409)) throw error;
      }
      const snap = await refresh();
      if (snap?.progress.running && !view.error) startPolling();
    } catch (error) {
      stopPolling();
      publish({ error: `同步请求失败：${errorMessage(error)}` });
    } finally {
      publish({ starting: false });
    }
  }

  function subscribe(listener: () => void) {
    listeners.add(listener);
    if (!view.starting) {
      void refresh().then((snap) => {
        if (!snap) return;
        if (snap.progress.running && !view.error) startPolling();
        else stopPolling();
      });
    }
    return () => {
      listeners.delete(listener);
      if (!listeners.size) {
        stopPolling();
        ++generation;
        statusRequest?.abort();
      }
    };
  }

  return { subscribe, getSnapshot: () => view, rebuild };
}
