import { afterEach, describe, expect, it, vi } from "vitest";

import { deleteMemoryItem, sendQuestion, submitFeedback } from "./api";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API client", () => {
  it("sends the request-level memory preference", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ answer: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await sendQuestion("質問", "client-001", "conversation-001", false);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      question: "質問",
      client_id: "client-001",
      conversation_id: "conversation-001",
      use_memory: false
    });
  });

  it("deletes one memory item", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ deleted: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteMemoryItem("client-001", "item/001");

    expect(fetchMock.mock.calls[0][0]).toContain("/memory/items/item%2F001");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "DELETE" });
  });

  it("submits answer feedback with an optional reason", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await submitFeedback(
      "request-001",
      "client-001",
      "conversation-001",
      "unhelpful",
      "引用を改善してほしい"
    );

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      request_id: "request-001",
      rating: "unhelpful",
      reason: "引用を改善してほしい"
    });
  });
});
