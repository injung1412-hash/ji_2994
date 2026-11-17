# AI 대학생활 시뮬레이션 시스템 — 실행: python3 app.py
# profile → scenario → simulation → compare → report → (학기 말) feedback → 다음 학기 simulation
import subprocess
import sys
import threading
import webbrowser

import streamlit as st


if __name__ == "__main__" and not st.runtime.exists():
    PORT = 8501
    threading.Timer(3, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", __file__,
            "--server.port", str(PORT),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ]
    )
    sys.exit()


from modules import compare as compare_mod
from modules import feedback as feedback_mod
from modules import profile as profile_mod
from modules import report as report_mod
from modules import scenario as scenario_mod
from modules import simulation as simulation_mod


APP_TITLE = "AI 대학생활 시뮬레이션 시스템"
MENUS = ["🏠 홈", "👤 프로필", "🔀 선택지", "📊 결과·보고서", "📝 학기 말 기록"]

st.set_page_config(page_title=APP_TITLE, page_icon="🎓", layout="wide")

for key, default in [("profile", None), ("scenarios", []), ("table", None), ("ai_status", "")]:
    if key not in st.session_state:
        st.session_state[key] = default


def go_to(target: str, message: str = None) -> None:
    st.session_state.next_menu = target
    st.session_state.scroll_to_top = True
    if message:
        st.session_state.flash_message = message
    st.rerun()


def run_simulation() -> None:
    """선택지를 저장하면 바로 시뮬레이션 → 비교까지 이어서 실행합니다."""
    profile = st.session_state.profile
    past = feedback_mod.past_records(profile["term"])
    with st.spinner("예상 학점을 계산하고 AI 보정을 받는 중입니다…"):
        result = simulation_mod.run(profile, st.session_state.scenarios, past)
    st.session_state.table = compare_mod.compare(result["rows"], profile["weekly_free_hours"])
    st.session_state.ai_status = result["ai_status"]


if "next_menu" in st.session_state:
    st.session_state.menu = st.session_state.pop("next_menu")

with st.sidebar:
    st.title("🎓 " + APP_TITLE)
    menu = st.radio("메뉴", MENUS, key="menu")
    st.divider()
    st.caption("profile → scenario → simulation → compare → report → feedback")
    st.caption("기록 파일: data/simulation_log.csv")

if st.session_state.pop("scroll_to_top", False):
    st.html(
        "<script>document.querySelector('[data-testid=\"stMain\"]').scrollTo(0, 0);</script>",
        unsafe_allow_javascript=True,
    )

if "flash_message" in st.session_state:
    st.success(st.session_state.pop("flash_message"))


if menu == "🏠 홈":
    st.header("🏠 홈")
    st.write(
        "학기 초에 인턴 병행 · 학점 집중 · 동아리 확대 중 어디에 시간을 쓸지 고민될 때, "
        "선택지마다 **남는 자유 시간**과 **예상 학점**을 같은 기준으로 비교해 보여 줍니다."
    )
    st.info(
        "① 프로필 입력 → ② 선택지 입력 → ③ 비교표와 보고서 확인 → (학기 말) ④ 실제 결과 기록\n\n"
        "학기 말에 기록한 결과는 다음 학기 예측에 반영됩니다."
    )
    st.caption("결정은 시스템이 아니라 내가 합니다. " + report_mod.NOTICE)

    c1, c2, c3 = st.columns(3)
    c1.metric("프로필", "입력됨" if st.session_state.profile else "미입력")
    c2.metric("선택지 수", len(st.session_state.scenarios))
    c3.metric("기록된 학기 결과", len(feedback_mod.history()))

    if st.session_state.table is not None:
        target = ("▶ 결과 보기", "📊 결과·보고서")
    elif st.session_state.profile:
        target = ("▶ 이어서 선택지 입력", "🔀 선택지")
    else:
        target = ("▶ 시작하기", "👤 프로필")
    if st.button(target[0], type="primary"):
        go_to(target[1])


