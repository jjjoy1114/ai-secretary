import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
'지문 맞추기' — 기존 1년 데이터를 만들 때 쓴 검색어가 뭐였는지 찾아보는 실험
-------------------------------------------------------------------------
실행 방법 (VS Code 터미널, venv 켜진 상태, ai-secretary 폴더에서):
    python scripts\\naver_match.py

하는 일:
  1) 기존 CSV(data/datalab_data.csv)와 '같은 기간(2025-09-09~2026-09-09)'을 받아와요.
  2) 후보 검색어마다 기존 그래프와 모양이 얼마나 닮았는지(닮은 정도 0~1) 점수를 매겨요.
     → 1에 가까우면(0.98 이상) 그 검색어가 기존 데이터의 정체일 가능성이 아주 높아요.
  ※ 화면에만 보여주고, Firestore·파일은 건드리지 않아요. 키 값은 찍지 않아요.
"""
import csv
import statistics as st
import requests
from dotenv import load_dotenv

load_dotenv()
CID, CSEC = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
if not CID or not CSEC:
    sys.exit("❌ .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 없어요.")

URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
START, END = "2025-09-09", "2026-09-09"
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "datalab_data.csv")

# 업종별 후보 검색어 묶음 (한 번에 최대 5개 그룹까지 보낼 수 있어요)
CANDIDATES = {
    "미용의료": [["창원성형외과", "창원보톡스"], ["창원성형외과", "창원리프팅"], ["창원성형외과", "창원지방흡입"], ["창원성형외과", "창원코성형"], ["창원성형외과", "창원필러"]],
}

# ---- 기존 CSV 읽기 ----
orig = {}
with open(CSV_PATH, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        orig.setdefault(r["memo"], {})[r["date"]] = float(r["value"])


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def fetch(groups):
    body = {
        "startDate": START, "endDate": END, "timeUnit": "date",
        "keywordGroups": [{"groupName": " + ".join(kws), "keywords": kws} for kws in groups],
    }
    headers = {"X-NCP-APIGW-API-KEY-ID": CID, "X-NCP-APIGW-API-KEY": CSEC, "Content-Type": "application/json"}
    res = requests.post(URL, json=body, headers=headers, timeout=60)
    if res.status_code != 200:
        sys.exit(f"❌ 응답 코드 {res.status_code}: {res.text[:300]}")
    return res.json()["results"]


print(f"기간 {START} ~ {END} / 닮은 정도(1에 가까울수록 같은 데이터)\n")
for industry, cand_list in CANDIDATES.items():
    print(f"■ {industry}  (기존 평균 {st.mean(orig[industry].values()):.1f})")
    scored = []
    for r in fetch(cand_list):
        series = {x["period"]: x["ratio"] for x in r["data"]}
        days = sorted(set(series) & set(orig[industry]))
        a = [orig[industry][d] for d in days]
        b = [series[d] for d in days]
        scored.append((corr(a, b), r["keywords"], len(days)))
    for c, kws, n in sorted(scored, key=lambda t: -t[0]):
        mark = "  ← 거의 같아요!" if c >= 0.98 else ""
        print(f"   {c:.3f}  {kws}  ({n}일 비교){mark}")
    print()
