"""네이버 검색관심도(3년) 저장 + 발행 타이밍 요약 보관.

  * 'search_trend' 컬렉션에 따로 저장 (기존 'data' 컬렉션·숫자와 섞이지 않게)
  * 문서 ID = '업종_날짜' → 새로 받으면 같은 ID는 덮어쓰고, 기간 밖 옛 문서만 지워요
  * 타이밍 요약은 받을 때 한 번 계산해서 'sync_log/search_trend' 문서 1개에 보관해요
    (→ 기획안을 만들 때마다 수천 개 문서를 다시 읽지 않아요: Firestore 무료 읽기 한도 보호)
"""
import json
from collections import defaultdict
from datetime import datetime

from firebase_config import db
from naver_client import KEYWORD_GROUPS, SOURCE, fetch_search_trend
from services.timing import build_timing_summary

COLLECTION = "search_trend"
BATCH_SIZE = 400   # Firestore 한 번에 쓸 수 있는 한도(500) 아래로


def _doc_id(industry, date):
    return f"{industry}_{date}".replace("/", "_")   # '미용/뷰티'의 '/'는 문서 ID에 못 써요


def refresh_search_trend():
    """네이버에서 3년 치를 받아 저장하고 타이밍 요약을 갱신해요. (NaverError는 호출한 쪽에서 처리)"""
    rows, start, end = fetch_search_trend()

    col = db.collection(COLLECTION)
    new_ids = set()
    batch, ops = db.batch(), 0
    for r in rows:
        doc_id = _doc_id(r["memo"], r["date"])
        new_ids.add(doc_id)
        batch.set(col.document(doc_id), r)
        ops += 1
        if ops >= BATCH_SIZE:
            batch.commit()
            batch, ops = db.batch(), 0
    if ops:
        batch.commit()

    # 새로 쓴 뒤에 기간 밖 옛 문서를 지워요 (쓰기가 실패해도 기존 데이터는 남아 있어요)
    removed, batch, ops = 0, db.batch(), 0
    for doc in col.stream():
        if doc.id not in new_ids:
            batch.delete(doc.reference)
            ops += 1
            removed += 1
            if ops >= BATCH_SIZE:
                batch.commit()
                batch, ops = db.batch(), 0
    if ops:
        batch.commit()

    by_industry = defaultdict(dict)
    for r in rows:
        by_industry[r["memo"]][r["date"]] = r["value"]
    summary = build_timing_summary(by_industry, keywords=KEYWORD_GROUPS, source=SOURCE, period=(start, end))

    db.collection("sync_log").document("search_trend").set({
        "source": SOURCE,
        "refreshed_at": datetime.now().isoformat(),
        "period": f"{start} ~ {end}",
        "count": len(rows),
        "timing_json": json.dumps(summary, ensure_ascii=False),
    })
    return {
        "message": "네이버 데이터랩에서 3년 치 검색관심도를 받아 저장하고, 발행 타이밍 요약을 갱신했어요",
        "period": f"{start} ~ {end}",
        "received": len(rows),
        "per_industry": {k: len(v) for k, v in by_industry.items()},
        "removed_old": removed,
        "keywords": KEYWORD_GROUPS,
        "note": "값은 '이 기간 안에서 가장 높은 날 = 100'인 상대지수예요. 기존 data 컬렉션(1년)과는 따로 보관돼요.",
    }


def load_timing_summary():
    """보관해 둔 타이밍 요약을 돌려줘요. 아직 없으면 None."""
    doc = db.collection("sync_log").document("search_trend").get()
    if not doc.exists:
        return None
    try:
        summary = json.loads(doc.to_dict().get("timing_json", ""))
    except (TypeError, ValueError):
        return None
    summary["refreshed_at"] = doc.to_dict().get("refreshed_at")
    return summary
