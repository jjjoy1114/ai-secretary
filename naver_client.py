"""
네이버 데이터랩 '검색어트렌드' 연결 모듈 (NAVER API HUB)
------------------------------------------------------
  * 3업종을 '한 번의 요청'에 담아 받아요 → 업종끼리 크기 비교가 같은 잣대예요.
  * 값은 '요청한 기간 안에서 가장 높은 날 = 100'인 상대지수예요.
    (그래서 기간을 바꾸면 모든 숫자가 다시 계산돼요 → 새로 받을 땐 항상 전체 기간을 통째로 받아요)
  * 검색어는 아래 KEYWORD_GROUPS 에 적어 두었어요. (scripts/naver_match.py 로 기존 데이터와 맞춰 본 결과)
  * 키(NAVER_CLIENT_ID / NAVER_CLIENT_SECRET)는 .env 에서만 읽고, 오류 메시지에 넣지 않아요.
"""
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
SOURCE = "네이버 데이터랩 검색어트렌드 (NAVER API HUB, 통합검색·일간·전체 성별/연령)"

# 업종 이름 : 그 업종으로 묶은 검색어 (업종 이름은 기존 'data' 컬렉션의 memo와 같아요)
KEYWORD_GROUPS = {
    "카페": ["창원카페", "창원디저트"],
    "미용/뷰티": ["창원미용실", "창원네일", "창원속눈썹"],
    "미용의료": ["창원성형외과"],
}

WINDOW_DAYS = 1096   # 받는 기간: 약 3년 (365×3 + 윤일)
END_LAG_DAYS = 2     # 오늘 기준 이틀 전까지만 받아요 (최근 1~2일은 집계 중일 수 있어요)
KST = timezone(timedelta(hours=9))


class NaverError(Exception):
    """네이버 쪽에서 문제가 생겼을 때 쓰는 에러 (인증키는 메시지에 넣지 않아요)."""


def default_window():
    end = datetime.now(KST).date() - timedelta(days=END_LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    return start.isoformat(), end.isoformat()


def fetch_search_trend(start=None, end=None):
    """3업종 일간 검색관심도를 [{date, value, memo}, ...] 로 돌려줘요. (start, end 도 함께)"""
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise NaverError(".env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 없어요")
    if not start or not end:
        start, end = default_window()

    body = {
        "startDate": start,
        "endDate": end,
        "timeUnit": "date",
        "keywordGroups": [{"groupName": g, "keywords": kws} for g, kws in KEYWORD_GROUPS.items()],
    }
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
        "Content-Type": "application/json",
    }
    try:
        res = requests.post(URL, json=body, headers=headers, timeout=60)
    except requests.RequestException as e:
        raise NaverError(f"네이버 서버에 연결하지 못했어요 ({type(e).__name__})")
    if res.status_code != 200:
        raise NaverError(f"네이버 응답 오류 {res.status_code}: {res.text[:200]}")

    rows = []
    for result in res.json().get("results", []):
        industry = result.get("title")
        for x in result.get("data", []):
            rows.append({"date": x["period"], "value": round(float(x["ratio"]), 2), "memo": industry})
    if not rows:
        raise NaverError("네이버에서 받은 데이터가 비어 있어요")
    rows.sort(key=lambda r: (r["memo"], r["date"]))
    return rows, start, end
