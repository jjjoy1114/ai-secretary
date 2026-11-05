"""창원시 인구 — KOSIS(국가통계포털) 공공데이터 연동.

  * 'population' 컬렉션에 따로 저장 (검색 관심도 데이터와 섞이지 않게)
  * 문서 ID = 'YYYY-MM' → 같은 달은 덮어쓰기라서 여러 번 눌러도 중복이 안 생겨요
"""
from datetime import datetime

from firebase_config import db
from kosis_client import fetch_changwon_population


def refresh_population_data(months):
    """KOSIS에서 받아와 저장하고 결과 정보를 돌려줘요. (KosisError는 호출한 쪽에서 처리)"""
    rows = fetch_changwon_population(months)

    col = db.collection("population")
    existing = {doc.id for doc in col.stream()}
    batch = db.batch()
    for r in rows:
        batch.set(col.document(r["date"]), r)
    batch.commit()

    new_count = len([r for r in rows if r["date"] not in existing])
    db.collection("sync_log").document("population").set({
        "source": "KOSIS DT_1B040A3 (행정안전부 주민등록인구)",
        "refreshed_at": datetime.now().isoformat(),
        "latest_month": rows[-1]["date"] if rows else None,
        "count": len(rows),
    })
    return {
        "message": "KOSIS에서 최신 인구 데이터를 받아 저장했어요",
        "received": len(rows),
        "new": new_count,
        "updated": len(rows) - new_count,
        "period": f"{rows[0]['date']} ~ {rows[-1]['date']}" if rows else None,
    }


def list_population():
    docs = db.collection("population").stream()
    return sorted((d.to_dict() for d in docs), key=lambda r: r["date"])


def build_population_summary():
    rows = list_population()
    if not rows:
        return None
    first, last = rows[0], rows[-1]
    values = [r["value"] for r in rows]

    # 1년 전 같은 달과 비교
    year_ago = next((r for r in rows if r["date"] == f"{int(last['date'][:4]) - 1}{last['date'][4:]}"), None)
    yoy = last["value"] - year_ago["value"] if year_ago else None

    # 100만 명 아래로 처음 내려간 달 (창원시는 '특례시' 기준이 인구 100만이라 의미 있는 지점)
    below_1m = next((r["date"] for r in rows if r["value"] < 1_000_000), None)

    sync = db.collection("sync_log").document("population").get()
    return {
        "region": "경상남도 창원시",
        "period": f"{first['date']} ~ {last['date']}",
        "count": len(rows),
        "unit": "명 (주민등록인구, 월말 기준)",
        "latest": {"date": last["date"], "value": last["value"]},
        "change_total": last["value"] - first["value"],
        "change_rate_total": round((last["value"] - first["value"]) / first["value"] * 100, 2),
        "change_1year": yoy,
        "avg_monthly_change": round((last["value"] - first["value"]) / max(len(rows) - 1, 1)),
        "max": max(values),
        "min": min(values),
        "first_month_below_1m": below_1m,
        "source": "KOSIS 국가통계포털 (행정안전부 주민등록인구통계)",
        "refreshed_at": sync.to_dict().get("refreshed_at") if sync.exists else None,
    }


def population_summary_to_text(p):
    lines = [
        f"- 지역: {p['region']}, 기간: {p['period']} (월별 {p['count']}개), 단위: {p['unit']}",
        f"- 최근({p['latest']['date']}) 인구: {p['latest']['value']:,}명",
        f"- 기간 전체 변화: {p['change_total']:+,}명 ({p['change_rate_total']:+}%), 월평균 {p['avg_monthly_change']:+,}명",
    ]
    if p["change_1year"] is not None:
        lines.append(f"- 최근 1년 변화: {p['change_1year']:+,}명")
    if p["first_month_below_1m"]:
        lines.append(f"- 인구 100만 명 아래로 처음 내려간 달: {p['first_month_below_1m']}")
    lines.append(f"- 출처: {p['source']}")
    return "\n".join(lines)
