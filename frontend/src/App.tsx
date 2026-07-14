// チャット UI、会話履歴、会話記憶の操作をまとめる画面コンポーネント。
import { KeyboardEvent, useEffect, useRef, useState } from "react";

import {
  ApiError,
  clearMemory,
  deleteMemoryItem,
  getMemory,
  sendQuestion,
  submitFeedback,
} from "./api";
import type { MemoryItem, Message } from "./types";

// ── 会話セッション型 ────────────────────────────────────────
interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string; // ISO string for localStorage serialization
}

const STORAGE_KEY = "rag_conversations";
const CLIENT_ID_KEY = "rag_client_id";
const MEMORY_PREFERENCE_KEY = "rag_memory_enabled";
const MAX_HISTORY = 30;

function sanitizeLocalHistoryText(value: string): string {
  // サーバーと同じ主要 PII を、ブラウザへ履歴保存する前にも防御的にマスクする。
  return value
    .normalize("NFKC")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
    .replace(/[\u200b-\u200f\u2060\ufeff]/g, "")
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[EMAIL]")
    .replace(/(?<!\d)(?:\+81[- ]?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)/g, "[PHONE]")
    .replace(/(?<!\d)〒?\d{3}-?\d{4}(?!\d)/g, "[POSTAL_CODE]")
    .replace(/(?<!\d)\d{10,19}(?!\d)/g, "[LONG_NUMBER]");
}

function loadConversations(): Conversation[] {
  // 保存形式の破損で画面全体が起動不能にならないよう、読込失敗は空履歴へ戻す。
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    // 過去バージョンの未マスク履歴も、読み込んだ時点で再保存して安全化する。
    const sanitized = parsed.map((c) => ({
      ...c,
      messages: c.messages.map((m) => ({
        ...m,
        question: sanitizeLocalHistoryText(m.question),
        answer: sanitizeLocalHistoryText(m.answer),
        timestamp: new Date(m.timestamp)
      })),
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitized.slice(0, MAX_HISTORY)));
    return sanitized;
  } catch {
    return [];
  }
}

function saveConversations(convs: Conversation[]) {
  // localStorage の肥大化を避けるため、新しい会話から最大件数だけ保存する。
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs.slice(0, MAX_HISTORY)));
  } catch {
    // 容量超過時もチャット自体は継続できるため、保存失敗は UI を止めない。
  }
}

const SAMPLE_QUESTIONS = [
  "本人確認書類の住所と申込住所が異なる場合はどうしますか？",
  "振込はいつまで取り消せますか？",
  "AML アラートが出たら直ちに口座を凍結しますか？",
  "返済が一度遅れた場合はどのように対応しますか？",
];

// ── SVG アイコン ────────────────────────────────────────────
const SendIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 2 11 13" /><path d="M22 2 15 22 11 13 2 9l20-7z" />
  </svg>
);
const DocIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
  </svg>
);
const BotIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4" /><path d="M8 15h.01M12 15h.01M16 15h.01" />
  </svg>
);
const PlusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 5v14M5 12h14" />
  </svg>
);
const ChatIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);
const TrashIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" />
  </svg>
);

function formatTime(date: Date): string {
  return date.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
}

function formatDate(isoString: string): string {
  const d = new Date(isoString);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "今日";
  if (d.toDateString() === yesterday.toDateString()) return "昨日";
  return d.toLocaleDateString("ja-JP", { month: "short", day: "numeric" });
}

function generateId(): string {
  // 対応ブラウザでは標準 UUID を使い、段階的に安全な代替手段へ降格する。
  const cryptoApi = globalThis.crypto;
  if (cryptoApi?.randomUUID) {
    return cryptoApi.randomUUID();
  }

  if (cryptoApi?.getRandomValues) {
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return [
      hex.slice(0, 4).join(""),
      hex.slice(4, 6).join(""),
      hex.slice(6, 8).join(""),
      hex.slice(8, 10).join(""),
      hex.slice(10, 16).join("")
    ].join("-");
  }

  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getOrCreateClientId(): string {
  // 匿名利用でも、会話記憶の所有者境界として安定したブラウザ ID が必要。
  const current = localStorage.getItem(CLIENT_ID_KEY);
  if (current) return current;
  const created = generateId();
  localStorage.setItem(CLIENT_ID_KEY, created);
  return created;
}

function loadMemoryPreference(): boolean {
  return localStorage.getItem(MEMORY_PREFERENCE_KEY) !== "false";
}

function getDisplayError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return "サーバーへの接続に失敗しました。しばらくしてから再度お試しください。";
}

