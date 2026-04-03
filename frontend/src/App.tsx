import { KeyboardEvent, useEffect, useRef, useState } from "react";

import { ApiError, sendQuestion } from "./api";
import type { Message } from "./types";

// ── 会話セッション型 ────────────────────────────────────────
interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string; // ISO string for localStorage serialization
}

const STORAGE_KEY = "rag_conversations";
const MAX_HISTORY = 30;

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    return parsed.map((c) => ({
      ...c,
      messages: c.messages.map((m) => ({ ...m, timestamp: new Date(m.timestamp) })),
    }));
  } catch {
    return [];
  }
}

function saveConversations(convs: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs.slice(0, MAX_HISTORY)));
  } catch {
    // ignore quota errors
  }
}

const SAMPLE_QUESTIONS = [
  "パスワードリセットの有効期限は何分ですか？",
  "P1 障害が発生した場合の目標復旧時間（RTO）は？",
  "スタンダードプランのスカウト送信上限は月何件ですか？",
  "面接をキャンセルする場合、どのような手順が必要ですか？",
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
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showDev, setShowDev] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // refs to avoid stale closures in async callbacks
  const activeConvIdRef = useRef<string | null>(null);
  activeConvIdRef.current = activeConvId;
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  // tracks the question currently being fetched (question state is cleared before request)
  const pendingQuestionRef = useRef("");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit() {
    const q = question.trim();
    if (!q || loading) return;
    pendingQuestionRef.current = q;
    setQuestion("");
    setError("");
    setLoading(true);
    textareaRef.current?.focus();
    try {
      const res = await sendQuestion(q);
      const newMsg = {
        id: generateId(),
        question: q,
        answer: res.answer,
        citations: res.citations,
        retrieved_chunks: res.retrieved_chunks,
        latency_ms: res.latency_ms,
        rewritten_query: res.rewritten_query,
        token_usage: res.token_usage,
        timestamp: new Date(),
      };

      // Compute updated messages using ref (safe against stale closure)
      const updatedMsgs = [...messagesRef.current, newMsg];
      setMessages(updatedMsgs);

      // Persist conversation — no nested setState calls
      const title =
        updatedMsgs[0].question.slice(0, 26) +
        (updatedMsgs[0].question.length > 26 ? "…" : "");
      const currentId = activeConvIdRef.current;

      if (currentId) {
        setConversations((prev) => {
          const updated = prev.map((c) =>
            c.id === currentId ? { ...c, messages: updatedMsgs } : c
          );
          saveConversations(updated);
          return updated;
        });
      } else {
        const newId = generateId();
        activeConvIdRef.current = newId;
        setActiveConvId(newId);
        setConversations((prev) => {
          const updated = [
            { id: newId, title, messages: updatedMsgs, createdAt: new Date().toISOString() },
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
    e.stopPropagation();
    setConversations((prev) => {
      const updated = prev.filter((c) => c.id !== convId);
      saveConversations(updated);
      return updated;
    });
    if (activeConvId === convId) {
      startNewConversation();
    }
  }

  // Group conversations by date label
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
          <span className="navbar-title">ナレッジアシスタント</span>
        </div>
        <div className="navbar-right">
          <span className="navbar-badge">Azure OpenAI × AI Search</span>
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
                社内ナレッジベースに登録された情報をもとに回答します。<br />
                業務ルール・手順・仕様・FAQ など幅広くサポートします。
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

                    {/* 開発者情報（Dev モード時のみ） */}
                    {showDev && (
                      <details className="dev-panel">
                        <summary>開発者情報</summary>
                        <dl className="dev-dl">
                          <dt>検索クエリ</dt>
                          <dd>{msg.rewritten_query || "—"}</dd>
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
            <p className="input-hint">Shift + Enter で改行</p>
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
    </div>
  );
}
