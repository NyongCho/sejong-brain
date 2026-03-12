"""
FastAPI 백엔드 — SejongBrain API 서버
"""

import os
import sys

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.models import (
    QuestionRequest,
    AnswerResponse,
    HealthResponse,
    SourceInfo,
    SuggestionsResponse,
    SuggestedQuestion,
)
from backend.rag_engine import RAGEngine, create_engine_from_scratch

# ─── 앱 초기화 ─────────────────────────────────────────

app = FastAPI(
    title="SejongBrain API",
    description="세종대학교 AI 학사 정보 검색 서비스",
    version="0.1.0",
)

# CORS 설정 (로컬 개발 + 배포 호환)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RAG 엔진 (서버 시작 시 1회 로드)
engine: RAGEngine = None

# 추천 질문 목록
SUGGESTED_QUESTIONS = [
    SuggestedQuestion(text="수강신청은 최대 몇 학점까지 가능한가요?", category="수강"),
    SuggestedQuestion(text="장학금 기본이수학점은 몇 학점인가요?", category="장학"),
    SuggestedQuestion(text="직전 학기 성적이 좋으면 초과 학점 신청이 가능한가요?", category="수강"),
    SuggestedQuestion(text="수강신청 학점 미달 시 어떻게 되나요?", category="수강"),
    SuggestedQuestion(text="4학년 장학금 기준은 다른가요?", category="장학"),
    SuggestedQuestion(text="폐강된 과목은 어떻게 처리되나요?", category="수강"),
]


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 RAG 엔진을 초기화합니다."""
    global engine
    print("🧠 RAG 엔진 초기화 중...")

    engine = RAGEngine()
    try:
        engine.load_index()
    except FileNotFoundError:
        print("📦 기존 인덱스 없음 → 새로 생성합니다 (1~2분 소요)...")
        engine = create_engine_from_scratch()

    print("✅ SejongBrain 서버 준비 완료!")


# ─── API 엔드포인트 ────────────────────────────────────

@app.post("/api/ask", response_model=AnswerResponse)
async def ask_question(request: QuestionRequest):
    """RAG 기반 질문 응답"""
    if engine is None:
        raise HTTPException(status_code=503, detail="RAG 엔진 초기화 중입니다. 잠시 후 다시 시도해주세요.")

    try:
        result = engine.ask(request.question)

        sources = [
            SourceInfo(
                title=s.get("title", ""),
                page=s.get("page"),
                category=s.get("category", ""),
                date=s.get("date", ""),
            )
            for s in result.get("sources", [])
        ]

        return AnswerResponse(
            answer=result["answer"],
            sources=sources,
            question=result["question"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """서버 상태 확인"""
    chunk_count = 0
    if engine and engine.all_chunks:
        chunk_count = len(engine.all_chunks)

    return HealthResponse(
        status="ok" if engine else "initializing",
        indexed_chunks=chunk_count,
        version="0.1.0",
    )


@app.get("/api/suggestions", response_model=SuggestionsResponse)
async def get_suggestions():
    """추천 질문 목록 반환"""
    return SuggestionsResponse(suggestions=SUGGESTED_QUESTIONS)


# ─── 프론트엔드 정적 파일 서빙 ─────────────────────────

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_frontend():
        """메인 페이지 서빙"""
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ─── 실행 ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
