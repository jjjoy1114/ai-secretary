"""보너스 과제 A — AI 도구 호출 (Function Calling)용 도구 설명서와 실행기."""
from services.population import build_population_summary, population_summary_to_text
from services.summary import build_statistics, build_summary, summary_to_text

# (1) GPT에게 건네줄 '도구 설명서' — 각 도구를 언제 쓰는지 알려준다
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_search_summary",
            "description": (
                "창원 업종별 '네이버 검색 관심도'(상대지수 0~100) 전체 요약을 돌려준다. "
                "기간, 데이터 개수, 업종별 평균/최대/최소, 최근 추세(증가/감소/유지) 포함. "
                "사용자가 검색 관심도·인기·추세·업종 평균을 물으면 사용한다."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": (
                "업종별 심화 통계를 돌려준다. 월별 평균 추이, 변동성(표준편차), "
                "업종 간 평균 격차, 가장 관심도가 높은 업종. "
                "'변동이 큰/작은', '격차', '어느 업종이 제일', '월별 흐름'을 물으면 사용한다."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_population_summary",
            "description": (
                "창원시 월별 주민등록인구(KOSIS 공공데이터) 요약을 돌려준다. "
                "최근 인구 수와 증감 추세 포함. 사용자가 인구·인구 변화를 물으면 사용한다."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# (2) 도구 이름이 오면 실제 우리 함수를 실행해 결과(문자열)를 돌려준다
def run_agent_tool(name: str) -> str:
    if name == "get_search_summary":
        s = build_summary()
        return summary_to_text(s) if s else "검색 관심도 데이터가 없어요."
    if name == "get_statistics":
        return str(build_statistics())
    if name == "get_population_summary":
        p = build_population_summary()
        return population_summary_to_text(p) if p else "인구 데이터가 없어요."
    return f"'{name}'은(는) 알 수 없는 도구예요."