elif menu == "👤 프로필":
    st.header("👤 ① 이번 학기 내 상황")
    st.caption("학번 · 실명 · 가구 소득은 받지 않습니다.")
    p = st.session_state.profile or {}
    with st.form("profile_form"):
        term = st.text_input("학기", p.get("term", ""), placeholder="예: 2026-2")
        c1, c2, c3 = st.columns(3)
        gpa = c1.number_input("현재 학점 (0.0~4.5)", 0.0, 4.5, p.get("current_gpa"), step=0.1, placeholder="예: 3.8")
        credits = c2.number_input("이번 학기 수강 학점", 1, 30, p.get("course_credits"), placeholder="예: 18")
        free = c3.number_input(
            "주간 자유 시간 (수업 외, 시간)", 1.0, 168.0, p.get("weekly_free_hours"), step=1.0, placeholder="예: 25"
        )
        submitted = st.form_submit_button("저장하고 선택지 입력으로 ▶", type="primary")
    if submitted:
        try:
            st.session_state.profile = profile_mod.build_profile(term, gpa, credits, free)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.table = None
            go_to("🔀 선택지", "프로필을 저장했습니다. 비교할 선택지를 입력하세요.")


elif menu == "🔀 선택지":
    st.header("🔀 ② 비교할 선택지")
    profile = st.session_state.profile
    if not profile:
        st.warning("먼저 프로필을 입력하세요.")
        if st.button("👤 프로필 입력하러 가기", type="primary"):
            go_to("👤 프로필")
        st.stop()

    st.caption(
        f"{profile['term']} 학기 · 현재 학점 {profile['current_gpa']:g} · 수강 {profile['course_credits']}학점 · "
        f"주간 자유 시간 {profile['weekly_free_hours']:g}시간"
    )
    saved = st.session_state.scenarios
    count = st.radio("선택지 수", [1, 2, 3], index=len(saved) - 1 if saved else 2, horizontal=True)
    with st.form("scenario_form"):
        items = []
        for i in range(count):
            old = saved[i] if i < len(saved) else {}
            st.subheader(f"선택지 {i + 1}")
            c1, c2 = st.columns([2, 1])
            option = c1.text_input(
                "선택지 이름", old.get("scenario_option", scenario_mod.SUGGESTED_OPTIONS[i]), key=f"opt{i}"
            )
            hours = c2.number_input(
                "주간 투입 시간", 0.0, 168.0, old.get("scenario_hours"), step=1.0, key=f"hrs{i}", placeholder="예: 15"
            )
            condition = st.text_area(
                "세부 조건 (글)", old.get("scenario_condition", ""), key=f"cond{i}", height=70,
                placeholder="예: 주 3일 근무, 출퇴근 왕복 1시간, 시험 기간에도 근무",
            )
            items.append({"scenario_option": option, "scenario_hours": hours, "scenario_condition": condition})
        submitted = st.form_submit_button("저장하고 시뮬레이션 실행 ▶", type="primary")
    if submitted:
        try:
            scenarios = scenario_mod.build_scenarios(items)
            scenario_mod.save_plan(profile, scenarios)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.scenarios = scenarios
            run_simulation()
            go_to("📊 결과·보고서", "선택지를 simulation_log.csv에 기록하고 시뮬레이션을 실행했습니다.")


