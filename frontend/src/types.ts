// バックエンドの Pydantic スキーマと対応する API 境界の型。
export interface Citation {
  title: string;
  chunk_id: string;
  content: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  title: string;
  score: number;
  content: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface MemoryUsage {
  enabled: boolean;
  context_items: number;
  stored_items: number;
  masked_pii: string[];
  dropped_items: number;
  summary_used: boolean;
  summary_stored: boolean;
}

export interface GenerationMetrics {
  // Ollama の各段階を分離し、モデル起動と生成処理の遅延を切り分ける。
  context_chunks: number;
  context_characters: number;
  prompt_characters: number;
  model_load_ms: number;
  prompt_eval_ms: number;
  generation_ms: number;
  ollama_total_ms: number;
  prompt_tokens_per_second: number;
  generation_tokens_per_second: number;
  done_reason: string;
  fallback_reason: string;
  evidence_completion_used: boolean;
}

export interface MemoryItem {
  // 長期 preference/fact と、会話単位の短期 summary だけを表示する。
  id: string;
  conversation_id: string;
  kind: "preference" | "fact" | "summary";
  key: string;
  value: string;
  confidence: number;
  source: string;
  created_at: string;
  updated_at: string;
  expires_at: string;
}

export interface MemoryListResponse {
  enabled: boolean;
  client_id: string;
  total: number;
  items: MemoryItem[];
}

export interface ChatResponse {
  request_id: string;
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  latency_ms: number;
  rewritten_query: string;
  token_usage: TokenUsage;
  rag_mode: string;
  model: string;
  fallback_used: boolean;
  sanitized_question: string;
  memory_usage: MemoryUsage;
  generation_metrics: GenerationMetrics;
}

export interface Message {
  // API 応答に、画面表示とローカル履歴に必要な情報を加えた UI モデル。
  id: string;
  request_id?: string;
  question: string;
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  latency_ms: number;
  rewritten_query: string;
  token_usage: TokenUsage;
  rag_mode?: string;
  model?: string;
  fallback_used?: boolean;
  sanitized_question?: string;
  memory_usage?: MemoryUsage;
  generation_metrics?: GenerationMetrics;
  feedback?: "helpful" | "unhelpful";
  timestamp: Date;
}
