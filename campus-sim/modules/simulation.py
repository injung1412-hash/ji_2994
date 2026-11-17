# simulation 모듈 — 남는 시간과 보정 전 예상 학점을 계산식으로 구하고,
# AI가 세부 조건 글과 feedback이 넘긴 지난 학기 기록을 읽어 ±0.3 안에서 보정합니다. (F04, F05, F12 / 문제1)
# AI가 실패하거나 범위를 벗어나면 계산식 결과에 "AI 보정 없음"을 붙입니다.
# 활동 이름에 공부 관련 단어가 있으면 그 시간을 '공부 시간'으로 보고 학점이 오르게 계산합니다.
# 한 선택지에 활동이 여러 개면(예: 인턴 15 + 공부 5) 공부 시간과 공부 외 시간을 나눠 계산합니다.
import configparser
import json
import re
from pathlib import Path

from modules.scenario import STUDY_KEYWORDS, is_study, parse_activities, split_mark   # noqa: F401

try:
    import anthropic
except ImportError:
    anthropic = None

CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_config.ini"
DEFAULT_MODEL = "claude-opus-5-5"
AI_TIMEOUT_SECONDS = 60

# 아래 기준값은 모두 임의로 정한 가정이며, 실제 기록으로 검증하지 않았습니다.
SPARE_RATIO = 0.6       # 자유 시간 중 이만큼은 남아야 학점이 유지된다고 가정
HOUR_WEIGHT = 0.02      # 남는 시간 1시간당 학점 변화
BASE_CREDITS = 18       # 기준 수강 학점
CREDIT_WEIGHT = 0.01    # 기준보다 1학점 많을 때 학점 변화
STUDY_WEIGHT = 0.01     # 공부 시간 1시간당 학점 변화 (공부형 선택지에만 적용)
GPA_MIN, GPA_MAX = 0.0, 4.5
AI_LIMIT = 0.3          # AI 보정 폭 한계
NO_AI = "AI 보정 없음"

# 내 기록 보정: 지난 학기 예측 오차(실제 − 계산식)의 평균을 기록 수에 따라 일부만 반영합니다.
PERSONAL_PRIOR = 2      # 반영 비율 = 기록 수 / (기록 수 + 2) → 1건 1/3, 2건 1/2, 8건 4/5
PERSONAL_LIMIT = 0.3    # 내 기록 보정 폭 한계
# 예상 범위: 기록이 3건 미만이면 기본 폭, 3건 이상이면 보정 뒤 남은 오차의 평균(최소 0.1)
RANGE_DEFAULT = 0.3
RANGE_MIN = 0.1
RANGE_MIN_RECORDS = 3

SYSTEM_PROMPT = """당신은 대학생의 학기 선택지별 예상 학점을 보정하는 도우미입니다.
입력 JSON에는 계산식으로 구한 '보정 전 예상 학점', 지난 학기 예측 오차로 조정한 '내 기록 보정 후 예상 학점',
선택지별 세부 조건 글, 지난 학기 기록이 있습니다. 보정 값은 '내 기록 보정 후 예상 학점'에 더해집니다.
계산식은 투입 시간과 시간 유형만 보고 세부 조건 글과 지난 학기 경험은 반영하지 못합니다. 이 글을 읽고 보정 값을 정하세요.
활동 구성에서 유형이 '공부'인 시간은 계산식이 이미 그만큼 학점을 올려 두었으니, 같은 이유로 또 올리지 마세요.
지난 학기 예측 오차의 크기는 이미 '내 기록 보정'으로 반영했으니, 오차 숫자만 보고 또 보정하지 말고
지난 학기 세부 조건과 자유 평가의 내용(무엇이 힘들었고 무엇이 잘됐는지)을 이번 선택지와 비교해 판단하세요.

규칙:
- 선택지마다 adjust(보정 값)를 -0.3에서 0.3 사이의 숫자로 정합니다. 근거가 없으면 0입니다.
- reason에는 어떤 글을 보고 그렇게 정했는지 "~합니다" 말투의 한국어 한두 문장으로 씁니다.
- 어떤 선택지를 추천하거나 정답으로 단정하지 않습니다.
- 다른 말 없이 아래 형식의 JSON만 답합니다.
{"results": [{"scenario_option": "선택지 이름", "adjust": 0.1, "reason": "이유"}]}"""


