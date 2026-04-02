"""
Azure OpenAI サービス
Embedding生成・クエリ書き換え・チャット回答生成を担当する
"""
import logging
from typing import List

from openai import AzureOpenAI

from app.services.config import get_settings

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = (
    "以下のユーザー質問を、ドキュメント検索に適した簡潔な検索クエリに書き換えてください。"
    "重要なキーワードと概念を保持し、検索に不要な語句（「〜ですか」「〜はどうすれば」など）を除いてください。"
    "検索クエリのみを返してください。説明は不要です。"
)


def _get_client() -> AzureOpenAI:
    s = get_settings()
    return AzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        api_version="2024-06-01",
    )


def rewrite_query(question: str) -> str:
    """
    ユーザーの質問を検索に適したクエリに書き換える。
    失敗した場合は元の質問をそのまま返す（フォールバック）。
    """
    s = get_settings()
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=s.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": _REWRITE_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=100,
        )
        rewritten = response.choices[0].message.content or question
        logger.info(f"クエリ書き換え: '{question[:40]}' → '{rewritten.strip()[:40]}'")
        return rewritten.strip()
    except Exception as e:
        logger.warning(f"クエリ書き換え失敗（元クエリを使用）: {e}")
        return question


def get_embedding(text: str) -> List[float]:
    """テキストのEmbeddingベクトルを生成する（3072次元: text-embedding-3-large）"""
    s = get_settings()
    client = _get_client()
    response = client.embeddings.create(
        input=text,
        model=s.azure_openai_embedding_deployment,
    )
    return response.data[0].embedding


def generate_answer(question: str, context: str) -> tuple[str, dict]:
    """
    検索コンテキストを使ってRAG回答を生成する。
    Returns: (answer_text, usage_dict)
    """
    s = get_settings()
    client = _get_client()

    system_prompt = _load_system_prompt()
    user_message = f"【質問】\n{question}\n\n【参考資料】\n{context}"

    response = client.chat.completions.create(
        model=s.azure_openai_chat_deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
        max_tokens=1000,
    )

    answer = response.choices[0].message.content or ""
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return answer, usage


def _load_system_prompt() -> str:
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent / "prompts" / "rag_prompt.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "あなたは企業内部の知識ベースアシスタントです。"
        "提供された参考資料のみに基づいて回答してください。"
        "資料に記載がない場合は「現在の資料では確認できません」と答えてください。"
    )
