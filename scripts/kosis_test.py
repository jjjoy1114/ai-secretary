import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
KOSIS(국가통계포털) OpenAPI 테스트 — 창원시 월별 인구 받아오기
-------------------------------------------------------------
실행 방법 (VS Code 터미널, venv 켜진 상태):
    python kosis_test.py

하는 일:
  1) 통계표의 '메뉴판(메타정보)'을 받아서 '창원시' 코드와 '총인구수' 코드를 찾아요.
  2) 그 코드로 최근 36개월치 월별 인구를 받아와 화면에 보여줘요.
  ※ 아직 Firestore 저장은 하지 않아요. (다음 단계에서 해요)
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()  # .env 금고에서 키를 꺼내요
API_KEY = os.getenv("KOSIS_API_KEY")
if not API_KEY:
    sys.exit("❌ .env 에 KOSIS_API_KEY 가 없어요. 철자와 '=' 앞뒤 띄어쓰기를 확인해 주세요.")

BASE = "https://kosis.kr/openapi"
ORG_ID = "101"           # 통계청(국가데이터처)
TBL_ID = "DT_1B040A3"    # 행정구역(시군구)별 성별 인구수 — 행정안전부 주민등록인구, 월별


def call(url, params):
    """KOSIS에 요청을 보내고 JSON으로 돌려받아요. 에러면 친절하게 알려줘요."""
    params = {**params, "apiKey": API_KEY, "format": "json", "jsonVD": "Y"}
    res = requests.get(url, params=params, timeout=30)
    if res.status_code != 200:
        # 에러 메시지에 인증키가 찍히지 않도록 주소만 보여줘요
        sys.exit(f"❌ KOSIS 응답 오류 {res.status_code} (요청 주소: {url})")
    data = res.json()
    if isinstance(data, dict) and data.get("err"):
        sys.exit(f"❌ KOSIS 에러 {data.get('err')}: {data.get('errMsg')}")
    return data


# ---------- 1) 메뉴판(메타정보)에서 코드 찾기 ----------
print("1) 통계표 메뉴판(메타정보) 받는 중...")
meta = call(f"{BASE}/statisticsData.do", {
    "method": "getMeta", "type": "ITM", "orgId": ORG_ID, "tblId": TBL_ID,
})

region = [m for m in meta if m.get("OBJ_ID") != "ITEM" and m.get("ITM_NM", "").strip() == "창원시"]
# '창원시'가 2개 나와요: 48120 = 2010년 통합 이후 지금의 창원시, 48110 = 통합 전 옛 창원시
# → 지금의 창원시(48120)를 맨 앞으로 보내요
region.sort(key=lambda m: m["ITM_ID"] != "48120")
items = [m for m in meta if m.get("OBJ_ID") == "ITEM"]
total = [m for m in items if "총인구" in m.get("ITM_NM", "")]

print(f"   - 지역 분류 중 '창원시': {[(r['OBJ_ID'], r['ITM_ID'], r['ITM_NM']) for r in region]}")
print(f"   - 항목 목록: {[(i['ITM_ID'], i['ITM_NM']) for i in items]}")

if not region or not total:
    # 못 찾으면 '창원'이 들어간 이름을 모두 보여줘서 함께 고를 수 있게 해요
    cands = [(m.get("OBJ_ID"), m.get("ITM_ID"), m.get("ITM_NM")) for m in meta if "창원" in m.get("ITM_NM", "")]
    sys.exit(f"⚠️ 코드를 자동으로 못 찾았어요. '창원' 후보: {cands}")

obj_id_sn = region[0].get("OBJ_ID_SN", "1")      # 몇 번째 분류인지 (보통 1)
region_code = region[0]["ITM_ID"]
item_code = total[0]["ITM_ID"]
print(f"   ✅ 창원시 코드 = {region_code} (분류 {obj_id_sn}번), 총인구수 코드 = {item_code}")

# ---------- 2) 창원시 월별 인구 받아오기 ----------
print("\n2) 최근 36개월 창원시 인구 받는 중...")
rows = call(f"{BASE}/Param/statisticsParameterData.do", {
    "method": "getList", "orgId": ORG_ID, "tblId": TBL_ID,
    "itmId": item_code, f"objL{obj_id_sn}": region_code,
    "prdSe": "M", "newEstPrdCnt": "36",
    # 다른 분류 칸은 비워 둬요 (이 통계표는 '행정구역' 분류 하나뿐이에요)
    **{f"objL{n}": "" for n in ("1", "2") if n != str(obj_id_sn)},
})

# 성별 같은 다른 분류가 섞여 있으면 '계'만 남겨요
rows = [r for r in rows if r.get("C2_NM") in (None, "", "계", "전체")] or rows
rows.sort(key=lambda r: r["PRD_DE"])

print(f"   ✅ {len(rows)}개월 받았어요!\n")
print("   년월      인구수(명)")
for r in rows:
    ym = f"{r['PRD_DE'][:4]}-{r['PRD_DE'][4:]}"
    print(f"   {ym}   {int(float(r['DT'])):>10,}")

first, last = rows[0], rows[-1]
diff = int(float(last["DT"])) - int(float(first["DT"]))
print(f"\n   📉📈 {first['PRD_DE']} → {last['PRD_DE']} 변화: {diff:+,}명")
print(f"   출처: KOSIS 국가통계포털 ({last.get('TBL_NM', TBL_ID)}), 단위: {last.get('UNIT_NM', '명')}")
