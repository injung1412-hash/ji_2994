# counsel 모듈 — 💬 AI 상담: 내 계산 결과를 바탕으로 선택을 함께 고민해 주는 대화 도우미.
# - API 키가 있으면 Claude가 상담합니다(답변은 바로바로 흘러나오게 스트리밍).
# - 키가 없거나 웹 버전이면 계산 결과로 바로 답하는 '기본 상담'으로 동작합니다.
# 상담 대화는 저장하지 않습니다(CSV 10개 항목 유지). 결정은 사용자가 합니다.
from modules import simulation

try:
    import anthropic
except ImportError:
    anthropic = None

MAX_TURNS = 20          # AI에 보내는 최근 대화 수(질문 + 답변)
MAX_TOKENS = 4000

SYSTEM_PROMPT = """당신은 대학생의 학기 시간 배분을 함께 고민해 주는 상담 도우미입니다.
사용자는 '대학생활 시뮬레이션' 앱에서 선택지(인턴 · 공부 · 동아리 등)마다 남는 자유 시간과 예상 학점을 계산했습니다.
'내 계산 결과'에 그 숫자와 지난 학기 말 기록(예상 → 실제 학점, 만족도, 후기)이 있습니다. 둘 중 일부만 있거나 하나도 없을 수 있습니다.

상담 원칙:
- 숫자는 '내 계산 결과'에 있는 것만 인용합니다. 새 예상 학점을 지어내지 말고, 다른 시간으로 다시 계산해 보고 싶다면 앱의 '목표 학점으로 거꾸로 계산'이나 '학기 중 점검'을 써 보라고 안내합니다.
- 기록이 있으면 지난 학기의 오차 · 만족도 · 후기를 근거로 돌아보게 돕고, 아무 정보가 없어도 일반적인 시간 관리 관점에서 상담합니다(이때 숫자는 만들지 않습니다).
- 예상 학점은 검증되지 않은 가정으로 만든 추정치라는 점을 필요할 때 짚어 줍니다.
- 하나를 정답으로 정해 주지 않습니다. 선택지마다 얻는 것과 잃는 것을 나란히 보여 주고, 사용자가 무엇을 더 중요하게 여기는지 물어 스스로 정하도록 돕습니다.
- 학점 말고도 경력, 수입, 체력, 만족도처럼 사용자가 말한 가치를 함께 고려합니다.
- 답은 한국어로, 짧고 구체적으로(대개 6문장 이내) 씁니다. 필요하면 짧은 목록을 씁니다.
- 학번, 실명, 연락처 같은 개인 정보는 묻지 않습니다.
- 사용자가 심한 스트레스, 우울, 극단적인 생각을 말하면 시간 계획보다 그 마음을 먼저 살피고, 학교 학생상담센터나 자살예방 상담전화 109(24시간)처럼 사람에게 도움을 받을 수 있는 곳을 안내합니다."""

QUICK_QUESTIONS = [          # 선택지를 비교했을 때
    "어떤 선택지가 학점에 유리해?",
    "시간이 부족한 선택지가 있어?",
    "목표 학점을 지키려면 어떻게 해야 해?",
    "지난 학기 기록은 어떻게 반영됐어?",
]
RECORD_QUESTIONS = [         # 비교 결과는 없고 학기 말 기록만 있을 때
    "내 지난 기록을 정리해 줘",
    "예측이 얼마나 맞았어?",
    "다음 학기엔 뭘 바꾸면 좋을까?",
]
START_QUESTIONS = [          # 아무것도 입력하지 않았을 때
    "학기 시간 계획은 어떻게 세워?",
    "인턴과 학점, 둘 다 챙길 수 있을까?",
    "요즘 너무 지쳐",
]
CARE_WORDS = ("지쳐", "지친", "우울", "번아웃", "불안", "죽고", "죽을", "너무힘들", "포기하고")


def fmt(value) -> str:
    return f"{round(float(value), 2):g}"


def quick_questions(table: dict = None, records: list = None) -> list:
    """지금 가진 정보(비교 결과 · 기록)에 맞는 빠른 질문"""
    if table:
        return QUICK_QUESTIONS if records else QUICK_QUESTIONS[:3]
    return RECORD_QUESTIONS if records else START_QUESTIONS


