"""
KOSIS(국가통계포털) OpenAPI 연결 모듈 — 창원시 월별 주민등록인구
------------------------------------------------------------------
kosis_test.py 에서 성공한 방법을 main.py 에서도 쓸 수 있게 '함수'로 정리했어요.

  통계표: 행정구역(시군구)별 성별 인구수 (orgId=101, tblId=DT_1B040A3)
  원자료: 행정안전부 주민등록인구통계 (매월 갱신)
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://kosis.kr/openapi"
ORG_ID = "101"
TBL_ID = "DT_1B040A3"
REGION_NAME = "창원시"
REGION_CODE = "48120"   # 2010년 통합 이후 지금의 창원시 (48110 = 통합 전 옛 창원시)
ITEM_CODE = "T20"       # 총인구수 (T21=남자, T22=여자)
MEMO = "창원시 총인구수"


class KosisError(Exception):
    """KOSIS 쪽에서 문제가 생겼을 때 쓰는 에러 (인증키는 메시지에 넣지 않아요)."""


def _call(path, params):
    api_key = os.getenv("KOSIS_API_KEY")
    if not api_key:
        raise KosisError(".env 에 KOSIS_API_KEY 가 없어요")
    full = {**params, "apiKey": api_key, "format": "json", "jsonVD": "Y"}
    res = requests.get(f"{BASE}/{path}", params=full, timeout=30)
    if res.status_code != 200:
        raise KosisError(f"KOSIS 응답 오류 {res.status_code} ({path})")
    data = res.json()
    if isinstance(data, dict) and data.get("err"):
        raise KosisError(f"KOSIS 에러 {data.get('err')}: {data.get('errMsg')}")
    return data


def fetch_changwon_population(months: int = 60):
    """최근 months 개월의 창원시 총인구수를 [{date, value, memo}, ...] 로 돌려줘요."""
    rows = _call("Param/statisticsParameterData.do", {
        "method": "getList", "orgId": ORG_ID, "tblId": TBL_ID,
        "itmId": ITEM_CODE, "objL1": REGION_CODE, "objL2": "",
        "prdSe": "M", "newEstPrdCnt": str(months),
    })
    result = []
    for r in rows:
        ym = r["PRD_DE"]                      # 예: '202609'
        result.append({
            "date": f"{ym[:4]}-{ym[4:]}",     # 예: '2026-09'
            "value": int(float(r["DT"])),     # 인구수(명)
            "memo": MEMO,
        })
    result.sort(key=lambda x: x["date"])
    return result
