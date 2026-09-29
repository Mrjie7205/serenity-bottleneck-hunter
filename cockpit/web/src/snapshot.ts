// 全局快照 store:股价同步状态 + 进度轮询 + rebuild,单例供导航按钮和计分卡共用
// 一个轮询循环,无论多少组件订阅,状态唯一,不会各转各的。
import { useSyncExternalStore } from "react";
import { api } from "./api";
import { createSnapshotStore } from "./snapshotStore";
import type { SnapshotStatus } from "./types";

const store = createSnapshotStore(api);
const serverView = { snap: null, error: "", starting: false };
export const rebuildSnapshot = store.rebuild;

export function useSnapshot() {
  const { snap, error, starting } = useSyncExternalStore(store.subscribe, store.getSnapshot, () => serverView);
  return { snap, error, rebuild: rebuildSnapshot, running: starting || (!!snap?.progress?.running && !error) };
}

// 快照年龄(小时);无快照返回 null
export function snapshotAgeHours(snap: SnapshotStatus | null): number | null {
  if (!snap?.generated_at) return null;
  const t = Date.parse(snap.generated_at.replace(" ", "T"));
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 3.6e6;
}