def build_context(profile: dict = None, table: dict = None, personal: dict = None, span: dict = None,
                  records: list = None, target: float = None) -> str:
    """AI에 넘길 '내 계산 결과' 요약(숫자와 선택지 이름만, 학번 · 이름은 처음부터 없음).
    프로필 · 선택지 · 기록 중 있는 것만 넣고, 하나도 없어도 상담할 수 있게 그렇다고 적습니다."""
    lines = []
    if profile:
        lines.append(
            f"이번 학기 {profile['term']} · 현재 학점 {fmt(profile['current_gpa'])} · 수강 {profile['course_credits']}학점 · "
            f"주간 자유 시간 {fmt(profile['weekly_free_hours'])}시간"
        )
        if target is not None:
            lines.append(f"목표 학점 {target:.2f}")
    if profile and table:
        for row in table["rows"]:
            acts = ", ".join(f"{a['name']} {fmt(a['hours'])}시간{'(공부)' if a['study'] else ''}" for a in row["activities"])
            text = (
                f"- 선택지 '{row.get('label') or row['scenario_option']}': {acts} / 남는 자유 시간 {fmt(row['free_left'])}시간 / "
                f"예상 학점 {row['expected_gpa']:.2f}"
            )
            if row.get("range"):
                text += f" (범위 {row['range'][0]:.2f}~{row['range'][1]:.2f})"
            if row["short"]:
                text += f" / 시간 {fmt(-row['free_left'])}시간 부족"
            if row["scenario_condition"]:
                text += f" / 세부 조건: {row['scenario_condition']}"
            if target is not None:
                plan = simulation.target_plan(profile, row, target, row.get("personal_adjust", 0))
                text += " / 목표 " + ("달성 예상" if plan["ok"] else f"{fmt(plan['gap'])} 부족")
                if plan["max_other"] is not None and plan["max_other"] >= 0:
                    text += f", 공부 외 활동은 주 {fmt(plan['max_other'])}시간까지"
                if plan["min_study"]:
                    text += f", 공부는 주 {fmt(plan['min_study'])}시간 이상"
            lines.append(text)
    if personal and personal.get("count"):
        lines.append(f"내 기록 보정: {personal['text']}")
    if span and span.get("text") and table:
        lines.append(f"예상 범위: {span['text']}")
    if records:
        lines.append(f"학기 말 기록 {len(records)}건(오래된 순, 최근 10건):")
    for record in (records or [])[-10:]:
        lines.append(
            f"- {record['term']} '{record['scenario_option']}': 계산식 예상 {record['predicted_gpa']:.2f} → "
            f"실제 {float(record['actual_gpa']):g}, 만족도 {record['satisfaction']}/5, 후기: {record['user_review']}"
        )
    if not lines:
        return ("아직 입력한 프로필 · 선택지 · 학기 말 기록이 없습니다. 숫자를 지어내지 말고 일반적인 시간 관리 관점에서 상담하세요. "
                "숫자로 비교해 보고 싶어 하면 앱의 👤 프로필과 🔀 선택지를 안내하세요.")
    if not table:
        lines.append("이번 학기 선택지는 아직 비교하지 않았습니다.")
    return "\n".join(lines)


def ai_ready() -> tuple:
    """(AI 상담 가능 여부, 이유)"""
    if anthropic is None:
        return False, "웹 버전에서는 API 키를 안전하게 숨길 수 없어 AI 대신 계산 결과로 답합니다"
    api_key, _ = simulation.load_config()
    if not api_key:
        return False, "ai_config.ini에 API 키가 없습니다"
    return True, ""


def stream_reply(history: list, context: str, client=None, model: str = None):
    """Claude 상담 답변을 조각(문자열) 단위로 내보냅니다. 실패하면 ValueError를 냅니다.
    history: [{"role": "user" | "assistant", "content": "..."}, ...] — 마지막은 사용자 질문"""
    if anthropic is None:
        raise ValueError("anthropic 라이브러리가 설치되어 있지 않습니다")
    if client is None:
        api_key, model_name = simulation.load_config()
        if not api_key:
            raise ValueError("ai_config.ini에 API 키가 없습니다")
        client = anthropic.Anthropic(api_key=api_key, timeout=simulation.AI_TIMEOUT_SECONDS, max_retries=1)
        model = model or model_name
    model = model or simulation.DEFAULT_MODEL
    request = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        # 고정 안내는 캐시하고, 바뀌는 '내 계산 결과'는 그 뒤에 둡니다.
        "system": [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "내 계산 결과:\n" + context},
        ],
        "messages": history[-MAX_TURNS:],
        "output_config": {"effort": "low"},   # 짧은 상담 답변이라 낮은 노력으로 빠르게
    }
    try:
        try:   # 안전상 거절되면 서버가 다른 모델로 이어서 답하도록(최신 SDK)
            stream = client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
            )
        except TypeError:   # fallbacks를 모르는 옛 SDK
            stream = client.messages.stream(**request)
        with stream as events:
            for text in events.text_stream:
                yield text
            final = events.get_final_message()
    except anthropic.AuthenticationError as error:
        raise ValueError("API 키가 올바르지 않습니다") from error
    except anthropic.APIConnectionError as error:
        raise ValueError("Claude에 연결하지 못했습니다") from error
    except anthropic.APIError as error:
        raise ValueError(f"Claude 요청에 실패했습니다 ({type(error).__name__})") from error
    if final.stop_reason == "refusal":
        yield "\n\n(이 질문에는 답할 수 없습니다. 질문을 바꿔 보세요.)"
    elif final.stop_reason == "max_tokens":
        yield "\n\n(답변이 길어 중간에서 끊겼습니다. 이어서 물어보세요.)"


