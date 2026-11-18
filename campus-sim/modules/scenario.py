# scenario 모듈 — 비교할 선택지를 정리하고, 세부 조건을 글로 받습니다. (F02, F03 / 문제1)
# 선택지마다 simulation_log.csv에 한 줄을 만들어 둡니다(실제 결과 3칸은 빈칸).
# 한 선택지에 활동을 여러 개 넣으면 scenario_option에 "인턴 병행(15) + 공부(5)"처럼,
# scenario_hours에 합계를 저장합니다(10개 항목을 늘리지 않습니다).
import csv
import io
import re
from pathlib import Path

from modules.profile import PROFILE_FIELDS

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "simulation_log.csv"
SCENARIO_FIELDS = ["scenario_option", "scenario_hours", "scenario_condition"]
RESULT_FIELDS = ["actual_gpa", "satisfaction", "user_review"]
LOG_FIELDS = PROFILE_FIELDS + SCENARIO_FIELDS + RESULT_FIELDS   # 10개 항목, 칸을 늘리지 않습니다
SUGGESTED_OPTIONS = ["인턴 병행", "학점 집중", "동아리 확대"]
# 선택지 화면에서 고를 수 있는 활동 목록(직접 입력도 가능). 공부 활동은 이름에 공부 관련 단어가 있어 자동으로 📚 체크됩니다.
PRESET_STUDY = ["학점 집중", "전공 공부", "시험 준비", "과제 · 팀플", "스터디", "토익 · 어학 공부", "자격증 공부"]
PRESET_OTHER = ["인턴 병행", "아르바이트", "동아리 확대", "학생회", "대외활동 · 공모전", "봉사활동", "운동", "취미 · 휴식"]
PRESET_ACTIVITIES = PRESET_STUDY + PRESET_OTHER
MAX_OPTIONS = 3
MAX_ACTIVITIES = 5          # 한 선택지 안의 활동 수
ACTIVITY_JOIN = " + "
ACTIVITY_RE = re.compile(r"^(.+?)\((\d+(?:\.\d+)?)\)$")

# 활동 유형: 이름에 아래 단어가 있으면 공부 시간으로 봅니다(자동).
# 자동 판단과 다르게 고르면 이름 앞에 표시를 붙여 저장합니다(칸을 늘리지 않습니다).
STUDY_KEYWORDS = ("공부", "학점", "스터디", "복습", "예습", "시험", "과제")
STUDY_MARK = "[공부] "
OTHER_MARK = "[공부 외] "


def split_mark(name) -> tuple:
    """'[공부] 토익' → ('토익', True), '[공부 외] 시험 감독' → ('시험 감독', False), 표시 없으면 (이름, None)"""
    name = str(name or "")
    if name.startswith(STUDY_MARK):
        return name[len(STUDY_MARK):].strip(), True
    if name.startswith(OTHER_MARK):
        return name[len(OTHER_MARK):].strip(), False
    return name.strip(), None


def keyword_study(name) -> bool:
    return any(word in str(name or "") for word in STUDY_KEYWORDS)


def is_study(name) -> bool:
    """직접 고른 유형이 있으면 그것을, 없으면 이름의 단어로 공부 시간인지 판단합니다."""
    clean, forced = split_mark(name)
    return keyword_study(clean) if forced is None else forced


def mark_name(name: str, study=None) -> str:
    """직접 고른 유형이 자동 판단과 다를 때만 이름 앞에 표시를 붙입니다."""
    clean, _ = split_mark(name)
    if study is None or bool(study) == keyword_study(clean):
        return clean
    return (STUDY_MARK if study else OTHER_MARK) + clean


def number_text(value) -> str:
    return f"{float(value):g}"


def encode_activities(activities: list) -> tuple:
    """[(이름, 시간), ...] → (scenario_option, scenario_hours). 활동이 하나면 이름 그대로 저장합니다."""
    if len(activities) == 1:
        name, hours = activities[0]
        return name, float(hours)
    option = ACTIVITY_JOIN.join(f"{name}({number_text(hours)})" for name, hours in activities)
    return option, float(sum(hours for _, hours in activities))


def parse_activities(scenario_option, scenario_hours) -> list:
    """저장된 선택지를 [(이름, 시간), ...]로 풉니다. 조합 형식이 아니면 활동 하나로 봅니다."""
    option, total = str(scenario_option or ""), float(scenario_hours)
    parts = option.split(ACTIVITY_JOIN)
    if len(parts) >= 2:
        matches = [ACTIVITY_RE.match(part.strip()) for part in parts]
        if all(matches):
            activities = [(m.group(1).strip(), float(m.group(2))) for m in matches]
            if abs(sum(hours for _, hours in activities) - total) < 1e-6:
                return activities
    return [(option, total)]


