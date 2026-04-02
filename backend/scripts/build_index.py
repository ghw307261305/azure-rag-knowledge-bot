"""
ナレッジベース インデクシングスクリプト
docs/knowledge/ のMarkdownファイルを読み込み、
チャンクに分割してAzure AI Searchに登録する

使い方:
  cd backend
  python scripts/build_index.py           # 差分更新
  python scripts/build_index.py --rebuild  # 全件再構築
"""
import argparse
import logging
import sys
import time
from pathlib import Path

# backend/ をモジュール検索パスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.services.chunking_service import load_and_chunk
from app.services.openai_service import get_embedding
from app.services.search_service import create_index, delete_index, upload_documents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "docs" / "knowledge"


def build_index(rebuild: bool = False) -> None:
    logger.info("=" * 50)
    logger.info("Azure RAG Knowledge Bot - Index Builder")
    logger.info("=" * 50)

    # 1. インデックス準備
    if rebuild:
        logger.info("【再構築モード】既存インデックスを削除します...")
        try:
            delete_index()
        except Exception:
            logger.info("インデックスが存在しないため削除をスキップ")

    logger.info("インデックスを作成/更新中...")
    create_index()

    # 2. Markdownファイルを収集
    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not md_files:
        logger.error(f"知識ドキュメントが見つかりません: {KNOWLEDGE_DIR}")
        sys.exit(1)

    logger.info(f"対象ファイル数: {len(md_files)}")

    # 3. チャンク化 → Embedding → 登録
    all_documents = []
    total_chunks = 0
    failed_files = []

    for file_path in md_files:
        logger.info(f"処理中: {file_path.name}")
        try:
            chunks = load_and_chunk(file_path)
            logger.info(f"  → {len(chunks)} チャンク生成")

            for chunk in chunks:
                try:
                    vector = get_embedding(chunk.content)
                    doc = {
                        "chunk_id": chunk.chunk_id,
                        "title": chunk.title,
                        "section": chunk.section,
                        "source": chunk.source,
                        "content": chunk.content,
                        "content_vector": vector,
                    }
                    all_documents.append(doc)
                    total_chunks += 1
                    # レート制限対策
                    time.sleep(0.1)

                except Exception as e:
                    logger.warning(f"  Embedding失敗 [{chunk.chunk_id}]: {e}")

        except Exception as e:
            logger.error(f"  ファイル処理失敗 [{file_path.name}]: {e}")
            failed_files.append(file_path.name)

    # 4. Azure AI Search に一括登録
    if all_documents:
        logger.info(f"Azure AI Search に {len(all_documents)} チャンクを登録中...")
        upload_documents(all_documents)

    # 5. 結果レポート
    logger.info("=" * 50)
    logger.info(f"完了: {total_chunks} チャンク登録成功")
    if failed_files:
        logger.warning(f"失敗ファイル ({len(failed_files)}件): {failed_files}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ナレッジベースインデックス構築")
    parser.add_argument("--rebuild", action="store_true", help="インデックスを全件再構築")
    args = parser.parse_args()
    build_index(rebuild=args.rebuild)
