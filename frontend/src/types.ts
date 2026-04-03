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

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  latency_ms: number;
  rewritten_query: string;
  token_usage: TokenUsage;
}

export interface Message {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  latency_ms: number;
  rewritten_query: string;
  token_usage: TokenUsage;
  timestamp: Date;
}

