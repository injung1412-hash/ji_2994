# counsel 모듈 — 💬 AI 상담: 내 계산 결과를 바탕으로 선택을 함께 고민해 주는 대화 도우미.
# - API 키가 있으면 Claude가 상담합니다(답변은 바로바로 흘러나오게 스트리밍).
# - 키가 없거나 웹 버전이면 계산 결과로 바로 답하는 '기본 상담'으로 동작합니다.
# 상담 대화는 저장하지 않습니다(CSV 10개 항목 유지). 결정은 사용자가 합니다.
import re

from modules import scenario, simulation

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
- 질문의 의도(계산 · 비교 · 고민 · 감정)에 맞춰 답하고, 매번 같은 형식을 반복하지 않습니다. 이전 대화를 이어서 답합니다.
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


CARE = (
    "많이 지치셨군요. 이야기해 줘서 고마워요. 시간 계획보다 지금 마음을 먼저 챙기는 게 중요해요.\n\n"
    "- 잠깐이라도 쉬는 시간을 일정에 먼저 넣고, 줄일 수 있는 활동이 있는지 봐요.\n"
    "- 혼자 버티기 힘들면 **학교 학생상담센터**에 이야기해 보세요.\n"
    "- 극단적인 생각이 든다면 지금 바로 **자살예방 상담전화 109**(24시간)에 연락하세요."
)
EXTRA_STUDY = ("토익", "토플", "어학", "자격증", "전공", "독서실")   # 이름만으로는 공부로 안 잡히는 공부형 활동
FOLLOW_UP = ("왜", "더자세히", "자세히", "구체적", "예를들", "그럼", "그러면", "그래서", "어떻게해", "어떡해", "또", "다른방법")
WHATIF = re.compile(r"([가-힣A-Za-z]+)\s*(?:주\s*)?(\d+(?:\.\d+)?)\s*시간")
TIME_WORDS = ("시간", "자유", "주", "하루", "매일", "일주일", "평일", "주말", "한달", "총", "약", "최대", "최소")
PARTICLE = re.compile(r"(을|를|은|는|이|가|로|으로|도|만|하고|랑|이랑|에|하면|할때|해서|하는데|씩)$")
DAILY = ("하루", "매일")


AI_NOTE = "\n\n아무 말이나 자유롭게 주고받는 대화는 **AI 상담**(내 컴퓨터에서 `ai_config.ini`에 API 키)에서 할 수 있어요."


class Ctx:
    """답에 넣을 '내 정보' 묶음"""

    def __init__(self, profile, table, personal, records, target, history):
        self.profile = profile
        self.rows = table["rows"] if (profile and table) else []
        self.personal = personal
        self.records = records or []
        self.target = target
        self.history = history or []
        self.adjust = (personal or {}).get("value", 0.0) if profile else 0.0

    def gpa(self, other=0.0, study=0.0):
        return simulation.gpa_for(self.profile, other, study, self.adjust)

    @property
    def free(self):
        return float(self.profile["weekly_free_hours"])


def name_of(row):
    return row.get("label") or row["scenario_option"]


def study_like(name: str) -> bool:
    return scenario.is_study(name) or any(word in name for word in EXTRA_STUDY)


def hours_line(ctx, name: str, hours=(5, 10, 15, 20)) -> str:
    """'인턴'을 주 5/10/15/20시간 할 때 예상 학점(내 프로필 기준)"""
    if not ctx.profile:
        return ""
    study = study_like(name)
    cells = []
    for h in hours:
        left = ctx.free - h
        cell = f"주 {h}시간 → **{ctx.gpa(0, h) if study else ctx.gpa(h, 0):.2f}**"
        cells.append(cell + (" (시간 부족)" if left < 0 else ""))
    base = ctx.gpa()
    return (f"\n\n📐 내 프로필(현재 {fmt(ctx.profile['current_gpa'])}, 자유 시간 {fmt(ctx.free)}시간)로 계산한 "
            f"**{name}** 시간별 예상 학점: 안 할 때 {base:.2f} · " + " · ".join(cells))


def past_line(ctx, words) -> str:
    """지난 학기 말 기록 중 이 주제와 관련된 것"""
    hits = [r for r in ctx.records if any(w in r["scenario_option"] for w in words)]
    if not hits:
        return ""
    r = hits[-1]
    return (f"\n\n🗂️ 지난 기록: {r['term']} **{r['scenario_option']}** — 예상 {r['predicted_gpa']:.2f} → 실제 "
            f"{float(r['actual_gpa']):g}, 만족도 {r['satisfaction']}/5, “{r['user_review']}”. 그때 무엇이 좋았고 힘들었는지 떠올려 보세요.")