def number_text(value) -> str:
    return f"{round(float(value), 2):g}"


def clamp_gpa(value: float) -> float:
    return min(max(value, GPA_MIN), GPA_MAX)


def free_left(weekly_free_hours, scenario_hours) -> float:
    """F04 남는 자유 시간 = 주간 자유 시간 − 투입 시간"""
    return float(weekly_free_hours) - float(scenario_hours)


def split_hours(scenario_option, scenario_hours) -> tuple:
    """(활동 목록, 공부 시간 합, 공부 외 시간 합). 활동: [{"name", "hours", "study"}, ...]"""
    activities = [
        {"name": split_mark(name)[0], "hours": hours, "study": is_study(name)}
        for name, hours in parse_activities(scenario_option, scenario_hours)
    ]
    study = sum(a["hours"] for a in activities if a["study"])
    other = sum(a["hours"] for a in activities if not a["study"])
    return activities, study, other


def base_gpa(current_gpa, course_credits, weekly_free_hours, scenario_hours, scenario_option="") -> tuple:
    """보정 전 예상 학점과 계산 근거를 돌려줍니다. 같은 입력에는 항상 같은 값이 나옵니다.

    - 공부 외 시간(인턴 · 동아리 등): 그만큼 공부할 수 있는 시간이 줄어 학점이 내려갑니다.
    - 공부 시간: 그 시간이 곧 공부라 학점이 오릅니다(공부 외 시간을 빼고 남은 자유 시간까지만 인정).
    """
    gpa, credits, free = float(current_gpa), float(course_credits), float(weekly_free_hours)
    _, study_hours, other = split_hours(scenario_option, scenario_hours)
    study = min(study_hours, max(free - other, 0.0))
    credit_part = (credits - BASE_CREDITS) * CREDIT_WEIGHT
    raw = gpa + (free - other - free * SPARE_RATIO) * HOUR_WEIGHT + study * STUDY_WEIGHT - credit_part
    credit_text = f" − ({number_text(credits)} − {BASE_CREDITS})×{CREDIT_WEIGHT} = {number_text(raw)}"
    if study_hours == 0:      # 공부 외 활동만: 이전과 같은 식
        evidence = (
            f"{number_text(gpa)} + ({number_text(free - other)} − {number_text(free)}×{SPARE_RATIO})×{HOUR_WEIGHT}"
            + credit_text
        )
    elif other == 0:          # 공부만
        evidence = (
            f"{number_text(gpa)} + ({number_text(free)} − {number_text(free)}×{SPARE_RATIO})×{HOUR_WEIGHT}"
            f" + {number_text(study)}×{STUDY_WEIGHT}(공부 시간)" + credit_text
        )
    else:                     # 공부 + 공부 외 활동
        evidence = (
            f"{number_text(gpa)} + ({number_text(free)} − {number_text(other)}(공부 외) − {number_text(free)}×{SPARE_RATIO})"
            f"×{HOUR_WEIGHT} + {number_text(study)}×{STUDY_WEIGHT}(공부 시간)" + credit_text
        )
    if study < study_hours:
        evidence += f" (공부 시간은 남은 자유 시간 {number_text(max(free - other, 0))}시간까지만 인정)"
    value = round(clamp_gpa(raw), 2)
    if not GPA_MIN <= round(raw, 2) <= GPA_MAX:
        evidence += f" → {GPA_MIN}~{GPA_MAX}로 제한 {number_text(value)}"
    return value, evidence


def personal_correction(past_records: list) -> dict:
    """지난 학기 예측 오차로 이번 예측을 얼마나 조정할지 정합니다(AI 없이도 동작)."""
    errors = [float(record["error"]) for record in past_records if record.get("error") is not None]
    count = len(errors)
    if not count:
        return {"value": 0.0, "count": 0, "mean_error": None, "text": "지난 학기 기록이 없어 내 기록 보정은 0입니다."}
    mean = sum(errors) / count
    weight = count / (count + PERSONAL_PRIOR)
    value = round(max(-PERSONAL_LIMIT, min(PERSONAL_LIMIT, mean * weight)), 2)
    text = (
        f"지난 학기 기록 {count}건의 예측 오차 평균 {mean:+.2f} × 반영 비율 {count}/{count + PERSONAL_PRIOR}"
        f" = {value:+.2f}" + (f" (±{PERSONAL_LIMIT}로 제한)" if abs(mean * weight) > PERSONAL_LIMIT else "")
    )
    return {"value": value, "count": count, "mean_error": round(mean, 2), "text": text}


