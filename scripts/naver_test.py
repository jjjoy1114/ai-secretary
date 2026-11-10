import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
네이버 데이터랩 '검색어트렌드' API 연결 테스트 (NAVER API HUB)
-------------------------------------------------------------
실행 방법 (VS Code 터미널, venv 켜진 상태, ai-secretary 폴더에서):
    python scripts\\naver_test.py

하는 일:
  1) .env 금고에서 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 꺼내요.
  2) 최근 한 달(일간) 검색 관심도를 3업종 그룹으로 받아와 화면에 보여줘요.
  ※ Firestore 저장은 하지 않아요. 연결이 되는지만 확인하는 테스트예요.
  ※ 키 값은 화면에 절대 찍지 않아요.

아래 KEYWORD_GROUPS 는 '연결 테스트용 예시 검색어'예요.
기존 데이터를 받을 때 쓴 진짜 검색어는 다음 단계에서 맞춰요.
"""
import requests
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
if not CLIENT_ID or not CLIENT_SECRET:
    sys.exit("❌ .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 없어요. 철자와 '=' 앞뒤 띄어쓰기를 확인해 주세요.")

URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"

# 주제어(그룹 이름) : 그 그룹에 묶을 검색어들  ← 연결 테스트용 예시
KEYWORD_GROUPS = {
    "카페": ["창원카페"],
    "미용/뷰티": ["창원미용실", "창원네일"],
    "미용의료": ["창원피부과"],
}

body = {
    "startDate": "2026-10-01",
    "endDate": "2026-10-31",
    "timeUnit": "date",   # date=일간, week=주간, month=월간
    "keywordGroups": [{"groupName": g, "keywords": kws} for g, kws in KEYWORD_GROUPS.items()],
}
headers = {
    "X-NCP-APIGW-API-KEY-ID": CLIENT_ID,
    "X-NCP-APIGW-API-KEY": CLIENT_SECRET,
    "Content-Type": "application/json",
}

print("1) 네이버 API HUB에 요청 보내는 중...")
try:
    res = requests.post(URL, json=body, headers=headers, timeout=30)
except requests.RequestException as e:
    sys.exit(f"❌ 네이버 서버에 연결하지 못했어요: {type(e).__name__}")

print(f"   응답 코드: {res.status_code}")
if res.status_code != 200:
    # 에러 설명에는 키가 들어 있지 않아요
    print("   ❌ 실패했어요. 아래 안내문을 그대로 알려 주세요:")
    print("  ", res.text[:500])
    sys.exit(1)

data = res.json()
print("   ✅ 연결 성공!\n")
print(f"2) 받은 기간: {data.get('startDate')} ~ {data.get('endDate')} ({data.get('timeUnit')})")
for r in data.get("results", []):
    rows = r.get("data", [])
    vals = [x["ratio"] for x in rows]
    print(f"\n   [{r.get('title')}] 검색어 {r.get('keywords')} — {len(rows)}일")
    for x in rows[:5]:
        print(f"     {x['period']}  {x['ratio']:.2f}")
    if vals:
        print(f"     … 평균 {sum(vals)/len(vals):.1f}, 최고 {max(vals):.1f} (※ 이 기간 안에서 가장 높은 날 = 100 인 상대값)")