def option_line(ctx, words) -> str:
    """지금 비교 중인 선택지 중 이 주제와 관련된 것"""
    hits = [r for r in ctx.rows if any(w in r["scenario_option"] for w in words)]
    return "".join(
        f"\n\n📊 지금 선택지 **{name_of(r)}**: 남는 시간 {fmt(r['free_left'])}시간, 예상 학점 {r['expected_gpa']:.2f}"
        + (f" (주 {fmt(-r['free_left'])}시간 부족)" if r["short"] else "") + "."
        for r in hits[:2]
    )


def clean_name(raw: str) -> str:
    name = raw
    while len(name) > 2 and PARTICLE.search(name):
        name = PARTICLE.sub("", name)
    return name


def whatif_pairs(question: str) -> list:
    """질문 속 '활동 N시간'을 [(활동, 주당 시간), ...]로. '하루 N시간'은 주 7일로 바꾸고 활동은 질문의 다른 단어에서 찾습니다."""
    pairs = []
    for raw, hours in WHATIF.findall(question):
        name, hours = clean_name(raw), float(hours)
        if name in DAILY:
            words = [clean_name(w) for w in re.findall(r"[가-힣A-Za-z]+", question)]
            acts = [w for w in words if w not in TIME_WORDS and w not in DAILY
                    and (study_like(w) or any(w.startswith(k) for v in ACTIVITY_WORDS.values() for k in v))]
            pairs.append((acts[0] if acts else "활동", hours * 7, hours))
        elif name not in TIME_WORDS:
            pairs.append((name, hours, None))
    return pairs


def whatif_reply(ctx, pairs) -> str:
    acts = [(name, float(hours)) for name, hours, _ in pairs]
    daily = {name: day for name, _, day in pairs if day}
    study = sum(h for n, h in acts if study_like(n))
    other = sum(h for n, h in acts if not study_like(n))
    desc = " + ".join(
        n + ("(공부)" if study_like(n) and "공부" not in n else "")
        + (f" 하루 {fmt(daily[n])}시간(주 {fmt(h)}시간)" if n in daily else f" {fmt(h)}시간") for n, h in acts
    )
    total = study + other
    if total > 168:
        return f"**{desc}**은 합이 주 {fmt(total)}시간이에요. 일주일은 168시간(하루 24시간)뿐이라 계산할 수 없어요. 시간을 다시 확인해 주세요."
    if not ctx.profile:
        return (f"**{desc}** 계획을 하루로 나누면 매일 약 {total / 7:.1f}시간, 평일에만 하면 약 {total / 5:.1f}시간이에요.\n\n"
                "👤 프로필(현재 학점 · 수강 학점 · 자유 시간)을 넣으면 이 계획의 예상 학점과 남는 시간을 바로 계산해 드릴게요.")
    left = ctx.free - total
    value = ctx.gpa(other, study)
    base = ctx.gpa()
    text = (f"**{desc}** 계획을 계산해 봤어요(계산식 + 내 기록 보정, AI 보정 제외).\n\n"
            f"- 예상 학점 **{value:.2f}** (아무것도 안 할 때 {base:.2f}, {value - base:+.2f})\n"
            f"- 남는 자유 시간 **{fmt(left)}시간** (주간 자유 시간 {fmt(ctx.free)}시간)")
    if left < 0:
        text += f"\n- ⚠️ 주 {fmt(-left)}시간이 모자라요. 잠이나 이동 시간을 깎게 되니 시간을 줄이는 걸 권해요."
    if ctx.rows:
        best = max(ctx.rows, key=lambda r: r["expected_gpa"])
        diff = value - best["expected_gpa"]
        text += (f"\n- 지금 선택지 중 예상 학점이 가장 높은 **{name_of(best)}**({best['expected_gpa']:.2f})보다 "
                 + (f"{-diff:.2f} 낮아요" if diff < 0 else f"{diff:.2f} 높아요" if diff > 0 else "같아요"))
    if ctx.target is not None:
        text += f"\n- 목표 학점 {ctx.target:.2f}까지 " + ("✓ 달성 예상" if value >= ctx.target else f"{ctx.target - value:.2f} 부족")
    return text + "\n\n이 계획이 마음에 들면 🔀 선택지에 그대로 넣어 다른 선택지와 나란히 비교해 보세요."


