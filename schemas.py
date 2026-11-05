"""요청 모델 — 서버가 들어오는 값을 먼저 검사해요(Pydantic)."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DataItem(BaseModel):
    """데이터 1건 — 서버가 들어오는 값을 먼저 검사해요(Pydantic)."""
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="날짜 (YYYY-MM-DD)", examples=["2026-09-09"])
    value: float = Field(ge=0, le=100, description="검색 관심도 상대지수 (0~100)", examples=[35.8])
    memo: str = Field(
        min_length=1, max_length=30,
        pattern=r"^[가-힣A-Za-z0-9][가-힣A-Za-z0-9 /·_\-]*$",
        description="업종 이름 — 한글·영문·숫자·공백·/ 만 허용(첫 글자는 글자나 숫자)",
        examples=["카페"],
    )

    @field_validator("date")
    @classmethod
    def date_must_exist(cls, v):
        datetime.strptime(v, "%Y-%m-%d")      # 2026-13-45 같은 없는 날짜는 여기서 걸러져요
        return v


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000, description="질문 (1~1,000자)")
    conversation_id: str | None = Field(default=None, max_length=100)


class ConversationCreate(BaseModel):
    messages: list = Field(max_length=200)  # [{"role": "...", "content": "..."} , ...] (최대 200개)


class ContentPlanRequest(BaseModel):
    industry: str = Field(min_length=1, max_length=30)          # 카페 / 미용/뷰티 / 미용의료 (memo 값, 부분입력 OK)
    season: str | None = Field(default=None, max_length=30)     # 예: 할로윈, 연말, 봄 (선택)
    channel: str | None = Field(default=None, max_length=30)    # 예: 인스타, 블로그, 숏폼 (선택)
    product: str | None = Field(default=None, max_length=100)   # 내 상품/서비스 (선택) — 롱테일 키워드·콘텐츠를 여기에 맞춤