def prediction_range(past_records: list, correction: dict) -> dict:
    """예상 학점에 붙일 범위의 폭(±)."""
    errors = [float(record["error"]) for record in past_records if record.get("error") is not None]
    if len(errors) < RANGE_MIN_RECORDS:
        return {
            "width": RANGE_DEFAULT,
            "text": f"기록이 {RANGE_MIN_RECORDS}건 미만이라 기본 폭 ±{RANGE_DEFAULT}을 씁니다(검증 전 가정).",
        }
    left = sum(abs(error - correction["value"]) for error in errors) / len(errors)
    width = round(max(RANGE_MIN, left), 2)
    return {"width": width, "text": f"내 기록으로 보정한 뒤 남은 오차의 평균 ±{width}를 씁니다(최소 ±{RANGE_MIN})."}


def calculate(profile: dict, scenario: dict, correction: float = 0.0) -> dict:
    hours = float(scenario["scenario_hours"])
    value, evidence = base_gpa(
        profile["current_gpa"], profile["course_credits"], profile["weekly_free_hours"], hours,
        scenario["scenario_option"],
    )
    activities, study_hours, _ = split_hours(scenario["scenario_option"], hours)
    corrected = round(clamp_gpa(value + correction), 2)
    return {
        "scenario_option": scenario["scenario_option"],
        "label": " + ".join(a["name"] for a in activities),
        "activities": activities,
        "study_hours": study_hours,
        "study": study_hours > 0,
        "all_study": all(a["study"] for a in activities),
        "scenario_hours": hours,
        "scenario_condition": scenario.get("scenario_condition", ""),
        "free_left": free_left(profile["weekly_free_hours"], hours),
        "base_gpa": value,
        "evidence": evidence,
        "personal_adjust": round(correction, 2),
        "corrected_gpa": corrected,
        "adjust": None,
        "expected_gpa": corrected,
        "ai_used": False,
        "reason": NO_AI,
    }


def apply_range(rows: list, width: float) -> list:
    for row in rows:
        row["range_width"] = width
        row["range"] = (round(clamp_gpa(row["expected_gpa"] - width), 2), round(clamp_gpa(row["expected_gpa"] + width), 2))
    return rows


def past_text(record: dict) -> dict:
    return {
        "학기": record["term"],
        "선택지": record["scenario_option"],
        "투입 시간": record["scenario_hours"],
        "세부 조건": record["scenario_condition"],
        "계산식 예상 학점": record.get("predicted_gpa"),
        "실제 학점": record["actual_gpa"],
        "만족도(1~5)": record["satisfaction"],
        "자유 평가": record["user_review"],
    }