# 주제별 답: (단어들, 첫 답, 이어지는 질문에 대한 답). 함수는 ctx를 받아 문자열을 돌려줍니다.
def t_intern(ctx):
    return ("인턴은 **경력**을 얻는 대신 **공부 시간**을 내주는 선택이에요. 핵심은 주당 몇 시간을 버틸 수 있느냐예요."
            + hours_line(ctx, "인턴") + option_line(ctx, ("인턴",)) + past_line(ctx, ("인턴",))
            + "\n\n이번 인턴에서 가장 얻고 싶은 게 **경력 · 수입 · 진로 확인** 중 무엇인가요? 그에 따라 적당한 시간이 달라져요.")


def m_intern(ctx):
    return ("인턴을 병행한다면 이것부터 확인해 보세요.\n\n"
            "1. 근무 요일 · 시간이 수업과 겹치지 않는지, 시험 기간에 근무를 줄일 수 있는지 미리 협의\n"
            "2. 학점으로 인정되는 현장실습 인턴인지 (학교마다 제도가 달라요 — 학과 사무실에 확인)\n"
            "3. 통근 시간까지 투입 시간에 넣기 — 하루 왕복 1시간이면 주 5시간이 더 들어요\n\n"
            "숫자로 보고 싶으면 \"인턴 15시간 공부 5시간 하면?\"처럼 물어보세요.")


def t_parttime(ctx):
    return ("알바는 **수입**이 분명한 대신 시간이 고정되기 쉬워요. 시급 × 주당 시간으로 한 달 수입을 먼저 계산하고, 그 돈이 꼭 필요한지 보세요."
            + hours_line(ctx, "아르바이트") + option_line(ctx, ("알바", "아르바이트", "과외")) + past_line(ctx, ("알바", "아르바이트", "과외"))
            + "\n\n생활비처럼 꼭 필요한 수입이라면 시간을 줄이기보다 **시험 기간만 근무를 빼는** 쪽을 먼저 알아보세요.")


def m_parttime(ctx):
    return ("알바를 고를 때 비교해 볼 점이에요.\n\n"
            "- **고정 알바**(매주 같은 시간): 계획 세우기 쉽지만 시험 기간에 빼기 어려움\n"
            "- **단기 · 주말 알바**: 시험 기간을 피해 몰아서 할 수 있음\n"
            "- **과외**: 시급이 높아 같은 수입을 적은 시간으로 — 다만 준비 시간도 투입 시간에 넣기")


def t_club(ctx):
    return ("동아리 · 대외활동은 **사람과 경험**을 얻지만, 행사나 공모전 마감 때 시간이 **한꺼번에 몰리는** 게 특징이에요."
            + hours_line(ctx, "동아리") + option_line(ctx, ("동아리", "학생회", "대외", "공모전", "봉사")) + past_line(ctx, ("동아리", "학생회", "대외", "공모전", "봉사"))
            + "\n\n행사 날짜가 시험 기간과 겹치는지 먼저 확인해 보세요.")


def m_club(ctx):
    return ("시간을 줄이면서 활동을 이어 가는 방법이에요.\n\n"
            "- 임원 · 운영진 대신 **일반 부원**으로 — 시간이 크게 줄어요\n"
            "- 활동 여러 개라면 **하나만 남기기** — 가장 만족도 높은 것 위주로\n"
            "- 공모전은 **학기 중 1개**로 제한하고 마감 2주 전엔 다른 일정을 비우기")


def t_exam(ctx):
    text = "시험은 **몇 주 전부터 거꾸로** 계획하는 게 가장 효과적이에요. 과목별로 남은 범위를 적고, 시험 3~4주 전부터 하루 분량을 나눠 보세요."
    text += hours_line(ctx, "시험 공부")
    if ctx.rows:
        heavy = [r for r in ctx.rows if r["free_left"] < 5]
        if heavy:
            text += "\n\n⚠️ 남는 시간이 5시간도 안 되는 선택지: " + ", ".join(f"**{name_of(r)}**" for r in heavy) + " — 시험 기간엔 이 활동을 줄일 수 있는지 확인하세요."
    return text


