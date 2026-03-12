"""
Pydantic 모델 — API 요청/응답 스키마 정의
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class QuestionRequest(BaseModel):
    """사용자 질문 요청"""
    question: str = Field(..., min_length=1, max_length=500, description="사용자 질문")


class SourceInfo(BaseModel):
    """출처 문서 정보"""
    title: str
    page: Optional[int] = None
    category: str = ""
    date: str = ""


class AnswerResponse(BaseModel):
    """RAG 답변 응답"""
    answer: str
    sources: List[SourceInfo]
    question: str


class HealthResponse(BaseModel):
    """서버 상태 응답"""
    status: str
    indexed_chunks: int
    version: str


class SuggestedQuestion(BaseModel):
    """추천 질문"""
    text: str
    category: str


class SuggestionsResponse(BaseModel):
    """추천 질문 목록"""
    suggestions: List[SuggestedQuestion]
