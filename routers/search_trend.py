"""네이버 검색관심도(3년) API — 발행 타이밍 근거 (NAVER API HUB 데이터랩 검색어트렌드 연동)."""
from fastapi import APIRouter, HTTPException

from naver_client import NaverError
from services.search_trend import load_timing_summary, refresh_search_trend

router = APIRouter()


@router.post("/api/search-trend/refresh")
def refresh():
    """네이버에서 최근 3년 일간 검색관심도를 받아 저장하고, 발행 타이밍 요약을 새로 계산해요.
    (상대지수라서 기간을 바꾸면 모든 숫자가 다시 계산돼요 → 항상 전체 기간을 통째로 받아요)"""
    try:
        return refresh_search_trend()
    except NaverError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/search-trend/summary")
def summary():
    """보관해 둔 발행 타이밍 요약(요일·월·행사 전후)을 보여줘요."""
    s = load_timing_summary()
    if s is None:
        return {"message": "아직 타이밍 요약이 없어요. POST /api/search-trend/refresh 를 먼저 실행해 주세요"}
    return s