def m_exam(ctx):
    return ("시험 공부를 구체적으로 나누면 이렇게 할 수 있어요.\n\n"
            "1. 과목별 범위 · 비중을 적고 어려운 과목부터 시간 배정\n"
            "2. 1회독은 시험 3주 전까지, 마지막 1주는 기출 · 오답 위주\n"
            "3. 공부 시간은 '앉아 있던 시간'이 아니라 '실제로 집중한 시간'으로 기록")


def t_recover(ctx):
    text = "성적이 기대보다 낮게 나오면 속상하죠. 한 학기 결과가 전부는 아니니, **원인 하나**만 찾아서 고쳐 봐요."
    if ctx.records:
        r = ctx.records[-1]
        diff = float(r["actual_gpa"]) - r["predicted_gpa"]
        text += (f"\n\n🗂️ 가장 최근 기록은 {r['term']} **{r['scenario_option']}**: 예상 {r['predicted_gpa']:.2f} → 실제 {float(r['actual_gpa']):g} ({diff:+.2f})."
                 + (" 예상보다 낮았으니, 그 학기 활동 시간이 생각보다 많았는지 돌아보세요." if diff < 0 else " 예측보다는 잘 나왔어요."))
    if ctx.profile:
        base = ctx.gpa()
        text += (f"\n\n📐 지금 프로필 기준 아무 활동 없을 때 {base:.2f}, 공부를 주 5시간 더하면 {ctx.gpa(0, 5):.2f}, "
                 f"10시간이면 {ctx.gpa(0, 10):.2f}이에요.")
    return text + "\n\n원인이 시간 부족이었나요, 과목 난이도였나요, 컨디션이었나요?"


def m_recover(ctx):
    text = ("학점을 올리는 현실적인 방법이에요.\n\n"
            "- 재수강 · 성적 대체 제도 확인 (학교마다 규정이 달라요)\n"
            "- 다음 학기 수강 학점을 조금 줄이고 전공에 집중\n"
            "- 공부 외 활동 하나를 줄이고 그 시간을 공부로")
    if ctx.profile:
        p = dict(ctx.profile, course_credits=float(ctx.profile["course_credits"]) - 3)
        text += f"\n\n📐 수강 학점을 3학점 줄이면 계산식상 예상 학점이 {ctx.gpa():.2f} → {simulation.gpa_for(p, 0, 0, ctx.adjust):.2f}가 돼요."
    return text


def t_scholar(ctx):
    text = "장학금 기준 학점은 **학교 · 장학금마다 달라요**(불확실하니 학교 공지에서 꼭 확인하세요). 기준을 알면 그 학점을 목표로 거꾸로 계산할 수 있어요."
    if ctx.target is not None and ctx.rows:
        ok = [name_of(r) for r in ctx.rows if r["expected_gpa"] >= ctx.target]
        text += (f"\n\n🎯 지금 목표 {ctx.target:.2f} 기준으로 " + (f"달성 예상 선택지는 **{', '.join(ok)}**예요." if ok else "달성 예상 선택지가 없어요. 활동 시간을 줄여 보세요."))
    elif ctx.rows:
        text += "\n\n📊 결과의 **🎯 목표** 탭에 장학 기준 학점을 넣으면 선택지마다 활동을 몇 시간까지 해도 되는지 알려 드려요."
    else:
        text += "\n\n선택지를 비교한 뒤 목표 학점에 기준을 넣어 보세요."
    return text


def t_cert(ctx):
    return ("토익 · 자격증 공부는 학점과 직접 상관은 없지만 **공부형 활동**이라 앱에서는 📚 공부로 체크하면 돼요. "
            "시험 날짜가 정해져 있으니 **학기 중 시험과 겹치지 않는 회차**를 고르는 게 중요해요."
            + hours_line(ctx, "토익 공부", (3, 5, 8, 10))
            + "\n\n이번 학기에 꼭 따야 하나요, 방학으로 미룰 수 있나요? 미룰 수 있다면 학기 중엔 전공에 집중하는 것도 방법이에요.")


def t_health(ctx):
    text = ("잠과 체력은 모든 계획의 바탕이에요. 시간이 모자랄 때 **잠부터 줄이면** 집중력이 떨어져 결국 공부 효율이 내려가요."
            "\n\n- 하루 7시간 안팎 수면을 먼저 고정\n- 운동은 주 2~3번, 30분이라도 꾸준히\n- 피곤한 주에는 활동 하나를 과감히 빼기")
    if ctx.profile:
        text += f"\n\n📐 운동을 주 3시간 하면 남는 자유 시간은 {fmt(ctx.free - 3)}시간, 계산식상 예상 학점은 {ctx.gpa():.2f} → {ctx.gpa(3, 0):.2f}로 차이가 작아요."
    return text