def activities_from_item(number: int, item: dict) -> list:
    """화면에서 받은 활동 목록을 검사해 [(이름, 시간), ...]로 돌려줍니다."""
    rows = item.get("activities")
    if rows is None:   # 활동 목록 없이 이름 · 시간만 받은 경우(이전 방식)
        rows = [{"name": item.get("scenario_option"), "hours": item.get("scenario_hours")}]
    if not 1 <= len(rows) <= MAX_ACTIVITIES:
        raise ValueError(f"선택지 {number}에는 활동을 1개에서 {MAX_ACTIVITIES}개까지 넣을 수 있습니다.")
    activities, names = [], set()
    for row in rows:
        name, forced = split_mark((row.get("name") or "").strip())
        study = row.get("study", forced)
        hours = row.get("hours")
        if not name:
            raise ValueError(f"선택지 {number}의 이름(활동 이름)을 입력해야 합니다.")
        if hours is None or not 0 <= hours <= 168:
            raise ValueError(f"선택지 {number}의 '{name}' 투입 시간은 0에서 168 사이로 입력해야 합니다.")
        if len(rows) > 1 and ("+" in name or ACTIVITY_RE.match(name)):
            raise ValueError(f"선택지 {number}의 활동 이름 '{name}'에는 '+'나 '(숫자)'를 쓸 수 없습니다.")
        if name in names:
            raise ValueError(f"선택지 {number}에 활동 '{name}'이 두 번 들어갔습니다.")
        names.add(name)
        activities.append((mark_name(name, study), float(hours)))
    if sum(hours for _, hours in activities) > 168:
        raise ValueError(f"선택지 {number}의 활동 시간 합계가 일주일(168시간)을 넘습니다.")
    return activities


def build_scenarios(items: list) -> list:
    """items: [{"activities": [{"name", "hours"}, ...], "scenario_condition"}, ...]
    또는 이전 방식 [{"scenario_option", "scenario_hours", "scenario_condition"}, ...]"""
    if not 1 <= len(items) <= MAX_OPTIONS:
        raise ValueError(f"선택지는 1개에서 {MAX_OPTIONS}개까지 입력합니다.")
    scenarios = []
    seen = {}
    for number, item in enumerate(items, start=1):
        option, hours = encode_activities(activities_from_item(number, item))
        condition = (item.get("scenario_condition") or "").strip()
        key = option_key(option, hours)   # 활동 이름이 같으면 시간이 달라도 같은 선택지로 저장되므로 막습니다
        if key in seen:
            raise ValueError(
                f"선택지 {seen[key]}과 선택지 {number}의 활동 구성('{key}')이 같습니다. "
                "시간만 다른 경우는 선택지 하나로 비교하거나 활동 이름을 다르게 적어 주세요."
            )
        seen[key] = number
        scenarios.append(
            {"scenario_option": option, "scenario_hours": float(hours), "scenario_condition": condition}
        )
    return scenarios


def read_log(path=LOG_PATH) -> list:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError(
            f"{Path(path).name} 파일을 읽을 수 없습니다. 🗂️ 기록 관리에서 파일을 초기화하거나 내려받아 둔 CSV를 불러와 주세요."
        ) from error
    if fieldnames and fieldnames != LOG_FIELDS:
        raise ValueError(
            f"{Path(path).name} 파일의 항목이 10개 항목과 다릅니다. "
            "🗂️ 기록 관리에서 파일을 초기화하거나 내려받아 둔 CSV를 불러와 주세요."
        )
    return rows