def build_ai_input(profile: dict, rows: list, past_records: list) -> str:
    """AI에는 예측에 필요한 숫자와 글만 보냅니다(학번 · 이름은 처음부터 받지 않습니다)."""
    data = {
        "이번 학기": {
            "현재 학점": profile["current_gpa"],
            "수강 학점": profile["course_credits"],
            "주간 자유 시간": profile["weekly_free_hours"],
        },
        "선택지": [
            {
                "scenario_option": row["scenario_option"],
                "투입 시간": row["scenario_hours"],
                "활동 구성": [
                    {
                        "활동": a["name"],
                        "주간 시간": a["hours"],
                        "유형": "공부(계산식이 학점을 올림)" if a["study"] else "공부 외 활동(계산식이 학점을 내림)",
                    }
                    for a in row["activities"]
                ],
                "남는 자유 시간": row["free_left"],
                "세부 조건": row["scenario_condition"] or "(없음)",
                "보정 전 예상 학점": row["base_gpa"],
                "내 기록 보정 후 예상 학점": row["corrected_gpa"],
            }
            for row in rows
        ],
        "내 기록 보정": personal_correction(past_records)["text"],
        "지난 학기 기록": [past_text(record) for record in past_records] or "없음(첫 학기)",
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def load_config(path=CONFIG_PATH) -> tuple:
    config = configparser.ConfigParser(interpolation=None)
    try:
        with open(path, encoding="utf-8") as f:
            config.read_file(f)
    except (OSError, UnicodeError, configparser.Error):
        return "", DEFAULT_MODEL
    api_key = config.get("claude", "api_key", fallback="").strip()
    model = config.get("claude", "model", fallback="").strip()
    return api_key, model or DEFAULT_MODEL


def ask_claude(ai_input: str, config_path=CONFIG_PATH) -> str:
    """Claude에게 묻고 답 글을 돌려줍니다. 실패하면 ValueError를 냅니다."""
    if anthropic is None:
        raise ValueError("anthropic 라이브러리가 설치되어 있지 않습니다")
    api_key, model = load_config(config_path)
    if not api_key:
        raise ValueError("ai_config.ini에 API 키가 없습니다")
    client = anthropic.Anthropic(api_key=api_key, timeout=AI_TIMEOUT_SECONDS, max_retries=1)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": ai_input}],
        )
    except anthropic.AuthenticationError as error:
        raise ValueError("API 키가 올바르지 않습니다") from error
    except anthropic.APIConnectionError as error:
        raise ValueError("Claude에 연결하지 못했습니다") from error
    except anthropic.APIError as error:
        raise ValueError(f"Claude 요청에 실패했습니다 ({type(error).__name__})") from error
    if response.stop_reason != "end_turn":
        raise ValueError(f"AI 답변이 완성되지 않았습니다 ({response.stop_reason})")
    return "".join(block.text for block in response.content if block.type == "text")


def parse_ai(text: str) -> dict:
    """AI 답에서 {선택지: (보정 값, 이유)}를 꺼냅니다. 형식이 틀리면 ValueError를 냅니다."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("AI 답이 JSON 형식이 아닙니다")
    try:
        items = json.loads(match.group())["results"]
        return {
            str(item["scenario_option"]): (float(item["adjust"]), str(item.get("reason", "")).strip())
            for item in items
        }
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("AI 답의 형식이 올바르지 않습니다") from error


def apply_ai(rows: list, answers: dict) -> list:
    for row in rows:
        answer = answers.get(row["scenario_option"])
        if answer is None:
            row["reason"] = f"{NO_AI} (AI 답에 이 선택지가 없습니다)"
            continue
        adjust, reason = answer
        if abs(adjust) > AI_LIMIT + 1e-9:
            row["reason"] = f"{NO_AI} (AI 보정 값 {adjust:+g}이 ±{AI_LIMIT}를 벗어나 버렸습니다)"
            continue
        row["adjust"] = round(adjust, 2)
        row["expected_gpa"] = round(clamp_gpa(row["corrected_gpa"] + adjust), 2)
        row["ai_used"] = True
        row["reason"] = reason or "AI가 이유를 적지 않았습니다."
    return rows


def run(profile: dict, scenarios: list, past_records: list = None, ask=None) -> dict:
    """계산식 → 내 기록 보정 → AI 보정(±0.3) → 예상 범위. ask: 테스트할 때 AI 대신 넣는 함수."""
    past_records = past_records or []
    correction = personal_correction(past_records)
    span = prediction_range(past_records, correction)
    rows = [calculate(profile, scenario, correction["value"]) for scenario in scenarios]
    ask = ask or ask_claude
    extra = {"past_count": len(past_records), "personal": correction, "range": span}
    try:
        answers = parse_ai(ask(build_ai_input(profile, rows, past_records)))
    except Exception as error:   # AI가 어떤 이유로 실패해도 계산식 결과는 보여 줍니다 (F12)
        for row in rows:
            row["reason"] = f"{NO_AI} ({error})"
        apply_range(rows, span["width"])
        return {"rows": rows, "ai_status": f"{NO_AI}: {error}. 계산식 결과를 보여 줍니다.", **extra}
    apply_ai(rows, answers)
    apply_range(rows, span["width"])
    used = sum(row["ai_used"] for row in rows)
    status = f"AI가 선택지 {len(rows)}개 중 {used}개를 보정했습니다."
    status += f" 지난 학기 기록 {len(past_records)}건을 함께 읽었습니다." if past_records else " 첫 학기라 세부 조건 글만 읽었습니다."
    return {"rows": rows, "ai_status": status, **extra}