def t_procrast(ctx):
    return ("미루는 건 의지 문제라기보다 **할 일이 너무 크게 보여서**인 경우가 많아요.\n\n"
            "1. 할 일을 25분 안에 끝낼 크기로 쪼개기\n2. 25분 집중 + 5분 휴식(포모도로)으로 시작만 하기\n"
            "3. 휴대폰은 다른 방에 두거나 앱 제한 걸기\n\n오늘 바로 할 수 있는 가장 작은 일 하나는 뭔가요?")


def t_credits(ctx):
    if not ctx.profile:
        return "수강 학점은 많을수록 수업 · 과제 시간이 늘어요. 이 앱은 18학점을 기준으로, 1학점 많을 때마다 예상 학점을 0.01 낮게 봐요(검증 전 가정). 👤 프로필을 넣으면 내 경우로 계산해 드릴게요."
    c = float(ctx.profile["course_credits"])
    lines = []
    for d in (-3, 0, 3):
        p = dict(ctx.profile, course_credits=c + d)
        lines.append(f"{fmt(c + d)}학점 → {simulation.gpa_for(p, 0, 0, ctx.adjust):.2f}")
    return (f"지금 {fmt(c)}학점을 듣고 있어요. 계산식(18학점 기준, 1학점당 0.01, 검증 전 가정)으로 보면 " + " · ".join(lines) + "이에요."
            "\n\n다만 수강 학점을 줄이면 수업 시간이 줄어 **자유 시간이 늘어나는** 효과가 더 커요. 줄이면 👤 프로필의 자유 시간도 함께 늘려서 다시 계산해 보세요.")


def t_leave(ctx):
    return ("휴학은 쉬는 게 목적인지, 다른 걸 하려는 건지(인턴 · 시험 준비 · 돈 모으기)에 따라 답이 달라요.\n\n"
            "- 목적과 휴학 뒤 계획을 한 줄로 적어 보기\n- 등록금 · 장학금 · 졸업 시기에 미치는 영향 확인 (학교 학사 규정 — 학교마다 다름)\n"
            "- 학기를 다니면서 활동을 줄이는 방법과 비교하기\n\n휴학하고 싶은 가장 큰 이유가 뭐예요?")


def t_career(ctx):
    text = ("진로가 정해져 있으면 **거꾸로** 계획하면 돼요: 졸업 때 필요한 것(학점 · 경력 · 자격) → 이번 학기에 할 것 하나.\n\n"
            "- 취업: 직무 관련 인턴 · 프로젝트 경험이 학점보다 크게 작용하는 경우가 많아요\n"
            "- 대학원: 전공 학점과 교수님과의 연구 경험이 중요해요\n- 아직 모르겠다면: 짧게 여러 가지를 경험해 보는 학기로")
    if ctx.rows:
        text += "\n\n지금 선택지 중 진로에 가장 가까운 건 어떤 거예요? 그걸 기준으로 학점 차이를 감수할 만한지 같이 볼게요."
    return text


def t_plan(ctx):
    text = ("학기 시간 계획은 이렇게 세워 보세요.\n\n"
            "1. 수업 · 이동 · 잠을 빼고 **일주일에 실제로 쓸 수 있는 자유 시간**을 셉니다.\n"
            "2. 하고 싶은 활동에 주 몇 시간이 드는지 적습니다.\n"
            "3. 합이 자유 시간을 넘으면 하나를 줄이고, 시험 기간용 여유를 남겨 둡니다.")
    if ctx.profile:
        text += (f"\n\n📐 내 자유 시간은 주 {fmt(ctx.free)}시간, 하루 약 {ctx.free / 7:.1f}시간이에요. "
                 f"계산식은 그중 {int(simulation.SPARE_RATIO * 100)}%({fmt(ctx.free * simulation.SPARE_RATIO)}시간)는 남겨야 학점이 유지된다고 봐요(가정).")
    else:
        text += "\n\n👤 프로필과 🔀 선택지에 넣으면 선택지마다 남는 시간과 예상 학점을 숫자로 비교해 드려요."
    return text


