"""발행 타이밍 근거 — 검색관심도(일간)에서 '언제 올릴지'를 계산해요.

  * 요일 패턴   : 주말/평일 비율, 연도별로 반복되는지
  * 시즌        : 월별 지수 (요일 효과를 먼저 걷어낸 뒤 계산)
  * 행사 전후   : 명절·기념일 며칠 전부터 검색이 오르는지
  * 다가오는 행사: 오늘 기준 '언제까지 올리면 좋은지'

순수 계산만 있어요 (Firestore·네트워크 없음) → 숫자만 넣어 바로 테스트할 수 있어요.
※ 검색관심도는 '관심의 흐름'이지 방문·매출이 아니에요. 시각(몇 시) 정보는 없어요.
"""
import statistics as st
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 행사 달력 — 양력(매년 같은 날)과 음력(해마다 날짜가 달라서 직접 적었어요)
FIXED_EVENTS = {
    "새해": (1, 1),
    "발렌타인데이": (2, 14),
    "화이트데이": (3, 14),
    "어린이날": (5, 5),
    "어버이날": (5, 8),
    "크리스마스": (12, 25),
}
LUNAR_EVENTS = {
    "설날": [date(2024, 2, 10), date(2025, 1, 29), date(2026, 2, 17), date(2027, 2, 6)],
    "추석": [date(2023, 9, 29), date(2024, 9, 17), date(2025, 10, 6), date(2026, 9, 25), date(2027, 9, 15)],
}

RISE_RATIO = 1.25      # 평소(행사 2주 전 평균)의 1.25배를 넘으면 '오르기 시작'으로 봐요
PEAK_MIN_RATIO = 1.3   # 행사 앞뒤 최고점이 평소의 1.3배 미만이면 '뚜렷한 변화 없음'


def event_occurrences(start_year, end_year):
    out = []
    for y in range(start_year, end_year + 1):
        for name, (m, d) in FIXED_EVENTS.items():
            out.append((name, date(y, m, d)))
    for name, days in LUNAR_EVENTS.items():
        out.extend((name, d) for d in days if start_year <= d.year <= end_year)
    return sorted(out, key=lambda t: t[1])


def weekday_factors(series):
    """요일별 지수: 그 요일 평균 ÷ 전체 평균 (1.0 = 평균)."""
    overall = st.mean(series.values())
    by = defaultdict(list)
    for d, v in series.items():
        by[d.weekday()].append(v)
    return {wd: (st.mean(vs) / overall if overall > 0 else 1.0) for wd, vs in by.items()}


def _adjusted(series, factors):
    """요일 효과를 걷어낸 값 (토요일 값은 토요일 지수로 나눠요)."""
    return {d: v / (factors.get(d.weekday()) or 1.0) for d, v in series.items()}


def _weekend_ratio(items):
    wk = [v for d, v in items if d.weekday() >= 5]
    wd = [v for d, v in items if d.weekday() < 5]
    if not wk or not wd or st.mean(wd) <= 0:
        return None
    return st.mean(wk) / st.mean(wd)


def analyze_weekday(series, factors):
    items = sorted(series.items())
    overall = _weekend_ratio(items)
    # 364일(52주)씩 끝에서부터 잘라 '연도별' 비율을 봐요 (요일이 균등하게 들어가요)
    yearly = []
    end = items[-1][0]
    n_blocks = ((end - items[0][0]).days + 1) // 364
    for i in range(n_blocks):
        blk_end = end - timedelta(days=364 * i)
        blk_start = blk_end - timedelta(days=363)
        blk = [(d, v) for d, v in items if blk_start <= d <= blk_end]
        if len(blk) >= 300:
            r = _weekend_ratio(blk)
            if r is not None:
                yearly.append(round(r, 2))
    yearly.reverse()   # 오래된 해 → 최근 해

    pattern = "요일 차이 작음"
    if overall is not None:
        if overall >= 1.15 and all(r >= 1.1 for r in yearly):
            pattern = "주말형"
        elif overall <= 0.87 and all(r <= 0.93 for r in yearly):
            pattern = "평일형"
    return {
        "pattern": pattern,
        "weekend_ratio": round(overall, 2) if overall is not None else None,
        "yearly_ratios": yearly,
        "index": {WEEKDAY_KR[wd]: round(f * 100) for wd, f in sorted(factors.items())},
    }


