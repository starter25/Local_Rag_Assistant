# Local RAG Assistant

Ollama 기반 로컬 LLM과 ChromaDB를 활용한 문서 기반 RAG Assistant 프로젝트입니다.

사용자가 PDF, TXT, MD, DOCX 문서를 업로드하면 문서를 텍스트로 추출하고 chunk 단위로 분리한 뒤, 임베딩하여 ChromaDB에 저장합니다. 이후 사용자의 질문이 들어오면 질문을 벡터화하고 관련 문서 chunk를 검색한 뒤, 검색된 근거를 바탕으로 로컬 LLM이 답변을 생성합니다.

외부 API를 사용하지 않고 로컬 환경에서 Ollama 모델과 벡터 DB를 실행하는 것을 목표로 합니다.

---

## 1. 프로젝트 목적

기존 생성형 AI는 토큰 비용, 외부 서버 전송, 개인정보 노출, 인터넷 연결 의존성 등의 한계가 있습니다.

이 프로젝트는 이러한 문제를 줄이기 위해 다음 목표로 개발되었습니다.

- 사용자가 직접 업로드한 문서를 기반으로 답변
- 문서를 외부 서버로 보내지 않고 로컬에서 처리
- Ollama 기반 로컬 LLM 사용
- ChromaDB 기반 벡터 검색
- 문서 근거 기반 답변 생성
- 문서에 없는 내용은 추측하지 않고 거부
- Fast / Balanced / Deep 검색 모드 제공
- 웹 UI를 통한 문서 업로드, 질문, 삭제 기능 제공

---

## 2. 주요 기능

### 문서 업로드 및 벡터화

지원 문서 형식:

- PDF
- TXT
- MD
- DOCX

업로드된 문서는 `storage/documents` 폴더에 저장되며, 문서 내용은 chunk 단위로 분리되어 임베딩된 후 `storage/chroma_db`에 저장됩니다.

### 문서 기반 질문 답변

사용자의 질문이 들어오면 다음 과정으로 답변을 생성합니다.

```text
사용자 질문
→ query rewrite
→ 질문 embedding 생성
→ ChromaDB에서 관련 chunk 검색
→ 검색된 chunk를 prompt에 삽입
→ Ollama LLM 답변 생성
→ 답변과 참고 근거 반환
```

---

## 3. 권장 실행 환경

이 프로젝트의 기준 Python 버전은 **Python 3.11**입니다.

- 권장: Python 3.11.x
- 호환 가능: Python 3.12.x
- 비권장: Python 3.13.x를 기본 런타임으로 사용하는 것

현재 기능만 보면 Python 3.12도 충분히 동작할 가능성이 높지만, 추후 `torch`, `sentence-transformers`, OCR, reranker, hybrid search 같은 RAG 고도화 패키지를 붙일 때는 Python 3.11이 가장 무난합니다.

### Windows 가상환경 생성

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

기존 `venv`가 다른 Python 경로를 바라보고 깨져 있다면, 새 가상환경을 만든 뒤 다시 의존성을 설치해야 합니다.

### 서버 실행

Ollama가 실행 중이고 필요한 모델이 받아져 있어야 합니다.

```powershell
ollama list
uvicorn app.main:app --reload
```

브라우저에서 `http://localhost:8000`으로 접속하면 프론트엔드 화면을 사용할 수 있습니다.

### Windows 런처 EXE 빌드

더블클릭으로 서버를 실행하고 브라우저를 여는 런처 EXE를 만들 수 있습니다.

```powershell
pip install -r requirements-dev.txt
.\tools\build_launcher.ps1
```

생성 위치:

```text
dist\LocalRAGAssistant.exe
```

런처 EXE는 프로젝트 폴더의 `venv`, `app`, `frontend`, `storage`를 사용합니다. Ollama는 별도 프로그램이므로 설치되어 있어야 하며, 실행 중이 아니면 런처가 가능한 경우 `ollama serve`를 시도합니다.

바탕화면에서 실행하고 싶다면 EXE 파일을 직접 복사하지 말고 바로가기를 만드세요.

```powershell
.\tools\create_desktop_shortcut.ps1
```

바로가기는 `dist\LocalRAGAssistant.exe`를 가리키고, 작업 폴더는 프로젝트 루트로 설정됩니다. 이렇게 해야 런처가 `venv`, `app`, `frontend`, `storage`를 안정적으로 찾습니다.