elif menu == "📊 결과·보고서":
    st.header("📊 ③ 선택지 비교와 보고서")
    table = st.session_state.table
    if table is None:
        st.warning("아직 시뮬레이션 결과가 없습니다. 선택지를 먼저 입력하세요.")
        if st.button("🔀 선택지 입력하러 가기", type="primary"):
            go_to("🔀 선택지")
        st.stop()

    status = st.session_state.ai_status
    (st.warning if status.startswith(simulation_mod.NO_AI) else st.info)(status)
    for warning in table["warnings"]:
        st.error(warning)

    st.subheader("비교표")
    st.dataframe(compare_mod.table_rows(table), hide_index=True, use_container_width=True)

    st.subheader("계산 근거와 보정 이유")
    for row in table["rows"]:
        with st.expander(row["scenario_option"]):
            st.write(f"**남는 자유 시간**: {table['weekly_free_hours']:g} − {row['scenario_hours']:g} = {row['free_left']:g}시간")
            st.write(f"**보정 전 예상 학점**: {row['evidence']}")
            st.write(f"**보정 이유**: {row['reason']}")
            if row["scenario_condition"]:
                st.caption(f"세부 조건: {row['scenario_condition']}")
    st.caption(
        f"계산식의 기준값({simulation_mod.SPARE_RATIO}, {simulation_mod.HOUR_WEIGHT}, "
        f"{simulation_mod.BASE_CREDITS}, {simulation_mod.CREDIT_WEIGHT})과 AI 보정 폭 ±{simulation_mod.AI_LIMIT}는 "
        "실제 기록으로 검증하지 않은 가정입니다."
    )

    st.subheader("보고서")
    st.markdown(report_mod.make_report(table))

    c1, c2 = st.columns(2)
    if c1.button("🔄 AI 보정 다시 받기"):
        run_simulation()
        go_to("📊 결과·보고서", "시뮬레이션을 다시 실행했습니다.")
    if c2.button("📝 학기 말에 실제 결과 기록하기"):
        go_to("📝 학기 말 기록")


elif menu == "📝 학기 말 기록":
    st.header("📝 ④ 학기 말 실제 결과 기록")
    st.caption("학기가 끝나면 실제로 고른 선택지의 결과를 기록합니다. 다음 학기 예측에 반영됩니다.")
    try:
        pending = feedback_mod.open_rows()
    except ValueError as error:
        st.error(str(error))
        st.stop()

    if not pending:
        st.info("결과를 기록할 선택지가 없습니다. 학기 초에 선택지를 먼저 입력하세요.")
    else:
        labels = {
            f"{row['term']} · {row['scenario_option']} (주 {float(row['scenario_hours']):g}시간)": index
            for index, row in pending
        }
        with st.form("feedback_form"):
            choice = st.selectbox("실제로 고른 선택지", list(labels))
            c1, c2 = st.columns(2)
            actual = c1.number_input("실제 학점 (0.0~4.5)", 0.0, 4.5, None, step=0.01, placeholder="예: 3.75")
            satisfaction = c2.select_slider("만족도", options=[1, 2, 3, 4, 5], value=3)
            review = st.text_area(
                "자유 평가", placeholder="예: 시험 기간에 근무가 겹쳐 과제 시간이 부족했다",
                help=feedback_mod.REVIEW_NOTICE,
            )
            st.caption("⚠️ " + feedback_mod.REVIEW_NOTICE)
            submitted = st.form_submit_button("기록하기", type="primary")
        if submitted:
            try:
                saved = feedback_mod.record_result(labels[choice], actual, satisfaction, review)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state.last_feedback = saved
                st.rerun()

    saved = st.session_state.pop("last_feedback", None)
    if saved:
        st.success(
            f"기록했습니다. 계산식 예상 학점 {saved['predicted_gpa']:.2f} → 실제 학점 {float(saved['actual_gpa']):g}, "
            f"예측 오차 {saved['error']:+.2f}"
        )

    rows = feedback_mod.history()
    if rows:
        st.subheader("지금까지의 예측 오차")
        st.dataframe(
            [
                {
                    "학기": row["term"],
                    "선택지": row["scenario_option"],
                    "계산식 예상 학점": f"{row['predicted_gpa']:.2f}",
                    "실제 학점": row["actual_gpa"],
                    "예측 오차": f"{row['error']:+.2f}",
                    "만족도": row["satisfaction"],
                    "자유 평가": row["user_review"],
                }
                for row in rows
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            f"오차 평균(절댓값): {feedback_mod.mean_abs_error(rows):.2f} · "
            "예측 오차 = 실제 학점 − 저장된 입력으로 계산식을 다시 돌린 예상 학점"
        )
