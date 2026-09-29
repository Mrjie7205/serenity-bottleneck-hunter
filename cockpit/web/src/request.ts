export type RequestOptions = { signal?: AbortSignal; timeoutMs?: number };

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

export const isAbortError = (error: unknown): boolean =>
  error instanceof Error && error.name === "AbortError";

// 所有请求共用超时和取消逻辑;保留 HTTP 状态,避免把任意失败当成 409。
export async function request<T>(url: string, method: "GET" | "POST", options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const { signal, timeoutMs = 30_000 } = options;
  let timedOut = false;
  const cancel = () => controller.abort(signal?.reason);
  if (signal?.aborted) cancel();
  else signal?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    controller.signal.throwIfAborted();
    const response = await fetch(url, { method, signal: controller.signal, headers: { "X-Serenity-Request": "cockpit" } });
    controller.signal.throwIfAborted();
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json();
        const message = body?.detail ?? body?.error;
        if (typeof message === "string") detail = message;
      } catch { /* 非 JSON 错误响应仍保留 HTTP 状态。 */ }
      throw new ApiError(`请求失败 (${response.status})${detail ? `：${detail}` : ""}`, response.status);
    }
    const data = await response.json() as T;
    controller.signal.throwIfAborted();
    return data;
  } catch (error) {
    if (timedOut && !signal?.aborted) throw new Error("请求超时，请稍后重试；已启动的后台任务可能仍在继续。");
    if (signal?.aborted || isAbortError(error) || error instanceof ApiError) throw error;
    throw new Error(`无法完成请求：${errorMessage(error)}`);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}
