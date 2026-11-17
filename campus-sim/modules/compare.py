# compare 모듈 — 선택지를 같은 기준으로 나란히 보여 주고,
# 시간이 모자라는 선택지에 경고를 띄웁니다. (F06, F09 / 문제1, 문제2)


def is_short(scenario_hours, weekly_free_hours) -> bool:
    """투입 시간이 주간 자유 시간을 넘으면 시간 부족입니다."""
    return float(scenario_hours) > float(weekly_free_hours)


def compare(rows: list, weekly_free_hours) -> dict:
    table = []
    warnings = []
    for row in rows:
        short = is_short(row["scenario_hours"], weekly_free_hours)
        table.append({**row, "short": short})
        if short:
            warnings.append(
                f"⚠️ {row['scenario_option']}: 투입 시간 {row['scenario_hours']:g}시간이 "
                f"주간 자유 시간 {float(weekly_free_hours):g}시간을 넘습니다 "
                f"({-row['free_left']:g}시간 부족)."
            )
    return {"rows": table, "warnings": warnings, "weekly_free_hours": float(weekly_free_hours)}


def time_type(row: dict) -> str:
    if row.get("all_study"):
        return "📚 공부"
    if row.get("study"):
        return f"혼합 (📚 공부 {row['study_hours']:g}시간)"
    return "공부 외 활동"


def table_rows(table: dict) -> list:
    """화면에 보여 줄 비교표(같은 기준의 칸)."""
    return [
        {
            "선택지": row["scenario_option"],
            "투입 시간": f"{row['scenario_hours']:g}시간",
            "시간 유형": time_type(row),
            "남는 자유 시간": f"{row['free_left']:g}시간",
            "보정 전 예상 학점": f"{row['base_gpa']:.2f}",
            "내 기록 보정": f"{row.get('personal_adjust', 0):+.2f}",
            "AI 보정": f"{row['adjust']:+.2f}" if row["ai_used"] else "AI 보정 없음",
            "예상 학점": f"{row['expected_gpa']:.2f}",
            "예상 범위": f"{row['range'][0]:.2f} ~ {row['range'][1]:.2f}" if row.get("range") else "—",
            "시간 상태": "⚠️ 시간 부족" if row["short"] else "시간 안에 가능",
        }
        for row in table["rows"]
    ]
