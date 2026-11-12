"""검색 관심도 데이터 API — 요약 / 통계 / CRUD."""
from fastapi import APIRouter, HTTPException, Query
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from firebase_config import db
from schemas import DataItem
from services.cache import clear_cache
from services.summary import build_statistics, build_summary

router = APIRouter()


@router.get("/api/data/summary")
def get_summary(days: int | None = Query(default=None, ge=1, le=365, description="추세 비교 기간(일). 비우면 기본값 30")):
    summary = build_summary(days)
    if summary is None:
        return {"message": "아직 데이터가 없어요"}
    return summary


# (보너스) 추가 통계 지표 — 업종별 월별 평균(그래프용) + 변동성·격차
@router.get("/api/data/statistics")
def get_statistics():
    return build_statistics()


# ============================================================
# 데이터 API (CRUD)
# ============================================================
@router.get("/api/data")
def get_data(memo: str | None = None, limit: int = Query(default=100, ge=1, le=2000)):
    """최신 날짜가 먼저 오도록 정렬해서 돌려줘요 (새로 넣은 데이터가 바로 보이게)."""
    if memo:
        # 업종 필터 + 날짜 정렬을 Firestore에서 같이 하려면 '복합 색인'이 필요해요.
        # 업종별 데이터는 양이 적으니, 가져온 뒤 파이썬에서 정렬해요.
        docs = db.collection("data").where(filter=FieldFilter("memo", "==", memo)).stream()
        result = []
        for doc in docs:
            item = doc.to_dict()
            item["id"] = doc.id
            result.append(item)
        result.sort(key=lambda r: r.get("date", ""), reverse=True)
        result = result[:limit]
    else:
        docs = db.collection("data").order_by("date", direction=firestore.Query.DESCENDING).limit(limit).stream()
        result = []
        for doc in docs:
            item = doc.to_dict()
            item["id"] = doc.id
            result.append(item)
    return {"count": len(result), "items": result}


@router.post("/api/data")
def create_data(item: DataItem):
    ref = db.collection("data").add(item.model_dump())
    clear_cache()   # 데이터가 바뀌었으니 기억해 둔 요약을 지워요
    return {"message": "저장했어요", "id": ref[1].id}


@router.put("/api/data/{doc_id}")
def update_data(doc_id: str, item: DataItem):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.set(item.model_dump())
    clear_cache()
    return {"message": "수정했어요", "id": doc_id}


@router.delete("/api/data/{doc_id}")
def delete_data(doc_id: str):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.delete()
    clear_cache()
    return {"message": "삭제했어요", "id": doc_id}
