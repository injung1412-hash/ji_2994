# report 모듈 — 어떤 선택이 어떤 점에서 나은지 짧게 정리합니다. (F10 / 문제1)
# 하나를 정답으로 단정하지 않으며, 결정은 사용자가 합니다.

NOTICE = "추정치이며 결과를 보장하지 않습니다."
DECISION = "결정은 AI가 아니라 사용자가 합니다."


def names(rows: list) -> str:
    return ", ".join(row["scenario_option"] for row in rows)


def best_rows(rows: list, key: str) -> list:
    top = max(row[key] for row in rows)
    return [row for row in rows if row[key] == top]


def option_line(row: dict) -> str:
    """보고서 표의 한 줄: 선택지 | 예상 학점 | 예상 범위 | 남는 시간 | 상태"""
    span = f"{row['range'][0]:.2f}~{row['range'][1]:.2f}" if row.get("range") else "—"
    name = row["scenario_option"].replace("|", "/") + (" 📚" if row.get("study") else "")
    state = f"⚠️ {-row['free_left']:g}시간 부족" if row["short"] else "✓ 가능"
    return f"| {name} | **{row['expected_gpa']:.2f}** | {span} | {row['free_left']:g}시간 | {state} |"


def make_report(table: dict) -> str:
    rows = table["rows"]
    parts = [
        "#### 한눈에 보기",
        "| 선택지 | 예상 학점 | 예상 범위 | 남는 시간 | 시간 |\n|---|---|---|---|---|\n"
        + "\n".join(option_line(row) for row in rows),
    ]
    points = []
    if len(rows) >= 2:
        gpa_rows = best_rows(rows, "expected_gpa")
        time_rows = best_rows(rows, "free_left")
        points.append(f"- 🏆 **학점이 가장 높은 선택지**: {names(gpa_rows)} ({gpa_rows[0]['expected_gpa']:.2f})")
        points.append(f"- 🕒 **시간이 가장 여유로운 선택지**: {names(time_rows)} ({time_rows[0]['free_left']:g}시간 남음)")
    if table["warnings"]:
        points.append("- ⚠️ **시간 부족**: " + ", ".join(
            f"{row['scenario_option']}({-row['free_left']:g}시간)" for row in rows if row["short"]
        ))
    else:
        points.append("- ✅ 모든 선택지가 주간 자유 시간 안에 들어갑니다.")
    parts += ["#### 정리", "\n".join(points)]
    ai_used = any(row["ai_used"] for row in rows)
    parts.append(
        "예상 학점 = 계산식 + 내 기록 보정" + (" + AI 보정(±0.3)" if ai_used else " (AI 보정 없음)")
        + f" · 📚 = 공부 시간 포함\n\n*{NOTICE} {DECISION}*"
    )
    return "\n\n".join(parts)
