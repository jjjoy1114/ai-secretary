"""검색 관심도('data' 컬렉션) 요약·통계 계산."""
import statistics as st
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from config import SUMMARY_RECENT_DAYS
from firebase_config import db
from services.cache import ttl_cache


@ttl_cache
def build_summary(days=None):
    """days: 추세 비교 기간(일). 안 주면 환경변수 SUMMARY_RECENT_DAYS(기본 30)를 써요."""
    days = days or SUMMARY_RECENT_DAYS
    docs = db.collection("data").stream()
    rows = [doc.to_dict() for doc in docs]
    if not rows:
        return None

    rows.sort(key=lambda r: r["date"])
    dates = [r["date"] for r in rows]

    industries = {}
    for r in rows:
        industries.setdefault(r["memo"], []).append(r)

    # 추세 비교 기준일 = 전체 데이터의 가장 최근 날짜 (모든 업종을 같은 기간으로 비교)
    end_date = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    recent_start = end_date - timedelta(days=days)         # 최근 N일: (recent_start, end_date]
    previous_start = end_date - timedelta(days=2 * days)   # 그 앞 N일: (previous_start, recent_start]

    def summarize(items):
        items = sorted(items, key=lambda r: r["date"])
        values = [r["value"] for r in items]
        n = len(values)
        avg = round(sum(values) / n, 1)
        # '개수'가 아니라 실제 날짜 범위로 최근/이전 구간을 나눠요 (날짜가 비어 있어도 정확)
        recent, previous = [], []
        for r in items:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if d > recent_start:
                recent.append(r["value"])
            elif d > previous_start:
                previous.append(r["value"])
        trend = "유지"
        if recent and previous:
            r_avg = sum(recent) / len(recent)
            p_avg = sum(previous) / len(previous)
            if r_avg > p_avg * 1.05:
                trend = "증가"
            elif r_avg < p_avg * 0.95:
                trend = "감소"
        return {
            "count": n,
            "average": avg,
            "max": round(max(values), 1),
            "min": round(min(values), 1),
            "trend": trend,
        }

    return {
        "period": f"{dates[0]} ~ {dates[-1]}",
        "count": len(rows),
        "recent_days": days,      # 추세를 비교한 기간(최근 N일 vs 그 앞 N일, 실제 날짜 기준)
        "trend_basis": f"{recent_start + timedelta(days=1)} ~ {end_date} vs {previous_start + timedelta(days=1)} ~ {recent_start}",
        "generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),  # 요약을 만든 시각(KST)
        "unit": "네이버 데이터랩 상대지수(0~100, 최고=100)",
        "by_industry": {name: summarize(items) for name, items in industries.items()},
    }


def summary_to_text(summary):
    lines = [
        f"- 기간: {summary['period']} (총 {summary['count']}개)",
        f"- 값 단위: {summary['unit']}",
    ]
    for name, s in summary["by_industry"].items():
        lines.append(
            f"- {name}: 평균 {s['average']}, 최대 {s['max']}, 최소 {s['min']}, 최근추세 {s['trend']}"
        )
    return "\n".join(lines)


@ttl_cache
def build_statistics():
    """(보너스) 추가 통계 지표 — 업종별 월별 평균(그래프용) + 변동성·격차."""
    rows = [d.to_dict() for d in db.collection("data").stream()]
    if not rows:
        return {"message": "데이터가 없어요"}

    monthly = defaultdict(lambda: defaultdict(list))  # 업종 -> 월 -> [값]
    by_ind = defaultdict(list)
    for r in rows:
        memo = r["memo"]; month = str(r["date"])[:7]; v = float(r["value"])
        monthly[memo][month].append(v)
        by_ind[memo].append(v)

    monthly_out = {}
    for memo, mm in monthly.items():
        monthly_out[memo] = [
            {"month": m, "avg": round(sum(vs) / len(vs), 1)} for m, vs in sorted(mm.items())
        ]

    std_out = {memo: round(st.pstdev(vs), 1) for memo, vs in by_ind.items()}  # 변동성
    avgs = {memo: sum(vs) / len(vs) for memo, vs in by_ind.items()}
    gap = round(max(avgs.values()) - min(avgs.values()), 1)                   # 업종간 격차
    top = max(avgs, key=avgs.get)

    return {
        "monthly": monthly_out,
        "변동성_표준편차": std_out,
        "업종간_평균격차": gap,
        "최고관심_업종": top,
    }
