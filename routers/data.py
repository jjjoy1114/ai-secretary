"""검색 관심도 데이터 API — 요약 / 통계 / CRUD."""
from fastapi import APIRouter, HTTPException
from google.cloud.firestore_v1 import FieldFilter

from firebase_config import db
from schemas import DataItem
from services.summary import build_statistics, build_summary

router = APIRouter()


@router.get("/api/data/summary")
def get_summary():
    summary = build_summary()
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
def get_data(memo: str | None = None, limit: int = 100):
    query = db.collection("data")
    if memo:
        query = query.where(filter=FieldFilter("memo", "==", memo))
    docs = query.limit(limit).stream()
    result = []
    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id
        result.append(item)
    return {"count": len(result), "items": result}


@router.post("/api/data")
def create_data(item: DataItem):
    ref = db.collection("data").add(item.model_dump())
    return {"message": "저장했어요", "id": ref[1].id}


@router.put("/api/data/{doc_id}")
def update_data(doc_id: str, item: DataItem):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.set(item.model_dump())
    return {"message": "수정했어요", "id": doc_id}


@router.delete("/api/data/{doc_id}")
def delete_data(doc_id: str):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.delete()
    return {"message": "삭제했어요", "id": doc_id}
