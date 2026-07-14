import type { ChatResponse, MemoryListResponse } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const LOCAL_AUTH_TOKEN = import.meta.env.VITE_LOCAL_AUTH_TOKEN as string | undefined;

function requestHeaders(json = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  if (LOCAL_AUTH_TOKEN) headers.Authorization = `Bearer ${LOCAL_AUTH_TOKEN}`;
  return headers;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function extractErrorMessage(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim()) {
    return payload.trim();
  }

  if (!payload || typeof payload !== "object") {
    return null;
  }

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (!Array.isArray(detail)) {
    return null;
  }

  const messages = detail
    .map((item) => {
      if (typeof item === "string") {
        return item.trim();
      }

      if (!item || typeof item !== "object") {
        return "";
      }

      const msg = typeof (item as { msg?: unknown }).msg === "string"
        ? (item as { msg: string }).msg.trim()
        : "";
      const loc = Array.isArray((item as { loc?: unknown }).loc)
        ? (item as { loc: unknown[] }).loc.join(".")
        : "";

      if (!msg) return "";
      return loc ? `${msg} (${loc})` : msg;
    })
    .filter(Boolean);

  return messages.length > 0 ? messages.join(" / ") : null;
}

export async function sendQuestion(
  question: string,
  clientId: string,
  conversationId: string,
  useMemory = true
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: requestHeaders(true),
    body: JSON.stringify({
      question,
      client_id: clientId,
      conversation_id: conversationId,
      use_memory: useMemory
    })
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      extractErrorMessage(payload) ??
      `API request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return payload as ChatResponse;
}

export async function getMemory(clientId: string): Promise<MemoryListResponse> {
  const params = new URLSearchParams({ client_id: clientId });
  const response = await fetch(`${API_BASE_URL}/memory?${params}`, {
    headers: requestHeaders()
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload) ?? "記憶データの取得に失敗しました。",
      response.status
    );
  }
  return payload as MemoryListResponse;
}

export async function clearMemory(
  clientId: string,
  conversationId?: string
): Promise<number> {
  const params = new URLSearchParams({ client_id: clientId });
  if (conversationId) params.set("conversation_id", conversationId);
  const response = await fetch(`${API_BASE_URL}/memory?${params}`, {
    method: "DELETE",
    headers: requestHeaders()
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload) ?? "記憶データの削除に失敗しました。",
      response.status
    );
  }
  return Number((payload as { deleted?: number }).deleted ?? 0);
}

export async function deleteMemoryItem(
  clientId: string,
  itemId: string
): Promise<void> {
  const params = new URLSearchParams({ client_id: clientId });
  const response = await fetch(`${API_BASE_URL}/memory/items/${encodeURIComponent(itemId)}?${params}`, {
    method: "DELETE",
    headers: requestHeaders()
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload) ?? "記憶データの削除に失敗しました。",
      response.status
    );
  }
}

export async function submitFeedback(
  requestId: string,
  clientId: string,
  conversationId: string,
  rating: "helpful" | "unhelpful",
  reason = ""
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/feedback`, {
    method: "POST",
    headers: requestHeaders(true),
    body: JSON.stringify({
      request_id: requestId,
      client_id: clientId,
      conversation_id: conversationId,
      rating,
      reason
    })
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload) ?? "フィードバックの保存に失敗しました。",
      response.status
    );
  }
}
