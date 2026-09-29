// 全局镜头(双镜头):hunt=猎手(只看上游瓶颈) / coverage=覆盖(完整AI全栈)
// localStorage 持久化 + useSyncExternalStore 跨页响应。默认 hunt(我们是瓶颈猎手)。
import { useSyncExternalStore } from "react";

export type Lens = "hunt" | "coverage";
const KEY = "serenity.lens";
let listeners: Array<() => void> = [];

function read(): Lens {
  try {
    return localStorage.getItem(KEY) === "coverage" ? "coverage" : "hunt";
  } catch {
    return "hunt";
  }
}

export function setLens(l: Lens) {
  try { localStorage.setItem(KEY, l); } catch { /* ignore */ }
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.push(fn);
  // 跨标签页同步:另一标签改了镜头 → 本标签也更新
  const onStorage = (e: StorageEvent) => { if (e.key === KEY) fn(); };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners = listeners.filter((x) => x !== fn);
    window.removeEventListener("storage", onStorage);
  };
}

export function useLens(): [Lens, (l: Lens) => void] {
  const lens = useSyncExternalStore(subscribe, read, () => "hunt" as Lens);
  return [lens, setLens];
}

export const LENS_META: Record<Lens, { label: string; icon: string; desc: string }> = {
  hunt: { label: "猎手", icon: "🎯", desc: "只看上游卡脖子瓶颈 — 我们的主战场(L0-L4 物理栈 + 数据/安全)" },
  coverage: { label: "覆盖", icon: "🗺️", desc: "完整 AI 全栈 — 含云/模型/应用大盘等覆盖型主题" },
};