def write_log(rows: list, path=LOG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def plan_row(profile: dict, scenario: dict) -> dict:
    return {
        "term": profile["term"],
        "current_gpa": number_text(profile["current_gpa"]),
        "course_credits": number_text(profile["course_credits"]),
        "weekly_free_hours": number_text(profile["weekly_free_hours"]),
        "scenario_option": scenario["scenario_option"],
        "scenario_hours": number_text(scenario["scenario_hours"]),
        "scenario_condition": scenario["scenario_condition"],
        "actual_gpa": "",
        "satisfaction": "",
        "user_review": "",
    }


def option_key(scenario_option, scenario_hours) -> str:
    """같은 선택지인지 판단하는 열쇠: 활동 이름만(시간 · 유형 표시 제외). 예: '인턴 병행 + 공부'"""
    try:
        activities = parse_activities(scenario_option, scenario_hours)
    except (TypeError, ValueError):
        return str(scenario_option)
    return ACTIVITY_JOIN.join(split_mark(name)[0] for name, _ in activities)


def same_plan(row: dict, new_row: dict) -> bool:
    return row["term"] == new_row["term"] and option_key(row["scenario_option"], row["scenario_hours"]) == option_key(
        new_row["scenario_option"], new_row["scenario_hours"]
    )


def save_plan(profile: dict, scenarios: list, path=LOG_PATH) -> list:
    """학기 초 기록: 같은 학기 · 같은 선택지(활동 이름이 같으면 시간만 바뀌어도 같은 선택지) 줄이 있으면
    고쳐 쓰고, 없으면 새 줄을 붙입니다."""
    rows = read_log(path)
    for scenario in scenarios:
        new_row = plan_row(profile, scenario)
        same = [row for row in rows if same_plan(row, new_row)]
        if any(row["actual_gpa"] for row in same):
            raise ValueError(
                f"{new_row['term']} 학기의 '{new_row['scenario_option']}'은 이미 실제 결과가 기록되어 고칠 수 없습니다."
            )
        if same:
            same[0].update(new_row)
        else:
            rows.append(new_row)
    write_log(rows, path)
    return [plan_row(profile, scenario) for scenario in scenarios]


def delete_rows(indices, path=LOG_PATH) -> int:
    """고른 줄(줄 번호)만 지우고 지운 줄 수를 돌려줍니다. 되돌릴 수 없습니다."""
    rows = read_log(path)
    targets = set(indices)
    if not targets:
        raise ValueError("지울 기록을 하나 이상 골라야 합니다.")
    if any(not 0 <= index < len(rows) for index in targets):
        raise ValueError("고른 기록을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 시도해 주세요.")
    write_log([row for index, row in enumerate(rows) if index not in targets], path)
    return len(targets)


def clear_log(path=LOG_PATH) -> None:
    """모든 기록을 지우고 항목 이름(첫 줄)만 남깁니다. 되돌릴 수 없습니다."""
    write_log([], path)


def check_row(number: int, row: dict) -> None:
    """불러온 CSV의 한 줄이 이 시스템이 만든 형식인지 검사합니다."""
    where = f"{number}번째 줄"

    def number_in(key, low, high, allow_empty=False):
        text = (row.get(key) or "").strip()
        if allow_empty and text == "":
            return
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"{where}의 {key} 값('{text}')이 숫자가 아닙니다.") from None
        if not low <= value <= high:
            raise ValueError(f"{where}의 {key} 값({text})이 {low:g}~{high:g} 범위를 벗어납니다.")

    if not (row.get("term") or "").strip():
        raise ValueError(f"{where}에 학기(term)가 없습니다.")
    if not (row.get("scenario_option") or "").strip():
        raise ValueError(f"{where}에 선택지(scenario_option)가 없습니다.")
    number_in("current_gpa", 0, 4.5)
    number_in("course_credits", 1, 30)
    number_in("weekly_free_hours", 1, 168)
    number_in("scenario_hours", 0, 168)
    number_in("actual_gpa", 0, 4.5, allow_empty=True)
    number_in("satisfaction", 1, 5, allow_empty=True)
    if (row.get("actual_gpa") or "").strip() and not (row.get("satisfaction") or "").strip():
        raise ValueError(f"{where}에 실제 학점은 있는데 만족도가 없습니다.")


def read_backup(data: bytes) -> list:
    """내려받아 둔 simulation_log.csv 내용을 읽어 검사한 뒤 줄 목록으로 돌려줍니다."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("파일을 읽을 수 없습니다. 이 시스템에서 내려받은 CSV(UTF-8)인지 확인해 주세요.") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))   # 세부 조건 안의 줄바꿈을 지킵니다
    if reader.fieldnames != LOG_FIELDS:
        raise ValueError("파일의 항목이 10개 항목(term ~ user_review)과 다릅니다. 이 시스템에서 내려받은 CSV만 불러올 수 있습니다.")
    rows = [{key: (row.get(key) or "").strip() for key in LOG_FIELDS} for row in reader]
    if not rows:
        raise ValueError("파일에 기록이 한 줄도 없습니다.")
    for number, row in enumerate(rows, start=1):
        check_row(number, row)
    return rows


def import_rows(new_rows: list, mode: str, path=LOG_PATH) -> dict:
    """mode "merge": 지금 기록에 합칩니다. 같은 학기 · 선택지가 있으면 실제 결과가 있는 쪽을 남깁니다.
    mode "replace": 지금 기록을 모두 지우고 파일 내용으로 바꿉니다."""
    if mode == "replace":
        write_log(new_rows, path)
        return {"added": len(new_rows), "updated": 0, "skipped": 0}
    rows = read_log(path)
    added = updated = skipped = 0
    for new_row in new_rows:
        same = [row for row in rows if same_plan(row, new_row)]
        if not same:
            rows.append(new_row)
            added += 1
        elif new_row["actual_gpa"] and not same[0]["actual_gpa"]:
            same[0].update(new_row)
            updated += 1
        else:
            skipped += 1
    write_log(rows, path)
    return {"added": added, "updated": updated, "skipped": skipped}
