# Local RAG Assistant

Ollama와 ChromaDB를 사용하는 로컬 RAG Assistant입니다. 문서, 코드, CSV, XLSX 파일을 업로드하면 텍스트로 변환하고, chunk로 나눈 뒤 embedding을 생성해 ChromaDB에 저장합니다. 질문할 때는 관련 chunk를 검색해 Ollama 모델로 답변을 생성합니다.

외부 API로 문서를 보내지 않고 로컬 환경에서 동작하는 것을 목표로 합니다.

## 주요 기능

- 로컬 Ollama chat 모델 선택
- 추천 Ollama 모델 설치 요청 및 진행률 표시
- Documents 모드: 업로드한 문서 근거 안에서만 답변
- Hybrid 모드: 문서 근거를 우선으로 쓰고 AI 해석/조언을 분리
- General AI 모드: 문서 검색 없이 일반 질문/코딩 질문 답변
- 채팅 저장, 불러오기, 삭제, 이전 대화 기반 후속 질문
- 문서 업로드, 동기화, 삭제
- 작업 진행 상태 표시: 질문 준비, 문서 검색, 답변 생성, 문서 처리 등
- 근거 품질 표시: 강함, 보통, 약함, 없음

## 지원 파일 형식

현재 RAG 업로드/동기화 대상:

