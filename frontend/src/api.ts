import type { ChatResponse } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

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

export async function sendQuestion(question: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ question })
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
