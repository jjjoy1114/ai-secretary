"""
AI 비서 MCP 서버
------------------------------------------------------------
배포된 백엔드(Render)의 기능을 Claude 데스크톱에서 '도구'로 쓸 수 있게 연결합니다.
- 이 서버는 GPT를 직접 부르지 않아요. 이미 배포된 우리 백엔드에 HTTP로 '전화'만 겁니다.
- 그래서 여기엔 어떤 API 키도 넣을 필요가 없습니다.
"""

import requests
from mcp.server.fastmcp import FastMCP

# 배포된 백엔드 주소 (Render)
BASE_URL = "https://ai-secretary-07fk.onrender.com"

# Render 무료 요금제는 15분 미사용 시 잠들어, 첫 호출이 30~60초 걸릴 수 있어요(콜드스타트).
TIMEOUT = 90

mcp = FastMCP("ai-secretary")


@mcp.tool()
def get_search_summary() -> dict:
    """창원 3업종(카페 · 미용/뷰티 · 미용의료)의 네이버 검색관심도 요약을 가져옵니다.
    업종별 평균과 최근 추세(오름/내림) 등 전반적인 '분위기'가 궁금할 때 사용하세요."""
    res = requests.get(f"{BASE_URL}/api/data/summary", timeout=TIMEOUT)
    res.raise_for_status()
    return res.json()


@mcp.tool()
def get_statistics() -> dict:
    """업종별 상세 통계를 가져옵니다.
    (업종별 월별 평균 추이, 변동성=표준편차, 업종 간 평균 격차, 최고 관심 업종)
    '어느 업종이 제일 들쭉날쭉한지', '월별 흐름' 같은 구체 수치가 필요할 때 사용하세요."""
    res = requests.get(f"{BASE_URL}/api/data/statistics", timeout=TIMEOUT)
    res.raise_for_status()
    return res.json()


@mcp.tool()
def get_population_summary() -> dict:
    """창원시 월별 인구(주민등록인구) 요약을 가져옵니다.
    인구 증감 추세, 최근 변화 등. '창원 인구', '손님(모집단) 변화' 맥락이 필요할 때 사용하세요."""
    res = requests.get(f"{BASE_URL}/api/population/summary", timeout=TIMEOUT)
    res.raise_for_status()
    return res.json()


@mcp.tool()
def make_content_plan(industry: str, season: str = "", channel: str = "", product: str = "") -> dict:
    """업종 데이터와 창원 인구 맥락을 반영해 SNS 콘텐츠 기획안을 만들어 돌려줍니다.
    '이번 달 무슨 콘텐츠 올릴까', '홍보 아이디어' 같은 요청에 사용하세요.

    매개변수:
      industry: 업종 — 카페 / 미용/뷰티 / 미용의료 (부분 입력 OK)
      season:  (선택) 시즌 — 예) 할로윈, 연말, 봄
      channel: (선택) 채널 — 예) 인스타, 블로그, 숏폼
      product: (선택) 내 상품/서비스 — 롱테일 키워드·리뷰 확보 아이디어를 여기에 맞춤
    """
    payload = {"industry": industry}
    if season:
        payload["season"] = season
    if channel:
        payload["channel"] = channel
    if product:
        payload["product"] = product
    res = requests.post(f"{BASE_URL}/api/content-plan", json=payload, timeout=TIMEOUT)
    res.raise_for_status()
    return res.json()


if __name__ == "__main__":
    # 표준 입출력(stdio) 방식으로 실행 — Claude 데스크톱이 이 서버를 켜고 대화합니다.
    mcp.run()