def records_summary(records: list) -> str:
    """학기 말 기록만으로 만드는 요약(프로필 · 선택지 없이도 동작)"""
    lines = [
        f"- {r['term']} **{r['scenario_option']}**: 예상 {r['predicted_gpa']:.2f} → 실제 {float(r['actual_gpa']):g} "
        f"(오차 {r['error']:+.2f}) · 만족도 {r['satisfaction']}/5"
        for r in records[-5:]
    ]
    mean = sum(r["error"] for r in records) / len(records)
    if abs(mean) < 0.1:
        trend = "계산식 예측이 실제와 거의 맞았어요"
    elif mean < 0:
        trend = f"실제 학점이 계산식보다 평균 {abs(mean):.2f} 낮게 나왔어요"
    else:
        trend = f"실제 학점이 계산식보다 평균 {mean:.2f} 높게 나왔어요"
    liked = max(records, key=lambda r: (int(r["satisfaction"]), float(r["actual_gpa"])))
    text = (f"학기 말 기록 {len(records)}건을 봤어요" + (" (최근 5건)" if len(records) > 5 else "") + ".\n\n"
            + "\n".join(lines) + f"\n\n- {trend}.\n- 만족도가 가장 높았던 건 **{liked['scenario_option']}**"
            f"({liked['term']}, {liked['satisfaction']}/5)이에요.")
    if records[-1].get("user_review"):
        text += f"\n- 가장 최근 후기: “{records[-1]['user_review']}”"
    return text


def next_tip(records: list) -> str:
    mean = sum(r["error"] for r in records) / len(records)
    if mean <= -0.1:
        tip = "지난번엔 생각보다 학점이 덜 나왔으니, 이번엔 공부 시간을 계획보다 조금 여유 있게 잡아 보세요."
    elif mean >= 0.1:
        tip = "지난번엔 생각보다 학점이 잘 나왔으니, 원하는 활동을 조금 더 넣어 볼 여지가 있어요."
    else:
        tip = "예측이 잘 맞았으니 지난번과 비슷한 시간 배분을 기준으로 삼아도 좋아요."
    low = [r for r in records if int(r["satisfaction"]) <= 2]
    if low:
        tip += f" 만족도가 낮았던 선택지(**{low[-1]['scenario_option']}**, {low[-1]['satisfaction']}/5)는 후기를 다시 읽고 무엇이 아쉬웠는지 떠올려 보세요."
    return tip


GENERAL_PLAN = (
    "학기 시간 계획은 이렇게 세워 보세요.\n\n"
    "1. 수업 · 이동 · 잠을 빼고 **일주일에 실제로 쓸 수 있는 자유 시간**을 먼저 셉니다.\n"
    "2. 하고 싶은 활동(인턴 · 동아리 · 알바 · 공부)에 주 몇 시간이 드는지 적습니다.\n"
    "3. 합이 자유 시간을 넘으면 하나를 줄이거나 빼고, 시험 기간에 쓸 여유 시간을 남겨 둡니다.\n\n"
    "👤 프로필과 🔀 선택지에 넣으면 선택지마다 남는 시간과 예상 학점을 숫자로 비교해 드려요."
)
GENERAL_BOTH = (
    "둘 다 챙길 수는 있지만, **주당 시간이 버티는지**가 관건이에요.\n\n"
    "- 인턴 시간 + 공부 시간이 주간 자유 시간을 넘지 않는지 먼저 보세요.\n"
    "- 시험 기간에 근무를 줄일 수 있는지, 근무 요일이 수업과 겹치지 않는지 확인하세요.\n"
    "- 학점 말고 경력 · 수입 · 체력 중 이번 학기에 무엇이 더 중요한지도 정해 두면 고르기 쉬워요.\n\n"
    "🔀 선택지에 '인턴 병행 15 + 공부 5'처럼 넣으면 예상 학점을 계산해 드려요."
)
CARE = (
    "많이 지치셨군요. 이야기해 줘서 고마워요. 시간 계획보다 지금 마음을 먼저 챙기는 게 중요해요.\n\n"
    "- 잠깐이라도 쉬는 시간을 일정에 먼저 넣고, 줄일 수 있는 활동이 있는지 봐요.\n"
    "- 혼자 버티기 힘들면 **학교 학생상담센터**에 이야기해 보세요.\n"
    "- 극단적인 생각이 든다면 지금 바로 **자살예방 상담전화 109**(24시간)에 연락하세요."
)