def analyze_months(adj):
    """월별 지수 (100 = 평균). 같은 달이 여러 해 있으면 몇 해나 평균 이상이었는지도 같이 봐요."""
    overall = st.mean(adj.values())
    by_ym = defaultdict(list)
    for d, v in adj.items():
        by_ym[(d.year, d.month)].append(v)
    by_month = defaultdict(list)
    for (_, m), vs in by_ym.items():
        if len(vs) >= 25:                    # 일부만 있는 달(예: 9일치)은 빼요
            by_month[m].append(st.mean(vs))
    out = {}
    for m, means in by_month.items():
        out[str(m)] = {
            "index": round(st.mean(means) / overall * 100),
            "years": len(means),
            "years_above_avg": sum(1 for x in means if x > overall),
        }
    return out


def analyze_events(adj):
    """행사 앞뒤 흐름: 행사 2주 전 평균(평소) 대비 며칠 전부터 몇 배로 오르는지."""
    result = {}
    if not adj:
        return result
    first, last = min(adj), max(adj)
    grouped = defaultdict(list)
    for name, d in event_occurrences(first.year, last.year):
        grouped[name].append(d)
    everything = event_occurrences(first.year - 1, last.year + 1)
    for name, days in grouped.items():
        ratios = defaultdict(list)
        n = 0
        for d in days:
            # 앞 2주~뒤 3일 안에 다른 행사가 있으면 섞이니까 그 해는 빼요 (예: 새해 7일 전 = 크리스마스)
            if any(o_name != name and -14 <= (o_date - d).days <= 3 for o_name, o_date in everything):
                continue
            offsets = range(-14, 4)
            if not all((d + timedelta(days=k)) in adj for k in offsets):
                continue                                   # 앞뒤 데이터가 다 있는 해만 써요
            base = st.mean(adj[d + timedelta(days=k)] for k in range(-14, -7))
            if base <= 0:
                continue
            for k in range(-7, 4):
                ratios[k].append(adj[d + timedelta(days=k)] / base)
            n += 1
        if n == 0:
            continue
        mean_ratio = {k: st.mean(v) for k, v in ratios.items()}
        peak_k = max(mean_ratio, key=mean_ratio.get)
        peak = mean_ratio[peak_k]
        rise = None
        if peak >= PEAK_MIN_RATIO:
            for k in range(-7, 1):
                tail = [mean_ratio[j] for j in range(k, 1)]
                if mean_ratio[k] >= RISE_RATIO and st.mean(tail) >= RISE_RATIO:
                    rise = k
                    break
        result[name] = {
            "occurrences": n,
            "peak_offset": peak_k,
            "peak_ratio": round(peak, 2),
            "rise_start": rise,       # 예: -3 → 행사 3일 전부터 오름 (None = 뚜렷한 상승 없음)
        }
    return result


def build_timing_summary(rows_by_industry, keywords=None, source="", period=None):
    """rows_by_industry: {업종: {'YYYY-MM-DD': 값}} → 업종별 타이밍 요약(JSON으로 저장 가능)."""
    industries = {}
    for name, vals in rows_by_industry.items():
        series = {date.fromisoformat(k): float(v) for k, v in vals.items()}
        if len(series) < 60:
            continue
        factors = weekday_factors(series)
        adj = _adjusted(series, factors)
        industries[name] = {
            "days": len(series),
            "weekday": analyze_weekday(series, factors),
            "months": analyze_months(adj),
            "events": analyze_events(adj),
        }
    return {
        "source": source,
        "period": f"{period[0]} ~ {period[1]}" if period else None,
        "keywords": keywords or {},
        "unit": "검색관심도 상대지수 (기간 내 최고=100). 방문·매출이 아니라 관심의 흐름",
        "industries": industries,
    }