def t_decide(ctx):
    if not ctx.rows:
        return ("고르기 어려울 땐 이렇게 해 보세요.\n\n1. 이번 학기에 가장 중요한 것 하나(학점 · 경력 · 수입 · 체력)를 정하기\n"
                "2. 선택지마다 그걸 얼마나 얻는지 점수 매기기\n3. 시간이 자유 시간을 넘는 선택지는 빼기\n\n"
                "🔀 선택지에 후보를 넣으면 이 과정을 숫자로 같이 해 볼 수 있어요.")
    best = max(ctx.rows, key=lambda r: r["expected_gpa"])
    lines = []
    for r in ctx.rows:
        others = [a["name"] for a in r["activities"] if not a["study"]]
        gain = ", ".join(others) + " 경험" if others else "공부 시간"
        cost = f"학점 {r['expected_gpa'] - best['expected_gpa']:+.2f}" if r is not best else "예상 학점 가장 높음"
        lines.append(f"- **{name_of(r)}** — 얻는 것: {gain} · 대가: {cost}, 남는 시간 {fmt(r['free_left'])}시간" + (" ⚠️ 시간 부족" if r["short"] else ""))
    return ("고민되는 선택지를 얻는 것과 대가로 나눠 봤어요.\n\n" + "\n".join(lines)
            + "\n\n이번 학기에 **학점 · 경력 · 수입 · 체력** 중 하나만 고른다면 뭐예요? 그 답이 가장 맞는 선택지를 알려 줘요.")


ACTIVITY_WORDS = {
    "인턴": ("인턴",), "알바": ("알바", "아르바이트", "과외"), "동아리": ("동아리", "학생회", "대외활동", "공모전", "봉사"),
    "공부": ("공부", "학점집중", "스터디"), "토익": ("토익", "자격증", "어학"), "운동": ("운동",),
}


def t_compare(ctx, names):
    if not ctx.profile:
        return (f"**{' vs '.join(names)}** — 같은 시간을 쓴다고 하면 공부형은 학점이 오르고, 공부 외 활동은 그만큼 공부 시간이 줄어요. "
                "👤 프로필을 넣으면 같은 시간 기준으로 예상 학점을 나란히 계산해 드릴게요.")
    rows = []
    for n in names:
        hit = [r for r in ctx.rows if any(w in r["scenario_option"] for w in ACTIVITY_WORDS[n])]
        if hit:
            r = hit[0]
            rows.append(f"- **{name_of(r)}** (내 선택지): 예상 {r['expected_gpa']:.2f}, 남는 시간 {fmt(r['free_left'])}시간")
        else:
            v = ctx.gpa(0, 10) if study_like(n) else ctx.gpa(10, 0)
            rows.append(f"- **{n}** 주 10시간이라면: 예상 {v:.2f}, 남는 시간 {fmt(ctx.free - 10)}시간")
    return ("둘을 나란히 놓고 보면 이래요.\n\n" + "\n".join(rows)
            + "\n\n예상 학점은 ±0.3 정도 틀릴 수 있는 추정치라, 차이가 작다면 **어느 쪽이 이번 학기 목표(경력 · 수입 · 사람 · 학점)에 더 가까운지**로 고르세요.")


TOPICS = [   # 위에서부터 먼저 맞는 주제로 답합니다
    ("scholar", ("장학",), t_scholar, None),
    ("recover", ("망쳤", "망했", "떨어졌", "떨어질", "낮게나", "회복", "올리고", "올리려", "성적이안", "학점이안"), t_recover, m_recover),
    ("leave", ("휴학",), t_leave, None),
    ("career", ("진로", "취업", "대학원", "스펙", "졸업후"), t_career, None),
    ("cert", ("토익", "토플", "자격증", "어학"), t_cert, None),
    ("intern", ("인턴",), t_intern, m_intern),
    ("parttime", ("알바", "아르바이트", "과외", "돈", "생활비"), t_parttime, m_parttime),
    ("club", ("동아리", "학생회", "대외활동", "공모전", "봉사"), t_club, m_club),
    ("exam", ("시험", "중간고사", "기말", "벼락", "공부"), t_exam, m_exam),
    ("health", ("운동", "잠을", "잠이", "잠못", "잠자", "수면", "건강", "체력", "피곤"), t_health, None),
    ("procrast", ("미루", "미뤄", "미룸", "집중이", "집중을", "의지", "게을", "폰", "유튜브"), t_procrast, None),
    ("credits", ("수강", "몇학점", "학점을많이", "학점을줄", "학점많"), t_credits, None),
    ("decide", ("고민", "결정", "모르겠", "골라", "뭘해야", "뭐하지", "추천", "선택해"), t_decide, None),
    ("plan", ("계획", "시간관리", "시간표", "일정", "시간을어떻게", "시간배분"), t_plan, None),
]