- 문서: `.pdf`, `.txt`, `.md`, `.docx`
- 코드: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.html`, `.css`, `.json`, `.yaml`, `.yml`, `.java`, `.cpp`, `.c`, `.cs`, `.go`, `.rs`, `.php`, `.sql`, `.sh`, `.ps1`, `.bat`
- 표: `.csv`, `.xlsx`

이미지와 스캔 PDF OCR은 아직 포함되어 있지 않습니다. 이미지 기반 파일은 OCR 또는 비전 모델로 텍스트화하는 별도 단계가 필요합니다.

## 전체 처리 흐름

```text
파일 업로드
→ 확장자 검증
→ 파일 종류별 텍스트 변환
→ chunk 분할
→ Ollama embedding 생성
→ ChromaDB 저장
→ 질문 입력
→ 질문 rewrite
→ 질문 embedding 생성
→ ChromaDB 검색
→ prompt 구성
→ Ollama 답변 생성
→ 답변, 출처, 근거 품질 표시
```

## 기능별 코드 지도

### 1. API 진입점

`app/main.py`

- FastAPI 앱의 중심입니다.
- `/models`, `/models/pull`로 Ollama 모델 목록과 설치 job을 관리합니다.
- `/ask/jobs`로 답변 생성 job을 시작하고 `/ask/jobs/{job_id}`로 진행 상태를 조회합니다.
- `/documents/upload`, `/documents/sync`, `/documents/jobs/{job_id}`로 문서 처리 job을 관리합니다.
- `/chats` 계열 API로 채팅 저장/수정/삭제를 제공합니다.

### 2. 파일 인식과 텍스트 변환

`app/rag/document_loader.py`

- 업로드된 파일 확장자에 따라 로더를 선택합니다.
- PDF는 페이지 단위 텍스트를 추출합니다.
- DOCX는 문단과 표를 함께 텍스트로 변환합니다.
- 코드 파일은 파일명, 파일 타입, 언어 정보를 붙여 원문 코드와 함께 저장합니다.
- CSV/XLSX는 행을 `컬럼=값` 형태의 텍스트로 바꿉니다.

### 3. 벡터화와 저장

`app/rag/ingest_service.py`

- 파일 해시를 계산해 문서 변경 여부를 판단할 수 있게 합니다.
- 텍스트를 chunk로 나누고 embedding을 생성합니다.
- ChromaDB에 chunk, embedding, source, page, file_hash 메타데이터를 저장합니다.

`app/rag/splitter.py`

- 긴 텍스트를 overlap이 있는 chunk로 분리합니다.

`app/rag/vector_db.py`

- ChromaDB collection을 열고 문서별 chunk 수를 집계합니다.
- 특정 문서의 chunk 삭제도 담당합니다.

### 4. 검색

`app/rag/retriever.py`

- 사용자 질문을 embedding으로 바꿔 ChromaDB에서 관련 chunk를 찾습니다.
- Fast/Balanced/Deep 모드별로 candidate 수와 distance threshold가 달라집니다.
- 여러 검색어 후보에서 같은 chunk가 나오면 더 가까운 distance만 남깁니다.

`app/rag/query_rewriter.py`

- Ollama를 사용해 질문을 RAG 검색에 더 적합한 검색어 후보로 확장합니다.
- rewrite가 실패해도 원래 질문으로 검색이 계속됩니다.

`app/rag/retrieval_settings.py`

- Fast/Balanced/Deep 검색 모드 설정을 제공합니다.

### 5. 답변 생성

`app/rag/answer_service.py`

- General, Documents, Hybrid 모드를 분기하는 핵심 서비스입니다.
- Documents 모드는 문서 근거 밖 추론을 막는 strict RAG prompt를 사용합니다.
- Hybrid 모드는 문서 근거와 AI 해석/조언을 분리하도록 prompt를 구성합니다.
- General AI 모드는 문서 검색 없이 선택한 Ollama 모델에 직접 질문합니다.

`app/rag/prompt_builder.py`

- 검색된 chunk와 이전 대화를 prompt에 넣습니다.
- strict RAG prompt와 Hybrid prompt를 각각 생성합니다.

`app/rag/ollama_client.py`

- Ollama 연결 확인, 모델 목록 조회, embedding 생성, chat 답변 생성을 담당합니다.

`app/rag/model_profiles.py`

- 모델별 system prompt, 생성 옵션, 추천 모델 정보를 관리합니다.
- DeepSeek 계열처럼 reasoning 흔적을 출력하기 쉬운 모델에는 별도 지침을 붙입니다.

`app/rag/answer_cleaner.py`

- `<think>` 블록 등 모델이 출력한 reasoning 흔적을 제거합니다.

`app/rag/source_quality.py`

- 검색된 chunk의 distance를 요약해 근거 품질을 계산합니다.

### 6. 작업 큐와 진행 상태

긴 작업은 UI를 멈추지 않도록 백그라운드 job으로 실행합니다.

`app/rag/ask_jobs.py`

- 답변 생성 job을 시작하고 진행 상태를 관리합니다.

`app/rag/document_jobs.py`

- 문서 업로드/동기화 job을 실행합니다.
- ChromaDB 쓰기 충돌을 피하기 위해 문서 처리 작업은 동시에 하나만 실행합니다.

`app/rag/model_pull.py`

- Ollama 모델 설치 job을 시작하고 stream 진행률을 저장합니다.

`app/rag/job_registry.py`

- 완료된 job 정리, 오래 멈춘 job 실패 처리, active job 수 계산을 공통으로 제공합니다.

### 7. 채팅 저장과 대화 기억

`app/chat_store.py`

- `storage/chats/chats.json`에 채팅 목록과 메시지를 저장합니다.
- 저장 파일이 없거나 깨졌을 때 빈 저장소로 복구합니다.

`app/rag/chat_context.py`

- 전체 대화 중 모델에 넘길 최근 메시지만 남깁니다.
- General, RAG, Hybrid, 검색용 질문마다 서로 다른 길이 제한을 적용합니다.

### 8. 프론트엔드

`frontend/index.html`

- 앱 화면 구조와 업로드 input 허용 확장자를 정의합니다.

`frontend/script.js`

- 모델 선택/설치, 채팅 저장, 문서 업로드/동기화, 질문 job polling, 답변 렌더링을 담당합니다.
- 작업 중 버튼 잠금으로 중복 실행을 막습니다.
- 답변마다 sources와 source quality 배지를 표시합니다.

`frontend/style.css`

- 사이드바, 채팅 화면, 모델 설치 카드, 문서 목록, 근거 품질 배지 스타일을 정의합니다.

## 실행 방법

Python 3.11 권장:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Ollama가 실행 중인지 확인:

```powershell
ollama list
```

개발 서버 실행:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

브라우저에서 접속:

```text
http://127.0.0.1:8000
```

## Tauri 데스크톱 개발 실행

```powershell
.\tools\run_tauri_dev.ps1
```

Windows MSI 빌드:

```powershell
.\tools\build_tauri_app.ps1
```

배포용 MSI를 만든 뒤 코드가 바뀌면 MSI에 자동 반영되지 않습니다. 변경사항을 배포하려면 다시 빌드해야 합니다.

## 테스트

문법 확인:

```powershell
venv\Scripts\python.exe -m compileall app tests
node --check frontend\script.js
```

단위 테스트:

```powershell
venv\Scripts\python.exe -m unittest discover -s tests
```

## 저장소 구조

```text
app/
  main.py                 FastAPI API 진입점
  chat_store.py           채팅 저장소
  rag/                    RAG 처리 로직
frontend/
  index.html              UI 구조
  script.js               UI 동작과 API 호출
  style.css               UI 스타일
storage/
  documents/              업로드 원본 파일
  chroma_db/              ChromaDB 영구 저장소
  chats/                  채팅 JSON 저장소
tools/
  run_tauri_dev.ps1       Tauri 개발 실행
  build_tauri_app.ps1     Tauri MSI 빌드
tests/
  test_*.py               핵심 기능 단위 테스트
```

`storage/`, `venv/`, `dist/`, `build/`, `desktop-runtime/`는 개발/실행 산출물이므로 Git에 올리지 않는 것이 기본입니다.
