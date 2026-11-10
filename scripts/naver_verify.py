import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
확정 검색어 점검 — 같은 잣대(한 번의 요청)로 3업종을 받아서 확인해요
--------------------------------------------------------------------
실행 방법 (VS Code 터미널, venv 켜진 상태, ai-secretary 폴더에서):
    python scripts\\naver_verify.py

하는 일:
  [점검 1] 기존과 같은 기간(2025-09-09~2026-09-09): 기존 CSV와 평균 크기·모양이 비슷한지
  [점검 2] 3년 치(2023-11-01~2026-10-31): 요일 패턴(주말/평일)이 해마다 이어지는지
  ※ 화면에만 보여주고 저장은 하지 않아요. 키 값은 찍지 않아요.
"""
import csv
import datetime as dt
import statistics as st
import requests
from dotenv import load_dotenv

load_dotenv()
CID, CSEC = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
if not CID or not CSEC:
    sys.exit("❌ .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 없어요.")

URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
GROUPS = {   # 확정안 (3업종을 한 번의 요청에 담아야 업종 간 크기 비교가 같은 잣대예요)
    "카페": ["창원카페", "창원디저트"],
    "미용/뷰티": ["창원미용실", "창원네일", "창원속눈썹"],
    "미용의료": ["창원성형외과"],
}
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "datalab_data.csv")


def fetch(start, end):
    body = {"startDate": start, "endDate": end, "timeUnit": "date",
            "keywordGroups": [{"groupName": g, "keywords": k} for g, k in GROUPS.items()]}
    headers = {"X-NCP-APIGW-API-KEY-ID": CID, "X-NCP-APIGW-API-KEY": CSEC, "Content-Type": "application/json"}
    res = requests.post(URL, json=body, headers=headers, timeout=60)
    if res.status_code != 200:
        sys.exit(f"❌ 응답 코드 {res.status_code}: {res.text[:300]}")
    return {r["title"]: {x["period"]: x["ratio"] for x in r["data"]} for r in res.json()["results"]}


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


# ---------- 점검 1 ----------
print("[점검 1] 기존 데이터와 비교 (2025-09-09 ~ 2026-09-09)")
orig = {}
with open(CSV_PATH, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        orig.setdefault(r["memo"], {})[r["date"]] = float(r["value"])
new1 = fetch("2025-09-09", "2026-09-09")
print(f"   {'업종':<8}{'기존 평균':>9}{'새 평균':>9}{'기존 최고':>10}{'새 최고':>8}{'닮은 정도':>10}")
for g in GROUPS:
    days = sorted(set(new1[g]) & set(orig[g]))
    a = [orig[g][d] for d in days]; b = [new1[g][d] for d in days]
    print(f"   {g:<8}{st.mean(a):>9.1f}{st.mean(b):>9.1f}{max(a):>10.1f}{max(b):>8.1f}{corr(a, b):>10.3f}")

# ---------- 점검 2 ----------
print("\n[점검 2] 3년 치 요일 패턴 (2023-11-01 ~ 2026-10-31)  ※ 숫자 = 주말 평균 ÷ 평일 평균")
new3 = fetch("2023-11-01", "2026-10-31")
periods = [("1년차(23.11~24.10)", "2023-11-01", "2024-10-31"),
           ("2년차(24.11~25.10)", "2024-11-01", "2025-10-31"),
           ("3년차(25.11~26.10)", "2025-11-01", "2026-10-31")]
print(f"   {'업종':<8}{'전체 평균':>9}" + "".join(f"{p[0]:>20}" for p in periods))
for g in GROUPS:
    allv = list(new3[g].values())
    cells = []
    for _, s, e in periods:
        wk = [v for d, v in new3[g].items() if s <= d <= e and dt.date.fromisoformat(d).weekday() >= 5]
        wd = [v for d, v in new3[g].items() if s <= d <= e and dt.date.fromisoformat(d).weekday() < 5]
        cells.append(f"{st.mean(wk) / st.mean(wd):>20.2f}" if wk and wd else f"{'-':>20}")
    print(f"   {g:<8}{st.mean(allv):>9.1f}" + "".join(cells))
print(f"\n   받은 날짜 수: " + ", ".join(f"{g} {len(new3[g])}일" for g in GROUPS) + "  (3년 = 약 1,096일)")