def topic_of(q: str):
    for key, words, first, more in TOPICS:
        if any(w in q for w in words):
            return key, first, more
    return None


def offline_reply(question: str, profile: dict = None, table: dict = None, personal: dict = None,
                  records: list = None, target: float = None, history: list = None) -> str:
    """AI 없이 답하는 기본 상담. 질문의 주제 · 숫자와 내 정보(프로필 · 선택지 · 기록 · 이전 대화)에 맞춰 답을 만듭니다."""
    ctx = Ctx(profile, table, personal, records, target, history)
    q = question.replace(" ", "")
    rows = ctx.rows

    if any(word in q for word in CARE_WORDS):
        return CARE
    pairs = whatif_pairs(question)
    if pairs and not any(w in q for w in ("자유시간이", "잠을")):
        return whatif_reply(ctx, pairs)
    if any(w in q for w in ("안녕", "반가", "하이")) and len(q) <= 10:
        hello = "안녕하세요! 학기 시간 배분 고민을 같이 정리해 드릴게요."
        if rows:
            return hello + f" 지금 선택지 {len(rows)}개를 비교해 두셨네요. 어떤 점이 가장 고민돼요?"
        return hello + (f" 학기 말 기록 {len(ctx.records)}건도 참고할게요." if ctx.records else "") + " 요즘 어떤 고민이 있어요?"
    if any(w in q for w in ("고마", "감사", "땡큐")) and len(q) <= 12 and not topic_of(q):
        return "도움이 됐다니 다행이에요. 결정은 언제든 바꿀 수 있으니, 학기 중간에 ⏱️ 학기 중 점검으로 한 번 더 확인해 보세요."

    about_records = any(w in q for w in ("지난학기", "지난번", "지난기록", "기록", "반영", "예측", "맞았", "다음학기"))
    if about_records:
        if ctx.records:
            if "다음" in q or "바꾸" in q:
                return next_tip(ctx.records) + "\n\n" + records_summary(ctx.records)
            text = records_summary(ctx.records)
            if personal and personal.get("count") and profile:
                text += f"\n\n이번 예측에는 {personal['text']}만큼 반영했어요."
            return text + "\n\n" + next_tip(ctx.records)
        return ("아직 학기 말 기록이 없어요. 학기가 끝나면 **📝 학기 말 기록**에 실제 학점과 후기를 남겨 주세요. "
                "기록이 쌓일수록 예측이 내게 맞춰지고, 여기서 지난 학기를 돌아볼 수 있어요.")

    if rows and "목표" in q:
        if target is None:
            return "📊 결과의 **🎯 목표** 탭에 지키고 싶은 학점을 먼저 넣어 주세요."
        lines = []
        for r in rows:
            plan = simulation.target_plan(profile, r, target, r.get("personal_adjust", 0))
            text = f"- **{name_of(r)}**: " + ("✓ 달성 예상" if plan["ok"] else f"✗ {fmt(plan['gap'])} 부족")
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
    found = topic_of(q)
    if rows and any(w in q for w in ("부족", "모자", "빠듯")) and ("선택지" in q or ("시간" in q and not found)):
        short = [r for r in rows if r["short"]]
        if not short:
            most = max(rows, key=lambda r: r["free_left"])
            least = min(rows, key=lambda r: r["free_left"])
            return (f"모든 선택지가 주간 자유 시간 안에 들어가요.\n\n- 여유가 가장 큰 선택지: **{name_of(most)}** (주 {fmt(most['free_left'])}시간 남음)\n"
                    f"- 가장 빠듯한 선택지: **{name_of(least)}** (주 {fmt(least['free_left'])}시간 남음)")
        return "시간이 모자라는 선택지가 있어요.\n\n" + "\n".join(
            f"- **{name_of(r)}**: 주 {fmt(-r['free_left'])}시간 부족 → 활동을 {fmt(-r['free_left'])}시간 줄이면 딱 맞아요" for r in short
        ) + "\n\n세부 조건(근무 요일 등)을 조정할 수 있는지도 살펴보세요."
    if rows and (any(w in q for w in ("유리", "어떤선택지", "선택지중", "뭐가좋")) or
                 (not found and "학점" in q and any(w in q for w in ("제일", "가장", "높")))):
        ranked = sorted(rows, key=lambda r: -r["expected_gpa"])
        lines = [f"{i}. **{name_of(r)}** — 예상 학점 {r['expected_gpa']:.2f}"
                 + (f" (범위 {r['range'][0]:.2f}~{r['range'][1]:.2f})" if r.get("range") else "")
                 + f", 남는 자유 시간 {fmt(r['free_left'])}시간" for i, r in enumerate(ranked, 1)]
        gap = ranked[0]["expected_gpa"] - ranked[-1]["expected_gpa"]
        note = ("1등과 꼴등 차이가 {:.2f}로 작아서, 학점보다는 경력 · 수입 · 체력으로 고르는 게 나을 수 있어요.".format(gap) if gap < 0.15
                else "차이가 {:.2f}로 꽤 커요. 학점이 중요하다면 위쪽 선택지를, 다른 가치가 중요하다면 그 대가로 학점이 얼마나 내려가는지 받아들일 수 있는지 보세요.".format(gap))
        return "예상 학점만 보면 이 순서예요.\n\n" + "\n".join(lines) + "\n\n" + note

    named = [n for n, words in ACTIVITY_WORDS.items() if any(w in q for w in words)]
    if len(named) >= 2 and any(w in q for w in ("vs", "중에", "중", "둘중", "비교", "뭐가나", "어느", "아니면", "랑", "이랑", "과", "와")) \
            and not any(w in q for w in ("둘다", "같이", "병행")):
        return t_compare(ctx, named[:2])

    if found:
        return found[1](ctx)

    # 이어지는 질문(왜? 더 자세히?)이면 바로 앞 질문의 주제로 더 깊게 답합니다
    if len(q) <= 15 and any(w in q for w in FOLLOW_UP):
        previous = [m["content"].replace(" ", "") for m in ctx.history if m["role"] == "user"][:-1]
        for prev in reversed(previous):
            before = topic_of(prev)
            if before:
                return (before[2] or before[1])(ctx)
        return "어떤 부분이 더 궁금한지 조금만 더 적어 주세요. 예: \"인턴을 하면 시간이 얼마나 남아?\""

    if rows:
        if "학점" in q or "성적" in q:
            return t_decide(ctx)
        return ("질문에서 주제를 잘 찾지 못했어요. 이런 식으로 물어보면 내 숫자로 답할게요.\n\n"
                "- **\"인턴 10시간 공부 5시간 하면?\"**처럼 활동과 시간을 함께 — 예상 학점을 바로 계산\n"
                "- **\"고민돼\"** — 선택지마다 얻는 것과 대가 정리\n- **\"시험 기간엔 어떻게 해?\"**, **\"장학금 지키려면?\"**" + AI_NOTE)
    if "선택지" in q or "유리" in q or "부족" in q:
        return ("아직 비교한 선택지가 없어서 숫자로는 답하기 어려워요. 👤 프로필 → 🔀 선택지에 후보(예: 인턴 병행 15시간, 학점 집중 5시간)를 넣으면 "
                "예상 학점 순위 · 시간 부족 여부를 바로 알려 드려요.\n\n지금 떠오르는 후보를 \"인턴 15시간 하면?\"처럼 물어봐도 돼요.")
    if "학점" in q or "성적" in q:
        return t_plan(ctx) if not profile else t_credits(ctx)
    return ("어떤 고민인지 조금 더 알려 주세요. 이런 주제라면 바로 답할 수 있어요.\n\n"
            "- 인턴 · 알바 · 동아리 · 토익 · 시험 · 장학금 · 휴학 · 진로 · 미루는 습관 · 체력\n"
            "- **\"알바 12시간 하면?\"**처럼 활동과 시간을 적으면 하루 몇 시간인지(프로필이 있으면 예상 학점까지) 계산해요\n"
            + ("- **\"지난 기록 정리해 줘\"** — 학기 말 기록을 돌아봐요" if ctx.records else "- 👤 프로필을 넣으면 답에 내 숫자가 들어가요") + AI_NOTE)