def upcoming_events(events, today, horizon_days=75):
    """오늘 기준 앞으로 horizon_days 안의 행사와 '언제까지 올리면 좋은지'."""
    out = []
    for name, d in event_occurrences(today.year, today.year + 1):
        left = (d - today).days
        info = events.get(name)
        if left < 0 or left > horizon_days or not info or info.get("rise_start") is None:
            continue
        publish_by = d + timedelta(days=info["rise_start"] - 1)
        out.append({
            "event": name,
            "date": d.isoformat(),
            "days_left": left,
            "rise_start": info["rise_start"],
            "publish_by": publish_by.isoformat(),
            "already_rising": publish_by < today,
        })
    return sorted(out, key=lambda x: x["date"])


def timing_to_text(summary, industry, today=None):
    """AI에게 줄 '발행 타이밍 근거' 문장 (한 업종). 근거가 없으면 빈 문자열."""
    info = (summary or {}).get("industries", {}).get(industry)
    if not info:
        return ""
    today = today or datetime.now(KST).date()
    wd, months, events = info["weekday"], info["months"], info["events"]
    kws = " · ".join((summary.get("keywords") or {}).get(industry, []))

    lines = [f"- 근거: 네이버 데이터랩 검색관심도(일간) {summary.get('period')}, 묶은 검색어: {kws}"]

    # 요일
    if wd["weekend_ratio"] is not None:
        yr = "·".join(f"{r:.2f}" for r in wd["yearly_ratios"])
        yr_text = f" (연도별 {yr})" if yr else ""
        verb = {"주말형": "주말(토·일)에 높아요", "평일형": "평일에 높고 주말에 낮아요"}.get(wd["pattern"], "요일 차이가 작아요")
        lines.append(f"- 요일: 주말 평균이 평일의 {wd['weekend_ratio']}배{yr_text} → {wd['pattern']}, {verb}")
        lines.append("  요일지수(평균=100): " + " ".join(f"{k} {v}" for k, v in wd["index"].items()))

    # 시즌(월)
    if months:
        ranked = sorted(months.items(), key=lambda kv: -kv[1]["index"])

        def fmt(item):
            m, v = item
            return f"{m}월 {v['index']}({v['years']}년 중 {v['years_above_avg']}년 평균 이상)"

        lines.append("- 시즌(월별 지수, 요일 효과 제거, 평균=100): 높은 달 " + ", ".join(fmt(x) for x in ranked[:3])
                     + " / 낮은 달 " + ", ".join(fmt(x) for x in ranked[-2:]))
        if max(v["years"] for v in months.values()) < 2:
            lines.append("  (※ 1년 치라 계절 패턴인지 우연인지 구분이 어려워요 — 참고용)")

    # 행사 전후
    ev_lines = []
    for name, e in events.items():
        if e["rise_start"] is None:
            continue
        ev_lines.append(f"{name}: 보통 {abs(e['rise_start'])}일 전부터 평소의 {RISE_RATIO}배 이상으로 오르고 "
                        f"{'당일' if e['peak_offset'] == 0 else str(abs(e['peak_offset'])) + '일 ' + ('전' if e['peak_offset'] < 0 else '후')}"
                        f" 약 {e['peak_ratio']}배까지 (확인 {e['occurrences']}회)")
    if ev_lines:
        lines.append("- 행사 전후(요일 효과 제거, 평소=1.0):")
        lines.extend("  · " + t for t in ev_lines)

    # 다가오는 행사
    up = upcoming_events(events, today)
    if up:
        lines.append(f"- 오늘({today.isoformat()}) 기준 다가오는 행사:")
        for u in up:
            if u["already_rising"]:
                tip = "이미 관심이 오르는 구간이에요 → 지금 바로 발행"
            else:
                tip = f"{u['publish_by']} 까지 발행 권장"
            lines.append(f"  · {u['event']} {u['date']} ({u['days_left']}일 후) → {tip}")

    lines.append("- 주의: 검색 관심의 흐름이며 방문·매출이 아니에요. 시각(몇 시) 근거는 데이터에 없어요.")
    return "\n".join(lines)
