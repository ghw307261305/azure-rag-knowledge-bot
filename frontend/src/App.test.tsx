import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const { sendQuestion, submitFeedback } = vi.hoisted(() => ({
  sendQuestion: vi.fn(),
  submitFeedback: vi.fn(),
}));

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {},
  clearMemory: vi.fn(),
  deleteMemoryItem: vi.fn(),
  getMemory: vi.fn().mockResolvedValue({ items: [] }),
  sendQuestion,
  submitFeedback,
}));

import App from "./App";

beforeEach(() => {
  localStorage.clear();
  sendQuestion.mockReset();
  submitFeedback.mockReset();
  sendQuestion.mockResolvedValue({
    request_id: "request-001",
    answer: "受付状態が RECEIVED の場合は取消可能です。[S1]",
    citations: [{ title: "振込手順", chunk_id: "chunk-001", content: "根拠" }],
    retrieved_chunks: [],
    latency_ms: 12,
    rewritten_query: "振込取消",
    token_usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    rag_mode: "mock",
    model: "",
    fallback_used: false,
    sanitized_question: "振込は取り消せますか",
    memory_usage: {
      enabled: true,
      context_items: 0,
      stored_items: 0,
      masked_pii: [],
      dropped_items: 0,
    },
    generation_metrics: {
      context_chunks: 0,
      context_characters: 0,
      prompt_characters: 0,
      model_load_ms: 0,
      prompt_eval_ms: 0,
      generation_ms: 0,
      ollama_total_ms: 0,
      prompt_tokens_per_second: 0,
      generation_tokens_per_second: 0,
      done_reason: "",
      fallback_reason: "",
      evidence_completion_used: false,
    },
  });
  submitFeedback.mockResolvedValue(undefined);
});

it("toggles memory and records helpful feedback", async () => {
  render(<App />);

  const memoryToggle = screen.getByRole("button", { name: "Memory ON" });
  fireEvent.click(memoryToggle);
  expect(screen.getByRole("button", { name: "Memory OFF" })).toHaveAttribute(
    "aria-pressed",
    "false"
  );

  fireEvent.change(screen.getByPlaceholderText(/メッセージを入力/), {
    target: { value: "振込は取り消せますか" },
  });
  fireEvent.click(screen.getByRole("button", { name: "送信" }));

  expect(await screen.findByText(/RECEIVED/)).toBeInTheDocument();
  expect(sendQuestion).toHaveBeenCalledWith(
    "振込は取り消せますか",
    expect.any(String),
    expect.any(String),
    false
  );

  fireEvent.click(screen.getByRole("button", { name: "役に立った" }));
  await waitFor(() => expect(submitFeedback).toHaveBeenCalled());
  expect(await screen.findByText("送信済み")).toBeInTheDocument();
});