export default function App() {
  // conversations は保存済み全会話、messages は現在開いている会話の表示状態。
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showDev, setShowDev] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 800);
  const [showMemory, setShowMemory] = useState(false);
  const [memoryItems, setMemoryItems] = useState<MemoryItem[]>([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [memoryEnabled, setMemoryEnabled] = useState(loadMemoryPreference);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // 非同期 API 完了時に古い state を参照しないよう、最新値を ref に同期する。
  const activeConvIdRef = useRef<string | null>(null);
  activeConvIdRef.current = activeConvId;
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  // 入力欄を先に空にしても送信中の質問を表示できるよう、別 ref で保持する。
  const pendingQuestionRef = useRef("");
  const clientIdRef = useRef(getOrCreateClientId());

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit() {
    // 二重送信を防ぎ、送信開始時点の質問と会話 ID を一つのリクエストに固定する。
    const q = question.trim();
    if (!q || loading) return;
    pendingQuestionRef.current = q;
    setQuestion("");
    setError("");
    setLoading(true);
    textareaRef.current?.focus();
    try {
      const currentId = activeConvIdRef.current;
      const requestConversationId = currentId ?? generateId();
      const res = await sendQuestion(
        q,
        clientIdRef.current,
        requestConversationId,
        memoryEnabled
      );
      const newMsg = {
        id: generateId(),
        request_id: res.request_id,
        question: res.sanitized_question || q,
        answer: res.answer,
        citations: res.citations,
        retrieved_chunks: res.retrieved_chunks,
        latency_ms: res.latency_ms,
        rewritten_query: res.rewritten_query,
        token_usage: res.token_usage,
        rag_mode: res.rag_mode,
        model: res.model,
        fallback_used: res.fallback_used,
        sanitized_question: res.sanitized_question,
        memory_usage: res.memory_usage,
        generation_metrics: res.generation_metrics,
        timestamp: new Date(),
      };

      // ref の最新メッセージを使い、待機中に切り替わった state の取りこぼしを防ぐ。
      const updatedMsgs = [...messagesRef.current, newMsg];
      setMessages(updatedMsgs);

      // 初回回答時だけ会話を作り、以降は同じ ID の履歴を更新する。
      const title =
        updatedMsgs[0].question.slice(0, 26) +
        (updatedMsgs[0].question.length > 26 ? "…" : "");
      if (currentId) {
        setConversations((prev) => {
          const updated = prev.map((c) =>
            c.id === currentId ? { ...c, messages: updatedMsgs } : c
          );
          saveConversations(updated);
          return updated;
        });
      } else {
        activeConvIdRef.current = requestConversationId;
        setActiveConvId(requestConversationId);
        setConversations((prev) => {
          const updated = [
            { id: requestConversationId, title, messages: updatedMsgs, createdAt: new Date().toISOString() },
            ...prev,
          ];
          saveConversations(updated);
          return updated;
        });
      }
    } catch (error) {
      setError(getDisplayError(error));
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function startNewConversation() {
    setMessages([]);
    setActiveConvId(null);
    activeConvIdRef.current = null;
    setQuestion("");
    setError("");
  }

  function loadConversation(conv: Conversation) {
    setMessages(conv.messages);
    setActiveConvId(conv.id);
    activeConvIdRef.current = conv.id;
    setError("");
  }

  function deleteConversation(e: React.MouseEvent, convId: string) {
    // クリックが親の「会話を開く」操作へ伝播しないよう先に止める。
    e.stopPropagation();
    setConversations((prev) => {
      const updated = prev.filter((c) => c.id !== convId);
      saveConversations(updated);
      return updated;
    });
    if (activeConvId === convId) {
      startNewConversation();
    }
    // ブラウザ履歴とサーバー記憶は別保存先なので、後者も明示的に削除する。
    void clearMemory(clientIdRef.current, convId).catch(() => {
      setError("会話履歴は削除しましたが、サーバー側の記憶削除に失敗しました。");
    });
  }

  async function openMemoryPanel() {
    // パネルは先に開き、取得中・失敗状態をダイアログ内で表示する。
    setShowMemory(true);
    setMemoryLoading(true);
    setMemoryError("");
    try {
      const response = await getMemory(clientIdRef.current);
      setMemoryItems(response.items);
    } catch (memoryLoadError) {
      setMemoryError(getDisplayError(memoryLoadError));
    } finally {
      setMemoryLoading(false);
    }
  }

  async function clearAllMemory() {
    if (!window.confirm("保存済みの会話記憶をすべて削除しますか？")) return;
    setMemoryLoading(true);
    setMemoryError("");
    try {
      await clearMemory(clientIdRef.current);
      setMemoryItems([]);
    } catch (memoryClearError) {
      setMemoryError(getDisplayError(memoryClearError));
    } finally {
      setMemoryLoading(false);
    }
  }

  function toggleMemory() {
    // 選択は次回起動後も維持するが、既に保存された記憶の削除は別操作とする。
    setMemoryEnabled((current) => {
      const next = !current;
      localStorage.setItem(MEMORY_PREFERENCE_KEY, String(next));
      return next;
    });
  }

  async function removeMemoryItem(itemId: string) {
    setMemoryLoading(true);
    setMemoryError("");
    try {
      await deleteMemoryItem(clientIdRef.current, itemId);
      setMemoryItems((current) => current.filter((item) => item.id !== itemId));
    } catch (memoryDeleteError) {
      setMemoryError(getDisplayError(memoryDeleteError));
    } finally {
      setMemoryLoading(false);
    }
  }

  async function rateMessage(
    message: Message,
    rating: "helpful" | "unhelpful"
  ) {
    // request_id がない旧履歴や、保存先会話が未確定の回答は送信対象外。
    if (!message.request_id || !activeConvIdRef.current) return;
    const reason = rating === "unhelpful"
      ? window.prompt("改善してほしい点があれば入力してください（任意）", "") ?? ""
      : "";
    try {
      await submitFeedback(
        message.request_id,
        clientIdRef.current,
        activeConvIdRef.current,
        rating,
        reason
      );
      const updatedMessages = messagesRef.current.map((item) =>
        item.id === message.id ? { ...item, feedback: rating } : item
      );
      setMessages(updatedMessages);
      setConversations((current) => {
        const updated = current.map((conversation) =>
          conversation.id === activeConvIdRef.current
            ? { ...conversation, messages: updatedMessages }
            : conversation
        );
        saveConversations(updated);
        return updated;
      });
    } catch (feedbackError) {
      setError(getDisplayError(feedbackError));
    }
  }

  // 履歴の並び順を保ったまま、表示上の日付ラベルだけでグループ化する。
  const groupedConvs = conversations.reduce<Record<string, Conversation[]>>((acc, c) => {
    const label = formatDate(c.createdAt);
    (acc[label] ??= []).push(c);
    return acc;
  }, {});

  const lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;

  return (
    <div className="layout">

      {/* ── ナビバー ── */}
      <nav className="navbar">
        <div className="navbar-brand">
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            aria-label="サイドバー切り替え"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <span className="navbar-logo"><BotIcon /></span>
          <span className="navbar-title">金融ナレッジアシスタント</span>
        </div>
        <div className="navbar-right">
          <span className="navbar-badge">Financial RAG PoC</span>
          <button
            type="button"
            className={`memory-toggle ${memoryEnabled ? "active" : ""}`}
            onClick={toggleMemory}
            aria-pressed={memoryEnabled}
            title="このブラウザから送る質問で会話記憶を使用するか切り替え"
          >
            Memory {memoryEnabled ? "ON" : "OFF"}
          </button>
          <button
            type="button"
            className={`dev-toggle ${showMemory ? "active" : ""}`}
            onClick={openMemoryPanel}
            title="治理済み会話記憶を確認"
          >
            Memory
          </button>
          <button
            type="button"
            className={`dev-toggle ${showDev ? "active" : ""}`}
            onClick={() => setShowDev((v) => !v)}
            title="開発者情報の表示切り替え"
          >
            Dev
          </button>
        </div>
      </nav>

      {/* ── メインエリア ── */}
      <div className="main-area">

        {/* ── 左：会話履歴サイドバー ── */}
        <aside className={`history-sidebar ${sidebarOpen ? "open" : "closed"}`}>
          <div className="history-header">
            <button
              type="button"
              className="new-chat-btn"
              onClick={startNewConversation}
            >
              <PlusIcon />
              <span>新しい会話</span>
            </button>
          </div>

          <div className="history-list">
            {conversations.length === 0 ? (
              <p className="history-empty">会話履歴はありません</p>
            ) : (
              Object.entries(groupedConvs).map(([label, convs]) => (
                <div key={label} className="history-group">
                  <p className="history-group-label">{label}</p>
                  {convs.map((c) => (
                    <div key={c.id} className={`history-item ${activeConvId === c.id ? "active" : ""}`}>
                      <button
                        type="button"
                        className="history-item-btn"
                        onClick={() => loadConversation(c)}
                      >
                        <ChatIcon />
                        <span className="history-item-title">{c.title}</span>
                      </button>
                      <button
                        type="button"
                        className="history-item-delete"
                        onClick={(e) => deleteConversation(e, c.id)}
                        aria-label="削除"
                        title="削除"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
        </aside>

        {/* ── 中：チャット ── */}
        <div className="chat-panel">

          {/* ウェルカム画面（会話なし時） */}
          {messages.length === 0 && !loading && (
            <div className="welcome">
              <div className="welcome-icon"><BotIcon /></div>
              <h2 className="welcome-title">何でもお聞きください</h2>
              <p className="welcome-desc">
                架空の金融機関向け社内ナレッジをもとに回答します。<br />
                口座・振込・KYC/AML・融資・リスク・障害対応を検索できます。
              </p>
              <div className="suggestion-grid">
                {SAMPLE_QUESTIONS.map((q) => (
                  <button type="button" key={q} className="suggestion-card" onClick={() => setQuestion(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* メッセージ一覧 */}
          <div className="messages">
            {messages.map((msg) => (
              <div key={msg.id} className="msg-group">

                {/* ユーザー */}
                <div className="msg-row msg-row--user">
                  <div className="msg-bubble msg-bubble--user">{msg.question}</div>
                  <span className="msg-time">{formatTime(msg.timestamp)}</span>
                </div>

                {/* アシスタント */}
                <div className="msg-row msg-row--assistant">
                  <div className="msg-avatar"><BotIcon /></div>
                  <div className="msg-content">
                    <div className="msg-bubble msg-bubble--assistant">
                      <p className="msg-answer">{msg.answer}</p>
                    </div>

                    {msg.model && (
                      <div className={`model-status ${msg.fallback_used ? "fallback" : ""}`}>
                        <span>{msg.rag_mode} · {msg.model}</span>
                        {msg.fallback_used && <span>原文回答へ安全に切替済み</span>}
                      </div>
                    )}

                    {/* 引用元ドキュメント */}
                    {msg.citations.length > 0 && (
                      <div className="citation-row">
                        <span className="citation-label">参照資料</span>
                        {msg.citations.map((c) => (
                          <div key={c.chunk_id} className="citation-chip" title={c.content}>
                            <DocIcon />
                            <span>{c.title}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {msg.request_id && (
                      <div className="feedback-row" aria-label="回答フィードバック">
                        <span>この回答は役に立ちましたか？</span>
                        <button
                          type="button"
                          className={msg.feedback === "helpful" ? "active" : ""}
                          onClick={() => void rateMessage(msg, "helpful")}
                          aria-label="役に立った"
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          className={msg.feedback === "unhelpful" ? "active" : ""}
                          onClick={() => void rateMessage(msg, "unhelpful")}
                          aria-label="改善が必要"
                        >
                          👎
                        </button>
                        {msg.feedback && <small>送信済み</small>}
                      </div>
                    )}

                    {/* 開発者情報（Dev モード時のみ） */}
                    {showDev && (
                      <details className="dev-panel">
                        <summary>開発者情報</summary>
                        <dl className="dev-dl">
                          <dt>検索クエリ</dt>
                          <dd>{msg.rewritten_query || "—"}</dd>
                          <dt>実行モード</dt>
                          <dd>{msg.rag_mode || "—"}</dd>
                          <dt>生成モデル</dt>
                          <dd>{msg.model || "未使用"}</dd>
                          <dt>フォールバック</dt>
                          <dd>{msg.fallback_used ? "使用" : "未使用"}</dd>
                          <dt>会話記憶</dt>
                          <dd>
                            {msg.memory_usage?.enabled
                              ? `参照 ${msg.memory_usage.context_items} / 保存 ${msg.memory_usage.stored_items} / 破棄 ${msg.memory_usage.dropped_items}`
                              : "未使用"}
                          </dd>
                          <dt>PII マスク</dt>
                          <dd>{msg.memory_usage?.masked_pii.join(", ") || "なし"}</dd>
                          <dt>生成コンテキスト</dt>
                          <dd>
                            {msg.generation_metrics
                              ? `${msg.generation_metrics.context_chunks} chunks / ${msg.generation_metrics.context_characters} chars`
                              : "—"}
                          </dd>
                          <dt>Ollama 段階時間</dt>
                          <dd>
                            {msg.generation_metrics
                              ? `load ${msg.generation_metrics.model_load_ms.toFixed(0)} / prompt ${msg.generation_metrics.prompt_eval_ms.toFixed(0)} / generate ${msg.generation_metrics.generation_ms.toFixed(0)} ms`
                              : "—"}
                          </dd>
                          <dt>生成速度</dt>
                          <dd>
                            {msg.generation_metrics?.generation_tokens_per_second
                              ? `${msg.generation_metrics.generation_tokens_per_second.toFixed(2)} tokens/s`
                              : "—"}
                          </dd>
                          <dt>回退理由</dt>
                          <dd>{msg.generation_metrics?.fallback_reason || "なし"}</dd>
                          <dt>根拠補完</dt>
                          <dd>
                            {msg.generation_metrics?.evidence_completion_used
                              ? "あり"
                              : "なし"}
                          </dd>
                          <dt>レイテンシ</dt>
                          <dd>{msg.latency_ms} ms</dd>
                          <dt>トークン</dt>
                          <dd>
                            prompt {msg.token_usage.prompt_tokens} /
                            completion {msg.token_usage.completion_tokens} /
                            total {msg.token_usage.total_tokens}
                          </dd>
                          <dt>検索スコア（上位）</dt>
                          <dd>
                            {msg.retrieved_chunks.slice(0, 3).map((c) => (
                              <span key={c.chunk_id} className="dev-score">
                                {c.title.slice(0, 14)}… {c.score.toFixed(3)}
                              </span>
                            ))}
                          </dd>
                        </dl>
                      </details>
                    )}

                    <span className="msg-time">{formatTime(msg.timestamp)}</span>
                  </div>
                </div>
              </div>
            ))}

            {/* ローディング */}
            {loading && (
              <div className="msg-group">
                <div className="msg-row msg-row--user">
                  <div className="msg-bubble msg-bubble--user">{pendingQuestionRef.current}</div>
                </div>
                <div className="msg-row msg-row--assistant">
                  <div className="msg-avatar"><BotIcon /></div>
                  <div className="msg-content">
                    <div className="msg-bubble msg-bubble--assistant thinking">
                      <span className="dot" /><span className="dot" /><span className="dot" />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {error && <div className="error-bar">{error}</div>}

          {/* 入力バー */}
          <div className="input-bar">
            <div className="input-wrap">
              <textarea
                ref={textareaRef}
                rows={1}
                value={question}
                onChange={(e) => {
                  setQuestion(e.target.value);
                  if (error) setError("");
                }}
                onKeyDown={handleKeyDown}
                placeholder="メッセージを入力…（Enter で送信）"
                disabled={loading}
                className="input-textarea"
              />
              <button
                type="button"
                className="send-btn"
                onClick={handleSubmit}
                disabled={loading || !question.trim()}
                aria-label="送信"
              >
                <SendIcon />
              </button>
            </div>
            <p className="input-hint">
              Shift + Enter で改行 · PII は回答生成・保存前にマスクされ、記憶には残りません。
            </p>
          </div>
        </div>

        {/* ── 右：引用パネル ── */}
        <aside className="ref-panel">
          <p className="ref-panel-label">参照資料</p>

          {lastMsg && lastMsg.citations.length > 0 ? (
            <div className="ref-list">
              {lastMsg.citations.map((c) => (
                <div key={c.chunk_id} className="ref-card">
                  <div className="ref-card-header">
                    <DocIcon />
                    <span className="ref-card-title">{c.title}</span>
                  </div>
                  <p className="ref-card-excerpt">{c.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="ref-empty">
              <DocIcon />
              <p>回答後に参照した資料がここに表示されます。</p>
            </div>
          )}

          {lastMsg && showDev && lastMsg.retrieved_chunks.length > 0 && (
            <>
              <p className="ref-panel-label ref-panel-label--section">検索スコア詳細</p>
              <div className="ref-list">
                {lastMsg.retrieved_chunks.map((c) => (
                  <div key={c.chunk_id} className="ref-card ref-card--debug">
                    <div className="ref-card-header">
                      <span className="ref-score">{c.score.toFixed(3)}</span>
                      <span className="ref-card-title">{c.title}</span>
                    </div>
                    <p className="ref-card-excerpt">{c.content}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>

      {showMemory && (
        <div className="memory-overlay" role="presentation" onMouseDown={() => setShowMemory(false)}>
          <section
            className="memory-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="会話記憶"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="memory-dialog-header">
              <div>
                <h2>会話記憶</h2>
                <p>PII 清洗後の preference と明示的 fact のみ保存します。</p>
              </div>
              <button type="button" className="memory-close" onClick={() => setShowMemory(false)}>×</button>
            </div>

            {memoryLoading ? (
              <p className="memory-empty">読み込み中…</p>
            ) : memoryError ? (
              <p className="memory-error">{memoryError}</p>
            ) : memoryItems.length === 0 ? (
              <p className="memory-empty">保存されている記憶はありません。</p>
            ) : (
              <div className="memory-list">
                {memoryItems.map((item) => (
                  <article key={item.id} className="memory-item">
                    <div className="memory-item-meta">
                      <span className={`memory-kind ${item.kind}`}>{item.kind}</span>
                      <div className="memory-item-actions">
                        <span>信頼度 {Math.round(item.confidence * 100)}%</span>
                        <button
                          type="button"
                          onClick={() => void removeMemoryItem(item.id)}
                          aria-label={`${item.key} を削除`}
                          title="この記憶だけを削除"
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    </div>
                    <strong>{item.key}</strong>
                    <p>{item.value}</p>
                    <small>有効期限 {new Date(item.expires_at).toLocaleDateString("ja-JP")}</small>
                  </article>
                ))}
              </div>
            )}

            <div className="memory-dialog-actions">
              <button type="button" className="memory-clear" onClick={clearAllMemory} disabled={memoryLoading || memoryItems.length === 0}>
                すべての記憶を削除
              </button>
              <button type="button" className="memory-done" onClick={() => setShowMemory(false)}>閉じる</button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
