"""Ollama のローカル API を使って、検索根拠に限定した回答を生成する。"""

import re
from functools import lru_cache
from pathlib import Path

import httpx

from app.models.chat import GenerationMetrics, TokenUsage
from app.services.config import get_settings

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_PATHS = {
    "": PROMPT_DIR / "local_llm_rag_prompt.txt",
    "日本語": PROMPT_DIR / "local_llm_rag_prompt.txt",
    "中文": PROMPT_DIR / "local_llm_rag_prompt_zh.txt",
    "English": PROMPT_DIR / "local_llm_rag_prompt_en.txt",
}
BRACKET_PATTERN = re.compile(r"\[([^\]]+)\]")
SOURCE_ID_PATTERN = re.compile(r"\bS(\d+)\b")


class OllamaError(RuntimeError):
    """Ollama 呼び出しを安全にフォールバックできる共通例外。"""


class OllamaUnavailableError(OllamaError):
    """Ollama API または指定モデルを利用できない。"""


class OllamaInvalidResponseError(OllamaError):
    """生成結果が空、または根拠の引用条件を満たしていない。"""


def generate_grounded_answer(
    question: str, chunks: list[dict], *, memory_context: str = ""
) -> tuple[str, TokenUsage, GenerationMetrics]:
    """許可済み記憶と番号付き根拠だけを渡し、生成結果と性能指標を返す。"""
    settings = get_settings()
    response_language = _extract_response_language(memory_context)
    preference_instruction = _build_preference_instruction(memory_context)
    if preference_instruction:
        system_prompt = (
            f"{_load_system_prompt(response_language)}\n\n{preference_instruction}"
        )
    else:
        system_prompt = _load_system_prompt(response_language)
    messages = [{"role": "system", "content": system_prompt}]
    messages.append(
        {
            "role": "user",
            "content": _build_user_prompt(
                question=question,
                chunks=chunks,
                memory_context=memory_context,
                response_language=response_language,
            ),
        }
    )
    # 非ストリーミング応答にして、回答検証後にだけ呼び出し元へ返す。
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "keep_alive": settings.ollama_keep_alive,
        "options": {
            "temperature": settings.ollama_temperature,
            "num_ctx": settings.ollama_context_length,
            "num_predict": settings.ollama_max_tokens,
            "num_thread": settings.ollama_num_threads,
            "num_batch": settings.ollama_num_batch,
        },
    }

    try:
        timeout = httpx.Timeout(settings.ollama_timeout_seconds, connect=5.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        raise OllamaUnavailableError(
            f"Ollama API returned HTTP {exc.response.status_code}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaUnavailableError("Ollama API request failed") from exc

    # モデルごとの引用表記揺れを正規化してから、存在する S 番号だけか検証する。
    answer = _normalize_source_markers(
        str(body.get("message", {}).get("content", "")).strip()
    )
    _validate_answer(answer, source_count=len(chunks))

    prompt_tokens = int(body.get("prompt_eval_count") or 0)
    completion_tokens = int(body.get("eval_count") or 0)
    prompt_eval_seconds = _nanoseconds_to_seconds(body.get("prompt_eval_duration"))
    generation_seconds = _nanoseconds_to_seconds(body.get("eval_duration"))
    usage = TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    metrics = GenerationMetrics(
        context_chunks=len(chunks),
        context_characters=sum(len(chunk["content"]) for chunk in chunks),
        prompt_characters=sum(len(message["content"]) for message in messages),
        model_load_ms=_nanoseconds_to_milliseconds(body.get("load_duration")),
        prompt_eval_ms=round(prompt_eval_seconds * 1000, 3),
        generation_ms=round(generation_seconds * 1000, 3),
        ollama_total_ms=_nanoseconds_to_milliseconds(body.get("total_duration")),
        prompt_tokens_per_second=_safe_rate(prompt_tokens, prompt_eval_seconds),
        generation_tokens_per_second=_safe_rate(
            completion_tokens, generation_seconds
        ),
        done_reason=str(body.get("done_reason") or ""),
    )
    return answer, usage, metrics


@lru_cache
def _load_system_prompt(response_language: str = "") -> str:
    prompt_path = PROMPT_PATHS.get(response_language, PROMPT_PATHS[""])
    return prompt_path.read_text(encoding="utf-8").strip()


def _build_user_prompt(
    question: str,
    chunks: list[dict],
    memory_context: str = "",
    response_language: str = "",
) -> str:
    """根拠境界を XML 風タグで明示し、質問や記憶との混同を防ぐ。"""
    sources: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        sources.append(
            "\n".join(
                [
                    f"<source id=\"S{index}\">",
                    chunk["content"],
                    "</source>",
                ]
            )
        )
    context = "\n\n".join(sources)
    preference_instruction = _build_preference_instruction(memory_context)
    final_instruction = (
        f"\n\n{preference_instruction}" if preference_instruction else ""
    )
    labels = {
        "中文": ("问题", "经过治理的会话记忆", "检索资料", "只输出最终答案。"),
        "English": (
            "Question",
            "Governed conversation memory",
            "Retrieved sources",
            "Output only the final answer.",
        ),
    }.get(
        response_language,
        ("質問", "治理済み会話記憶", "検索で取得した資料", "回答だけを出力してください。"),
    )
    memory_block = (
        f"\n\n{labels[1]}:\n{memory_context}" if memory_context else ""
    )
    return (
        f"{labels[2]}:\n{context}"
        f"{memory_block}\n\n"
        f"{labels[0]}:\n{question}\n\n"
        f"{labels[3]}{final_instruction}"
    )


def _build_preference_instruction(memory_context: str) -> str:
    """治理済み記憶のうち許可リストにある表示設定だけを指示へ変換する。"""
    instructions: list[str] = []
    language_match = re.search(
        r"^\[preference\]\s+response_language=(中文|日本語|English)\s+",
        memory_context,
        re.MULTILINE,
    )
    language = language_match.group(1) if language_match else ""
    if language:
        language_rules = {
            "中文": "回答本文必须使用简体中文。金融术语代码和 [S#] 引用可以保留原文。",
            "日本語": "回答本文は必ず日本語で記述してください。",
            "English": "Write the answer body in English.",
        }
        instructions.append(language_rules[language])

    style_match = re.search(
        r"^\[preference\]\s+answer_style=(concise|detailed)\s+",
        memory_context,
        re.MULTILINE,
    )
    if style_match:
        if style_match.group(1) == "concise":
            concise_rules = {
                "中文": "请只保留结论和重要条件，简洁回答。",
                "日本語": "結論と重要条件だけを簡潔に回答してください。",
                "English": "Answer concisely with only the conclusion and key conditions.",
                "": "結論と重要条件だけを簡潔に回答してください。",
            }
            instructions.append(concise_rules[language])
        else:
            detailed_rules = {
                "中文": "在保留依据的前提下，详细说明步骤和注意事项。",
                "日本語": "根拠を保ったまま、手順と注意点を詳しく回答してください。",
                "English": "Explain the steps and cautions in detail while preserving the evidence.",
                "": "根拠を保ったまま、手順と注意点を詳しく回答してください。",
            }
            instructions.append(detailed_rules[language])

    if not instructions:
        return ""
    header = {
        "中文": "回答格式的强制要求:",
        "English": "Mandatory response format:",
    }.get(language, "回答形式の必須指定:")
    return f"{header}\n- " + "\n- ".join(instructions)


def _extract_response_language(memory_context: str) -> str:
    match = re.search(
        r"^\[preference\]\s+response_language=(中文|日本語|English)\s+",
        memory_context,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def _validate_answer(answer: str, source_count: int) -> None:
    """空回答、引用なし、存在しない引用番号を生成失敗として扱う。"""
    if not answer:
        raise OllamaInvalidResponseError("Ollama returned an empty answer")
    markers = {
        int(value)
        for bracket in BRACKET_PATTERN.findall(answer)
        for value in SOURCE_ID_PATTERN.findall(bracket)
    }
    if not markers:
        raise OllamaInvalidResponseError("The answer does not contain a source marker")
    if any(marker < 1 or marker > source_count for marker in markers):
        raise OllamaInvalidResponseError("The answer contains an invalid source marker")


def _normalize_source_markers(answer: str) -> str:
    """Gemma が生成する [S1, S2] を API 標準の [S1][S2] に揃える。"""

    def replace(match: re.Match[str]) -> str:
        source_ids = SOURCE_ID_PATTERN.findall(match.group(1))
        if not source_ids:
            return match.group(0)
        return "".join(f"[S{source_id}]" for source_id in source_ids)

    return BRACKET_PATTERN.sub(replace, answer)


def _nanoseconds_to_seconds(value: object) -> float:
    try:
        return float(value or 0) / 1_000_000_000
    except (TypeError, ValueError):
        return 0.0


def _nanoseconds_to_milliseconds(value: object) -> float:
    return round(_nanoseconds_to_seconds(value) * 1000, 3)


def _safe_rate(tokens: int, seconds: float) -> float:
    return round(tokens / seconds, 3) if tokens > 0 and seconds > 0 else 0.0
