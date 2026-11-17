# scenario 모듈 — 비교할 선택지를 정리하고, 세부 조건을 글로 받습니다. (F02, F03 / 문제1)
# 선택지마다 simulation_log.csv에 한 줄을 만들어 둡니다(실제 결과 3칸은 빈칸).
import csv
from pathlib import Path

from modules.profile import PROFILE_FIELDS

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "simulation_log.csv"
SCENARIO_FIELDS = ["scenario_option", "scenario_hours", "scenario_condition"]
RESULT_FIELDS = ["actual_gpa", "satisfaction", "user_review"]
LOG_FIELDS = PROFILE_FIELDS + SCENARIO_FIELDS + RESULT_FIELDS   # 10개 항목, 칸을 늘리지 않습니다
SUGGESTED_OPTIONS = ["인턴 병행", "학점 집중", "동아리 확대"]
MAX_OPTIONS = 3


def number_text(value) -> str:
    return f"{float(value):g}"


def build_scenarios(items: list) -> list:
    """items: [{"scenario_option", "scenario_hours", "scenario_condition"}, ...]"""
    if not 1 <= len(items) <= MAX_OPTIONS:
        raise ValueError(f"선택지는 1개에서 {MAX_OPTIONS}개까지 입력합니다.")
    scenarios = []
    seen = set()
    for number, item in enumerate(items, start=1):
        option = (item.get("scenario_option") or "").strip()
        hours = item.get("scenario_hours")
        condition = (item.get("scenario_condition") or "").strip()
        if not option:
            raise ValueError(f"선택지 {number}의 이름을 입력해야 합니다.")
        if option in seen:
            raise ValueError(f"선택지 이름 '{option}'이 두 번 들어갔습니다.")
        if hours is None or not 0 <= hours <= 168:
            raise ValueError(f"선택지 {number}의 투입 시간은 0에서 168 사이로 입력해야 합니다.")
        seen.add(option)
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
        raise ValueError(f"{Path(path).name} 파일을 읽을 수 없습니다. 파일을 확인해 주세요.") from error
    if fieldnames and fieldnames != LOG_FIELDS:
        raise ValueError(f"{Path(path).name} 파일의 항목이 10개 항목과 다릅니다. 파일을 확인해 주세요.")
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


def save_plan(profile: dict, scenarios: list, path=LOG_PATH) -> list:
    """학기 초 기록: 같은 학기 · 같은 선택지 줄이 있으면 고쳐 쓰고, 없으면 새 줄을 붙입니다."""
    rows = read_log(path)
    for scenario in scenarios:
        new_row = plan_row(profile, scenario)
        same = [
            row for row in rows
            if row["term"] == new_row["term"] and row["scenario_option"] == new_row["scenario_option"]
        ]
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
