"""콘텐츠 추천 도구 — 업종 데이터(성수기·변동성·관심도) + 창원 인구 맥락을
GPT에 주입해 SNS 콘텐츠·마케팅 기획안을 자동 생성한다. (SNS 대행 영업용)
"""
from fastapi import APIRouter, HTTPException

from config import logger, token_limit
from schemas import ContentPlanRequest
from services.llm import MODEL, get_client
from services.population import build_population_summary, population_summary_to_text
from services.search_trend import load_timing_summary
from services.summary import build_statistics
from services.timing import timing_to_text

router = APIRouter()


@router.post("/api/content-plan")
def content_plan(req: ContentPlanRequest):
    """업종 데이터 + 인구 맥락으로 SNS 콘텐츠 기획안을 만들어 돌려준다."""
    try:
        stats = build_statistics()
        if "message" in stats:
            raise HTTPException(status_code=400, detail="데이터가 없어 기획안을 만들 수 없어요")

        ind = req.industry.strip()
        monthly = stats["monthly"]
        matched = next((k for k in monthly if ind in k or k in ind), None)
        if not matched:
            raise HTTPException(
                status_code=404,
                detail=f"'{ind}' 업종을 찾을 수 없어요. (가능: {', '.join(monthly.keys())})",
            )
        ind = matched
        months = monthly[ind]                       # [{month, avg}, ...]
        peak = max(months, key=lambda m: m["avg"])  # 성수기
        low = min(months, key=lambda m: m["avg"])   # 비수기
        overall_avg = round(sum(m["avg"] for m in months) / len(months), 1)
        std = stats["변동성_표준편차"].get(ind)
        gap = stats["업종간_평균격차"]
        top = stats["최고관심_업종"]

        pop = build_population_summary()
        pop_text = population_summary_to_text(pop) if pop else "- (인구 데이터 없음)"

        # 발행 타이밍 근거(3년 검색관심도) — 없거나 문제가 있어도 기획안은 기존 방식대로 만들어요
        try:
            timing_text = timing_to_text(load_timing_summary(), ind)
        except Exception as e:
            logger.warning("발행 타이밍 근거를 불러오지 못했어요: %s", type(e).__name__)
            timing_text = ""
        timing_block = f"[발행 타이밍 근거 — 3년 검색관심도 분석]\n{timing_text}\n\n" if timing_text else ""

        facts = (
            f"- 업종: {ind}\n"
            f"- 평균 검색관심도: {overall_avg} (전체 최고관심 업종: {top}, 업종간 평균격차: {gap})\n"
            f"- 성수기(가장 높은 달): {peak['month']} ({peak['avg']}) / 비수기(가장 낮은 달): {low['month']} ({low['avg']})\n"
            f"- 변동성(표준편차): {std} (클수록 시즌 영향이 큼)\n"
        )

        user_ask = f"'{ind}' 업종"
        product = (req.product or "").strip()
        prod_text = f"[내 상품/서비스]\n{product}\n\n" if product else "[내 상품/서비스]\n(입력 없음 — 이 업종의 대표 상품 기준으로 작성)\n\n"
        if req.season:
            user_ask += f", 시즌/테마: {req.season}"
        if req.channel:
            user_ask += f", 채널: {req.channel}"

        system_prompt = (
            "당신은 경남 창원 지역 소상공인을 돕는 SNS 콘텐츠·마케팅 기획 전문가입니다. "
            "아래 '네이버 검색 관심도 데이터'와 '창원 인구 추이'를 근거로, 바로 실행 가능한 "
            "콘텐츠 기획안을 제안하되, 각 콘텐츠의 실제 게시 본문(초안)과 구체적 발행 시점까지 작성하세요. 검색 관심도는 매출이 아니라 관심의 흐름이며, 인구와의 "
            "연결은 '참고' 수준으로만 조심스럽게 쓰세요. 한국어 존댓말로, 아래 형식을 지켜 "
            "간결하고 구체적으로 작성하세요.\n\n"
            "[출력 형식]\n"
            "1) 한줄 진단: 이 업종 관심도 흐름을 한 문장으로\n"
            "2) 추천 콘텐츠 3개 — 각 콘텐츠마다 아래를 모두 작성:\n"
            "   · 제목:\n"
            "   · 본문 초안: 실제 게시물에 바로 올릴 수 있는 2~4문장 글(채널 톤에 맞게, 이모지 1~2개 OK)\n"
            "   · 포맷: 릴스·카드뉴스·블로그 등\n"
            "   · 추천 발행 시점: 성수기 월을 반영한 시기 + 추천 요일·시간대(이유 한 줄)\n"
            "   · 해시태그: 3~5개\n"
            "3) 발행 타이밍 요약: 이 업종은 언제(월·요일·시간대) 올리는 게 유리한지 2~3줄\n"
            "4) 창원 맥락 한마디: 인구 흐름을 고려한 조언 1줄\n"
            "5) 롱테일 키워드 후보 6개: '내 상품/서비스'가 주어지면 그것과 직접 관련된 검색어로, 없으면 이 업종의 대표 상품 기준으로 만드세요. "
            "'지역(창원 동네명 가능)+상품+상황·목적'처럼 3어절 이상의 구체적인 검색어여야 하고, 홍보 콘텐츠 제목·본문에 그대로 쓸 수 있어야 합니다. "
            "각 키워드에 [정보형/비교형/방문형] 중 검색 의도를 붙이세요. 검색량·광고 단가·경쟁 강도 수치는 보유 데이터에 없으므로 절대 지어내지 말고, "
            "'경쟁이 상대적으로 낮을 가능성이 있는 후보'라고만 표현하세요. 마지막 줄에 "
            "'※ 실제 검색량·광고 단가는 네이버 검색광고 키워드 도구 등으로 확인 후 선택하세요'를 덧붙이세요.\n"
            "6) 리뷰 확보 아이디어 3개: 실제 손님이 자발적으로 정직한 후기를 남기도록 돕는 방법(예: 결제·수령 시 QR 안내, 방문 후 감사 메시지, "
            "후기 작성에 대한 소소한 감사 혜택 등)을 각각 '실행 방법 + 손님께 보낼 문구 한 줄'로 제시하세요.\n"
            "[리뷰 안전 규칙] 맞구매(서로 상품을 사주고 리뷰 쓰기), 가짜·대행 리뷰, 긍정 후기만 요구하는 방식, 경쟁업체 비방은 절대 추천하지 마세요. "
            "6) 끝에 '맞구매·가짜 리뷰는 플랫폼 정책 위반이며 노출 불이익·처벌 위험이 있어요' 한 줄을 넣고, 혜택을 제공하는 경우 "
            "협찬·대가 제공 사실을 후기에 표시하도록 안내하세요.\n"
            "※ 발행 시점(요일·월·행사 전 발행일)은 '[발행 타이밍 근거]'가 주어지면 그 수치를 우선 사용하고, 근거 수치(예: 주말이 평일의 N배)를 한 줄로 인용하세요. "
            "근거에 '다가오는 행사'가 있으면 그 날짜를 기준으로 '○월 ○일까지 발행'처럼 구체적인 날짜를 쓰세요. "
            "시각(몇 시)은 보유 데이터에 없으니 일반적인 SNS 운영 관행을 참고로 '추천' 톤으로만 쓰고, 근거가 없을 때는 요일·시간대도 단정하지 마세요.\n"
        )
        user_prompt = (
            f"[검색 관심도 데이터]\n{facts}\n"
            f"[창원 인구 요약]\n{pop_text}\n\n"
            f"{timing_block}"
            f"{prod_text}"
            f"위 데이터를 바탕으로 {user_ask} 에 맞는 SNS 콘텐츠 기획안을 만들어 주세요."
        )

        completion = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **token_limit(),
        )
        plan = completion.choices[0].message.content

        return {
            "industry": ind,
            "season": req.season,
            "channel": req.channel,
            "product": product,
            "data_used": {
                "평균관심도": overall_avg,
                "성수기": peak,
                "비수기": low,
                "변동성": std,
                "최고관심업종": top,
                "업종간격차": gap,
            },
            "timing_basis": timing_text or None,
            "plan": plan,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