def offline_reply(question: str, profile: dict = None, table: dict = None, personal: dict = None,
                  records: list = None, target: float = None) -> str:
    """AI 없이 답하는 기본 상담: 비교 결과 → 학기 말 기록 → 일반 조언 순서로, 있는 정보로 답합니다."""
    q = question.replace(" ", "")
    records = records or []
    if any(word in q for word in CARE_WORDS):
        return CARE
    rows = table["rows"] if (profile and table) else []
    name = lambda r: r.get("label") or r["scenario_option"]   # noqa: E731
    about_records = any(w in q for w in ("지난", "기록", "반영", "예측", "맞았", "정리", "다음학기", "바꾸"))

    if rows and not about_records:
        if "목표" in q:
            if target is None:
                return "📊 결과·보고서의 **🎯 목표 학점**에 지키고 싶은 학점을 먼저 넣어 주세요."
            lines = []
            for r in rows:
                plan = simulation.target_plan(profile, r, target, r.get("personal_adjust", 0))
                text = f"- **{name(r)}**: " + ("✓ 달성 예상" if plan["ok"] else f"✗ {fmt(plan['gap'])} 부족")
                if plan["max_other"] is not None and plan["max_other"] >= 0:
                    text += f" · 공부 외 활동은 주 {fmt(plan['max_other'])}시간까지"
                elif plan["max_other"] is not None:
                    text += " · 공부 외 활동을 모두 빼도 어려움"
                if plan["min_study"]:
                    text += f" · 공부는 주 {fmt(plan['min_study'])}시간 이상"
                elif plan["min_study"] == 0 and plan["ok"]:
                    text += " · 추가 공부 없이도 가능"
                lines.append(text)
            return f"목표 학점 {target:.2f} 기준이에요(계산식 + 내 기록 보정, AI 보정 제외).\n\n" + "\n".join(lines)
        if "부족" in q or "시간" in q:
            short = [r for r in rows if r["short"]]
            if not short:
                most = max(rows, key=lambda r: r["free_left"])
                return f"모든 선택지가 주간 자유 시간 안에 들어가요. 여유가 가장 큰 건 **{name(most)}**(남는 시간 {fmt(most['free_left'])}시간)예요."
            return "시간이 모자라는 선택지가 있어요.\n\n" + "\n".join(
                f"- **{name(r)}**: 주 {fmt(-r['free_left'])}시간 부족" for r in short
            ) + "\n\n투입 시간을 줄이거나, 세부 조건(근무 요일 등)을 조정할 수 있는지 살펴보세요."
        if "유리" in q or "학점" in q or "어떤" in q or "뭐" in q:
            ranked = sorted(rows, key=lambda r: -r["expected_gpa"])
            lines = [f"{i}. **{name(r)}** — 예상 학점 {r['expected_gpa']:.2f}"
                     + (f" (범위 {r['range'][0]:.2f}~{r['range'][1]:.2f})" if r.get("range") else "")
                     + f", 남는 자유 시간 {fmt(r['free_left'])}시간" for i, r in enumerate(ranked, 1)]
            return ("예상 학점만 보면 이 순서예요.\n\n" + "\n".join(lines) +
                    "\n\n다만 범위가 겹치면 실제로는 차이가 거의 없을 수 있어요. 학점 말고 경력 · 수입 · 체력 중 무엇이 더 중요한지도 함께 생각해 보세요.")

    if records:
        if "다음" in q or "바꾸" in q or "어떻게" in q:
            return next_tip(records) + "\n\n" + records_summary(records)
        text = records_summary(records)
        if personal and personal.get("count"):
            text += f"\n\n이번 예측에는 {personal['text']}만큼 반영했어요."
        return text + "\n\n" + next_tip(records)
    if about_records:
        return ("아직 학기 말 기록이 없어요. 학기가 끝나면 **📝 학기 말 기록**에 실제 학점과 후기를 남겨 주세요. "
                "기록이 쌓일수록 예측이 내게 맞춰지고, 여기서 지난 학기를 돌아볼 수 있어요.")
    if any(w in q for w in ("인턴", "알바", "동아리", "둘다", "병행")):
        return GENERAL_BOTH
    if rows:
        return ("이 질문은 기본 상담에서 바로 답하기 어려워요. 위의 빠른 질문을 눌러 보세요.\n\n"
                "자유롭게 묻고 답하는 **AI 상담**은 내 컴퓨터에서 `ai_config.ini`에 API 키를 넣으면 쓸 수 있어요.")
    return GENERAL_PLAN
