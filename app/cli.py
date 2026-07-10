import argparse

from app.config import DEFAULT_RETRIEVAL_MODE, RETRIEVAL_MODES
from app.rag.answer_service import answer_question
from app.rag.ingest_service import ingest_documents
from app.rag.sync_service import delete_document, list_documents, sync_documents


def print_answer_result(result):
    answer = result["answer"]
    sources = result["sources"]
    mode = result.get("mode", DEFAULT_RETRIEVAL_MODE)

    print("\n========== 답변 ==========\n")
    print(f"[검색 모드: {mode}]")
    print()
    print(answer)

    print("\n========== 검색된 근거 ==========\n")

    if not sources:
        print("관련 기준을 통과한 문서가 없어.")
        return

    for i, item in enumerate(sources, start=1):
        page_text = f", page {item['page']}" if item["page"] != "" else ""

        print(f"[{i}] {item['source']}{page_text}, chunk {item['chunk_index']}")
        print(f"거리값: {item['distance']}")
        print(item["text"][:300] + "...")
        print()


def main():
    parser = argparse.ArgumentParser(description="Local RAG Assistant MVP")

    parser.add_argument(
        "--ingest",
        action="store_true",
        help="documents 폴더의 문서를 벡터 DB에 저장",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="기존 ChromaDB 컬렉션 삭제 후 다시 저장",
    )

    parser.add_argument(
        "--sync",
        action="store_true",
        help="documents 폴더와 ChromaDB 동기화",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="ChromaDB에 저장된 문서 목록 보기",
    )

    parser.add_argument(
        "--delete",
        type=str,
        help="특정 문서를 ChromaDB에서 삭제",
    )

    parser.add_argument(
        "--ask",
        type=str,
        help="문서 기반 질문",
    )

    parser.add_argument(
        "--mode",
        choices=list(RETRIEVAL_MODES.keys()),
        default=DEFAULT_RETRIEVAL_MODE,
        help="검색 모드 선택: fast, balanced, deep",
    )

    args = parser.parse_args()

    if args.sync:
        sync_documents()
        return

    if args.list:
        list_documents()
        return

    if args.delete:
        delete_document(args.delete)
        return

    if args.ingest:
        ingest_documents(reset=args.reset)
        return

    if args.ask:
        result = answer_question(args.ask, mode=args.mode)
        print_answer_result(result)
        return

    print("사용법:")
    print("1. 문서 저장: python local_rag.py --ingest")
    print("2. 초기화 후 저장: python local_rag.py --ingest --reset")
    print("3. 문서 동기화: python local_rag.py --sync")
    print("4. 문서 목록: python local_rag.py --list")
    print('5. 문서 삭제: python local_rag.py --delete "test.txt"')
    print('6. 빠른 질문: python local_rag.py --ask "질문" --mode fast')
    print('7. 균형 질문: python local_rag.py --ask "질문" --mode balanced')
    print('8. 깊은 질문: python local_rag.py --ask "질문" --mode deep')