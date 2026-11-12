"""창원시 인구 API — KOSIS(국가통계포털) 공공데이터 연동."""
from fastapi import APIRouter, HTTPException

from errors import server_error
from kosis_client import KosisError
from services.population import build_population_summary, list_population, refresh_population_data

router = APIRouter()


@router.post("/api/population/refresh")
def refresh_population(months: int = 60):
    """KOSIS에서 최신 창원시 월별 인구를 받아와 Firestore에 저장(없으면 추가, 있으면 갱신)."""
    try:
        return refresh_population_data(months)
    except KosisError as e:
        raise server_error("인구 데이터 갱신", e, 502, "인구 데이터를 가져오지 못했어요. 잠시 후 다시 시도해 주세요.")


@router.get("/api/population")
def get_population():
    items = list_population()
    return {"count": len(items), "items": items}


@router.get("/api/population/summary")
def get_population_summary():
    p = build_population_summary()
    if p is None:
        return {"message": "아직 인구 데이터가 없어요. POST /api/population/refresh 를 먼저 실행해 주세요"}
    return p
