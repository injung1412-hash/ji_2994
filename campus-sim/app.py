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
from modules import ui


APP_TITLE = "AI 대학생활 시뮬레이션 시스템"
MENUS = ["🏠 홈", "👤 프로필", "🔀 선택지", "📊 결과·보고서", "⏱️ 학기 중 점검", "📝 학기 말 기록", "🗂️ 기록 관리"]

st.set_page_config(page_title=APP_TITLE, page_icon="🎓", layout="wide")
ui.inject_css()

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
    st.session_state.personal = result["personal"]
    st.session_state.range_info = result["range"]


def new_activity(name: str = "", hours=None, study=None) -> dict:
    """study: 직접 고른 유형(True 공부 / False 공부 외), None이면 이름으로 자동 판단"""
    st.session_state.activity_seq = st.session_state.get("activity_seq", 0) + 1
    return {"id": st.session_state.activity_seq, "name": name, "hours": hours, "study": study}


CUSTOM = "✏️ 직접 입력"


def preset_label(name: str) -> str:
    return name if name == CUSTOM else ("📚 " if scenario_mod.keyword_study(name) else "· ") + name


def pick_activity(i: int, activity_id: int) -> None:
    """목록에서 활동을 고르면 이름을 바꾸고 유형은 자동 판단으로 되돌립니다."""
    choice = st.session_state[f"pk_{activity_id}"]
    for act in st.session_state.draft[i]["acts"]:
        if act["id"] == activity_id:
            if choice != CUSTOM:
                act["name"] = choice
                act["study"] = None
            st.session_state.pop(f"an_{activity_id}", None)   # 직접 입력 칸은 지금 이름에서 시작


def set_study(i: int, activity_id: int) -> None:
    for act in st.session_state.draft[i]["acts"]:
        if act["id"] == activity_id:
            act["study"] = st.session_state[f"as_{activity_id}"]


def load_draft() -> list:
    """선택지 화면에서 입력 중인 내용(선택지마다 활동 목록 + 세부 조건)."""
    if "draft" not in st.session_state:
        st.session_state.draft = [
            {
                "acts": [
                    new_activity(clean, hours, forced)
                    for name, hours in scenario_mod.parse_activities(s["scenario_option"], s["scenario_hours"])
                    for clean, forced in [scenario_mod.split_mark(name)]
                ],
                "cond": s["scenario_condition"],
            }
            for s in st.session_state.scenarios
        ]
    return st.session_state.draft


def ensure_draft(count: int) -> None:
    draft = st.session_state.draft
    while len(draft) < count:
        draft.append({"acts": [new_activity(scenario_mod.SUGGESTED_OPTIONS[len(draft)])], "cond": ""})


def sync_draft() -> None:
    """화면 입력값을 draft에 옮겨 둡니다(활동을 추가 · 삭제하기 전에 호출)."""
    for i, option in enumerate(st.session_state.draft):
        for act in option["acts"]:
            choice = st.session_state.get(f"pk_{act['id']}")
            if choice and choice != CUSTOM:
                act["name"] = choice
            else:
                act["name"] = st.session_state.get(f"an_{act['id']}", act["name"])
            act["hours"] = st.session_state.get(f"ah_{act['id']}", act["hours"])
        option["cond"] = st.session_state.get(f"cond_{i}", option["cond"])


def add_activity(i: int) -> None:
    sync_draft()
    st.session_state.draft[i]["acts"].append(new_activity())


def remove_activity(i: int, activity_id: int) -> None:
    sync_draft()
    acts = st.session_state.draft[i]["acts"]
    st.session_state.draft[i]["acts"] = [a for a in acts if a["id"] != activity_id]


@st.dialog("선택한 기록을 지울까요?")
def confirm_delete(indices: list, labels: list) -> None:
    st.write(f"아래 기록 {len(indices)}줄을 지웁니다. **지운 기록은 되돌릴 수 없습니다.**")
    for label in labels:
        st.markdown(f"- {label}")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 지우기", type="primary", use_container_width=True):
        try:
            count = scenario_mod.delete_rows(indices)
        except ValueError as error:
            st.error(str(error))
            return
        profile = st.session_state.profile
        if profile and any(label.startswith(profile["term"] + " ·") for label in labels):
            st.session_state.table = None   # 이번 학기 기록을 지웠으면 이전 결과 화면도 비웁니다
        st.session_state.delete_round = st.session_state.get("delete_round", 0) + 1
        go_to("🗂️ 기록 관리", f"기록 {count}줄을 지웠습니다.")
    if c2.button("취소", use_container_width=True):
        st.rerun()


@st.dialog("모든 기록을 지울까요?")
def confirm_clear() -> None:
    st.write("simulation_log.csv의 기록을 **모두** 지우고, 입력한 프로필 · 선택지 · 결과도 비워 처음 상태로 돌아갑니다.")
    st.warning("지운 기록은 되돌릴 수 없습니다. 필요하면 먼저 CSV로 내려받아 두세요.", icon="⚠️")
    agree = st.checkbox("모든 기록을 지우는 데 동의합니다")
    c1, c2 = st.columns(2)
    if c1.button("⚠️ 모두 지우기", type="primary", disabled=not agree, use_container_width=True):
        scenario_mod.clear_log()
        for key, default in [("profile", None), ("scenarios", []), ("table", None), ("ai_status", "")]:
            st.session_state[key] = default
        st.session_state.pop("draft", None)
        st.session_state.delete_round = st.session_state.get("delete_round", 0) + 1
        go_to("🗂️ 기록 관리", "모든 기록을 지웠습니다. 처음부터 다시 시작할 수 있습니다.")
    if c2.button("취소", use_container_width=True):
        st.rerun()


def target_input(container, key: str) -> float:
    """목표 학점 입력칸. 화면을 옮겨 다녀도 마지막에 넣은 값을 기억합니다."""
    default = st.session_state.get("target_value")
    if default is None:
        profile = st.session_state.profile
        default = float(profile["current_gpa"]) if profile else 3.5
    value = container.number_input(
        "🎯 목표 학점", 0.0, 4.5, float(default), step=0.05, format="%.2f", key=key,
        help="장학금 기준처럼 지키고 싶은 학점을 넣으세요.",
    )
    st.session_state.target_value = value
    return value


def safe_history() -> list:
    try:
        return feedback_mod.history()
    except ValueError:
        return []


if "next_menu" in st.session_state:
    st.session_state.menu = st.session_state.pop("next_menu")

records = safe_history()
done = [
    bool(st.session_state.profile),
    bool(st.session_state.scenarios),
    st.session_state.table is not None,
    bool(records),
]

with st.sidebar:
    ui.sidebar_brand(APP_TITLE)
    menu = st.radio("메뉴", MENUS, key="menu", label_visibility="collapsed")
    st.divider()
    ui.sidebar_progress(done)
    st.divider()
    st.caption("profile → scenario → simulation → compare → report → feedback")
    st.caption("기록 파일: data/simulation_log.csv")

if st.session_state.pop("scroll_to_top", False):
    try:
        st.html(
            "<script>document.querySelector('[data-testid=\"stMain\"]').scrollTo(0, 0);</script>",
            unsafe_allow_javascript=True,
        )
    except TypeError:   # Streamlit 1.52 이전에는 unsafe_allow_javascript가 없어 빈 iframe으로 대신합니다
        import streamlit.components.v1 as components
        components.html(
            "<script>window.parent.document.querySelector('[data-testid=\"stMain\"]').scrollTo(0, 0);</script>",
            height=0,
        )

if "flash_message" in st.session_state:
    st.success(st.session_state.pop("flash_message"), icon="✅")


if menu == "🏠 홈":
    ui.hero(
        "학기 초 선택을 숫자로 비교하는 도구",
        "이번 학기,<br>어디에 시간을 쓸까?",
        "인턴 병행 · 학점 집중 · 동아리 확대 중 어디에 시간을 쓸지 고민될 때, "
        "선택지마다 <b>남는 자유 시간</b>과 <b>예상 학점</b>을 같은 기준으로 비교해 보여 줍니다.",
    )
    if st.session_state.table is not None:
        target = ("▶ 결과 보기", "📊 결과·보고서")
    elif st.session_state.profile:
        target = ("▶ 이어서 선택지 입력", "🔀 선택지")
    else:
        target = ("▶ 시작하기", "👤 프로필")
    if st.button(target[0], type="primary"):
        go_to(target[1])

    ui.stats(
        [
            ("👤", "프로필", "입력됨" if st.session_state.profile else "미입력"),
            ("🔀", "선택지 수", f"{len(st.session_state.scenarios)}개"),
            ("📝", "기록된 학기 결과", f"{len(records)}건"),
        ]
    )


    st.subheader("사용 흐름")
    ui.flow()
    ui.callout("🔁", "학기 말에 기록한 결과는 다음 학기 예측에 반영됩니다.")
    st.caption("결정은 시스템이 아니라 내가 합니다. " + report_mod.NOTICE)


elif menu == "👤 프로필":
    ui.page_header("👤", "STEP 1", "이번 학기 내 상황", "학번 · 실명 · 가구 소득은 받지 않습니다.")
    ui.stepper(0, done)
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
    ui.callout("💡", "주간 자유 시간은 수업 시간을 뺀, 일주일에 내가 쓸 수 있는 시간입니다. 잠 · 식사 · 이동 시간은 빼고 적어 주세요.")
    if submitted:
        try:
            st.session_state.profile = profile_mod.build_profile(term, gpa, credits, free)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.table = None
            go_to("🔀 선택지", "프로필을 저장했습니다. 비교할 선택지를 입력하세요.")


elif menu == "🔀 선택지":
    ui.page_header("🔀", "STEP 2", "비교할 선택지", "선택지마다 활동과 주간 투입 시간, 세부 조건을 적습니다. 한 선택지에 활동을 여러 개 넣을 수 있습니다.")
    ui.stepper(1, done)
    profile = st.session_state.profile
    if not profile:
        st.warning("먼저 프로필을 입력하세요.")
        if st.button("👤 프로필 입력하러 가기", type="primary"):
            go_to("👤 프로필")
        st.stop()

    ui.chips(
        [
            ("학기", profile["term"]),
            ("현재 학점", f"{profile['current_gpa']:g}"),
            ("수강", f"{profile['course_credits']}학점"),
            ("주간 자유 시간", f"{profile['weekly_free_hours']:g}시간"),
        ]
    )
    draft = load_draft()
    count = st.radio("선택지 수", [1, 2, 3], index=min(len(st.session_state.scenarios) or 3, 3) - 1, horizontal=True)
    ensure_draft(count)

    items = []
    for i in range(count):
        option = draft[i]
        acts = option["acts"]
        with st.container(border=True):
            ui.option_title(i, f"선택지 {i + 1}")
            for j, act in enumerate(acts):
                c1, c2, c4, c3 = st.columns([5, 3, 1.6, 1], vertical_alignment="bottom")
                visibility = "visible" if j == 0 else "collapsed"
                options = scenario_mod.PRESET_ACTIVITIES + [CUSTOM]
                current = act["name"] if act["name"] in scenario_mod.PRESET_ACTIVITIES else CUSTOM
                if st.session_state.get(f"pk_{act['id']}") not in options:
                    st.session_state[f"pk_{act['id']}"] = current
                choice = c1.selectbox(
                    "활동 고르기", options, key=f"pk_{act['id']}", format_func=preset_label,
                    on_change=pick_activity, args=(i, act["id"]), label_visibility=visibility,
                    help="목록에서 고르거나, 맨 아래 '✏️ 직접 입력'을 고르면 이름을 직접 적을 수 있습니다.",
                )
                if choice == CUSTOM:
                    c1.text_input(
                        "활동 이름 직접 입력", act["name"] if act["name"] not in scenario_mod.PRESET_ACTIVITIES else "",
                        key=f"an_{act['id']}", label_visibility="collapsed", placeholder="활동 이름을 직접 적으세요 (예: 편입 준비)",
                    )
                    name_now = st.session_state.get(f"an_{act['id']}") or ""
                else:
                    name_now = choice
                c2.number_input(
                    "주간 시간", 0.0, 168.0, act["hours"], step=1.0, key=f"ah_{act['id']}",
                    label_visibility=visibility, placeholder="예: 15",
                )
                if act["study"] is None:   # 직접 고르기 전에는 이름의 단어로 자동 체크
                    st.session_state[f"as_{act['id']}"] = scenario_mod.keyword_study(name_now)
                else:
                    st.session_state[f"as_{act['id']}"] = act["study"]
                c4.checkbox(
                    "📚 공부", key=f"as_{act['id']}", on_change=set_study, args=(i, act["id"]),
                    help="공부 시간이면 체크합니다. 처음에는 이름에 공부 관련 단어가 있으면 자동으로 체크됩니다.",
                )
                c3.button(
                    "🗑️", key=f"del_{act['id']}", on_click=remove_activity, args=(i, act["id"]),
                    disabled=len(acts) == 1, help="이 활동 지우기", use_container_width=True,
                )
            names = [
                st.session_state.get(f"an_{a['id']}") or "" if st.session_state.get(f"pk_{a['id']}") == CUSTOM
                else st.session_state.get(f"pk_{a['id']}") or a["name"]
                for a in acts
            ]
            hours = [st.session_state.get(f"ah_{a['id']}") for a in acts]
            kinds = [bool(st.session_state.get(f"as_{a['id']}")) for a in acts]
            total = sum(h for h in hours if h is not None)
            study = sum(h for k, h in zip(kinds, hours) if h is not None and k)
            c1, c2 = st.columns([1, 2], vertical_alignment="center")
            c1.button(
                "➕ 활동 추가", key=f"add_{i}", on_click=add_activity, args=(i,),
                disabled=len(acts) >= scenario_mod.MAX_ACTIVITIES, use_container_width=True,
            )
            ui.activity_total(c2, total, study, profile["weekly_free_hours"])
            st.text_area(
                "세부 조건 (글)", option["cond"], key=f"cond_{i}", height=80,
                placeholder="예: 주 3일 근무, 출퇴근 왕복 1시간, 시험 기간에도 근무",
            )
        items.append(
            {
                "activities": [{"name": n, "hours": h, "study": k} for n, h, k in zip(names, hours, kinds)],
                "scenario_condition": st.session_state.get(f"cond_{i}", ""),
            }
        )
    sync_draft()   # 다른 화면에 다녀와도 입력한 내용이 남도록
    submitted = st.button("저장하고 시뮬레이션 실행 ▶", type="primary")
    ui.callout(
        "📚",
        "활동은 <b>목록에서 고르거나 ✏️ 직접 입력</b>할 수 있습니다. "
        "<b>📚 공부</b>에 체크한 활동은 <b>공부 시간</b>으로 보고 시간을 늘릴수록 예상 학점이 오르게 계산합니다. "
        "활동 이름에 <b>" + " · ".join(simulation_mod.STUDY_KEYWORDS) + "</b> 중 하나가 들어가면 자동으로 체크되고, "
        "“토익”처럼 빠졌거나 “시험 감독 알바”처럼 잘못 체크되면 직접 바꾸면 됩니다. "
        "그 밖의 활동(인턴 · 동아리 등)은 투입 시간만큼 공부할 시간이 줄어 예상 학점이 내려갑니다. "
        "예: <b>인턴 병행 15시간 + 공부 5시간</b>처럼 한 선택지에 활동을 섞을 수 있습니다.",
    )
    ui.callout("🤖", "세부 조건 글은 AI가 읽고 예상 학점을 ±0.3 안에서 보정하는 데 씁니다. 구체적으로 적을수록 보정 이유가 분명해집니다.")
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
    ui.page_header("📊", "STEP 3", "선택지 비교와 보고서", "모든 선택지를 남는 자유 시간 · 예상 학점이라는 같은 기준으로 비교합니다.")
    ui.stepper(2, done)
    table = st.session_state.table
    if table is None:
        st.warning("아직 시뮬레이션 결과가 없습니다. 선택지를 먼저 입력하세요.")
        if st.button("🔀 선택지 입력하러 가기", type="primary"):
            go_to("🔀 선택지")
        st.stop()

    status = st.session_state.ai_status
    if status.startswith(simulation_mod.NO_AI):
        st.warning(status, icon="⚠️")
    else:
        st.info(status, icon="🤖")
    for warning in table["warnings"]:
        st.error(warning)

    ui.option_cards(table)
    personal = st.session_state.get("personal") or {"value": 0, "count": 0, "text": ""}
    span = st.session_state.get("range_info") or {"width": simulation_mod.RANGE_DEFAULT, "text": ""}
    ui.callout(
        "📏",
        f"<b>내 기록 보정 {personal['value']:+.2f}</b> — {personal['text']}<br>"
        f"<b>예상 범위 ±{span['width']:g}</b> — {span['text']}",
    )

    st.subheader("🎯 목표 학점으로 거꾸로 계산")
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    target = target_input(c1, "target_result")
    c2.caption(
        "목표 학점을 지키려면 선택지마다 **공부 외 활동(인턴 · 동아리 등)은 최대 몇 시간**, **공부는 최소 몇 시간**인지 "
        "거꾸로 계산합니다. 시간에 따라 다시 계산할 수 없는 AI 보정은 빼고 계산식 + 내 기록 보정으로 계산합니다(0.5시간 단위)."
    )
    ui.target_cards(
        [
            (ui.label(row), index, simulation_mod.target_plan(st.session_state.profile, row, target, row.get("personal_adjust", 0)))
            for index, row in enumerate(table["rows"])
        ]
    )

    tab_chart, tab_table, tab_reason = st.tabs(["📈 차트로 보기", "📋 비교표", "🧮 계산 근거와 보정 이유"])
    with tab_chart:
        c1, c2 = st.columns(2)
        with c1:
            ui.time_chart(table)
        with c2:
            ui.gpa_chart(table, st.session_state.profile["current_gpa"])
    with tab_table:
        st.dataframe(compare_mod.table_rows(table), hide_index=True, use_container_width=True)
    with tab_reason:
        for row in table["rows"]:
            with st.expander(row["scenario_option"], expanded=True):
                st.write(f"**남는 자유 시간**: {table['weekly_free_hours']:g} − {row['scenario_hours']:g} = {row['free_left']:g}시간")
                st.write(f"**보정 전 예상 학점**: {row['evidence']}")
                st.write(f"**보정 이유**: {row['reason']}")
                if row["scenario_condition"]:
                    st.caption(f"세부 조건: {row['scenario_condition']}")
        st.caption(
            f"계산식의 기준값({simulation_mod.SPARE_RATIO}, {simulation_mod.HOUR_WEIGHT}, "
            f"{simulation_mod.BASE_CREDITS}, {simulation_mod.CREDIT_WEIGHT}, 공부 {simulation_mod.STUDY_WEIGHT})과 "
            f"AI 보정 폭 ±{simulation_mod.AI_LIMIT}은 "
            "실제 기록으로 검증하지 않은 가정입니다."
        )

    st.subheader("📝 보고서")
    with st.container(border=True):
        st.markdown(report_mod.make_report(table))

    c1, c2, _ = st.columns([1, 1, 2])
    if c1.button("🔄 AI 보정 다시 받기", use_container_width=True):
        run_simulation()
        go_to("📊 결과·보고서", "시뮬레이션을 다시 실행했습니다.")
    if c2.button("📝 학기 말에 실제 결과 기록하기", type="primary", use_container_width=True):
        go_to("📝 학기 말 기록")


elif menu == "⏱️ 학기 중 점검":
    ui.page_header(
        "⏱️", "학기 중", "학기 중 점검",
        "계획대로 되고 있는지, 지금 실제로 쓰는 시간을 넣어 예상 학점을 다시 계산합니다. 점검 결과는 저장하지 않습니다.",
    )
    try:
        pending = feedback_mod.open_rows()
    except ValueError as error:
        st.error(str(error))
        st.stop()
    if not pending:
        st.info("점검할 계획이 없습니다. 학기 초에 선택지를 먼저 입력하세요.")
        if st.button("🔀 선택지 입력하러 가기", type="primary"):
            go_to("🔀 선택지" if st.session_state.profile else "👤 프로필")
        st.stop()

    plans = {
        f"{row['term']} · {row['scenario_option']} (주 {float(row['scenario_hours']):g}시간)": (index, row)
        for index, row in pending
    }
    choice = st.selectbox("점검할 계획 (학기 초에 실제로 고른 선택지)", list(plans))
    index, row = plans[choice]
    plan_profile = {
        "term": row["term"],
        "current_gpa": float(row["current_gpa"]),
        "course_credits": int(float(row["course_credits"])),
        "weekly_free_hours": float(row["weekly_free_hours"]),
    }
    correction = simulation_mod.personal_correction(feedback_mod.past_records(row["term"]))["value"]
    plan_row = simulation_mod.calculate(plan_profile, row, correction)

    st.subheader("지금 실제로 쓰는 시간")
    with st.container(border=True):
        free_now = st.number_input(
            "지금 주간 자유 시간 (수업 외)", 1.0, 168.0, plan_profile["weekly_free_hours"], step=1.0, key=f"mc_free_{index}",
            help="학기 중에 수업이나 고정 일정이 늘었다면 줄여서 넣으세요.",
        )
        acts = []
        for j, act in enumerate(plan_row["activities"]):
            c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
            c1.markdown(
                f"{'📚' if act['study'] else '·'} **{act['name']}** — 계획 주 {act['hours']:g}시간"
            )
            hours = c2.number_input(
                f"{act['name']} 지금 주간 시간", 0.0, 168.0, float(act["hours"]), step=1.0,
                key=f"mc_h_{index}_{j}", label_visibility="collapsed",
            )
            acts.append({"name": act["name"], "hours": hours, "study": act["study"]})
        c1, c2, c3 = st.columns([3, 1.4, 1], vertical_alignment="bottom")
        extra_name = c1.text_input("새로 생긴 활동 (있으면)", key=f"mc_xn_{index}", placeholder="예: 아르바이트")
        extra_hours = c2.number_input("주간 시간", 0.0, 168.0, 0.0, step=1.0, key=f"mc_xh_{index}")
        extra_study = c3.checkbox("📚 공부", key=f"mc_xs_{index}")
        if extra_name.strip() and extra_hours > 0:
            acts.append({"name": extra_name.strip(), "hours": extra_hours, "study": extra_study})
    try:
        now_scenario = scenario_mod.build_scenarios([{"activities": acts, "scenario_condition": row["scenario_condition"]}])[0]
    except ValueError as error:
        st.error("입력한 시간이나 새로 생긴 활동 이름을 확인해 주세요. " + str(error).replace("선택지 1의 ", "").replace("선택지 1에 ", ""))
        st.stop()
    now_profile = {**plan_profile, "weekly_free_hours": free_now}
    now_row = simulation_mod.calculate(now_profile, now_scenario, correction)

    st.subheader("계획과 비교")
    ui.compare_plan(plan_row, now_row)
    delta = now_row["expected_gpa"] - plan_row["expected_gpa"]
    other_diff = sum(a["hours"] for a in now_row["activities"] if not a["study"]) - sum(
        a["hours"] for a in plan_row["activities"] if not a["study"]
    )
    study_diff = now_row["study_hours"] - plan_row["study_hours"]
    reasons = []
    if other_diff:
        reasons.append(f"공부 외 활동이 계획보다 주 {abs(other_diff):g}시간 {'늘어' if other_diff > 0 else '줄어'}")
    if study_diff:
        reasons.append(f"공부 시간이 주 {abs(study_diff):g}시간 {'늘어' if study_diff > 0 else '줄어'}")
    if free_now != plan_profile["weekly_free_hours"]:
        reasons.append(f"자유 시간이 {plan_profile['weekly_free_hours']:g} → {free_now:g}시간으로 바뀌어")
    if reasons:
        ui.callout(
            "🧭",
            ", ".join(reasons) + f" 예상 학점이 <b>{plan_row['expected_gpa']:.2f}에서 {now_row['expected_gpa']:.2f}로</b> 바뀝니다"
            f"({delta:+.2f})." + (" 시간이 모자랍니다." if now_row["free_left"] < 0 else ""),
        )
    else:
        ui.callout("🧭", "지금 넣은 시간은 학기 초 계획과 같습니다. 바뀐 시간이 있으면 위 칸을 고쳐 보세요.")

    st.subheader("🎯 목표 학점 점검")
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    target = target_input(c1, "target_midterm")
    c2.caption("지금 상황 기준으로 목표 학점을 지키려면 시간을 어떻게 조정해야 하는지 계산합니다.")
    ui.target_cards([("지금 상황", 0, simulation_mod.target_plan(now_profile, now_row, target, correction))])
    st.caption(
        "점검 결과는 저장하지 않습니다(CSV 10개 항목 유지). 계산식 + 내 기록 보정으로 계산하며 AI 보정은 빠집니다. "
        "학기 말에는 📝 학기 말 기록에서 실제 결과를 기록하세요."
    )


elif menu == "📝 학기 말 기록":
    ui.page_header("📝", "STEP 4", "학기 말 실제 결과 기록", "실제로 고른 선택지의 결과를 기록합니다. 다음 학기 예측에 반영됩니다.")
    ui.stepper(3, done)
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
            satisfaction = c2.select_slider(
                "만족도", options=[1, 2, 3, 4, 5], value=3,
                format_func=lambda v: f"{v} " + ["😞", "🙁", "😐", "🙂", "😄"][v - 1],
            )
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
            f"예측 오차 {saved['error']:+.2f}",
            icon="✅",
        )

    rows = feedback_mod.history()
    if rows:
        st.subheader("지금까지의 예측 오차")
        ui.stats(
            [
                ("🗂️", "기록된 결과", f"{len(rows)}건"),
                ("📏", "오차 평균(절댓값)", f"{feedback_mod.mean_abs_error(rows):.2f}"),
                ("😊", "평균 만족도", f"{sum(int(r['satisfaction']) for r in rows) / len(rows):.1f} / 5"),
            ]
        )
        ui.trend_chart(rows)
        ui.history_chart(rows)
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
        st.caption("예측 오차 = 실제 학점 − 저장된 입력으로 계산식을 다시 돌린 예상 학점")


elif menu == "🗂️ 기록 관리":
    ui.page_header(
        "🗂️", "기록 관리", "저장된 기록 확인 · 지우기 · 불러오기",
        "잘못 입력한 기록은 골라서 지우고, 다른 기기에서 내려받은 CSV로 기록을 옮기거나 되살립니다.",
    )
    try:
        log = scenario_mod.read_log()
    except ValueError as error:
        st.error(str(error))
        st.caption("기록 파일을 초기화하면 다시 쓸 수 있습니다(기존 내용은 사라집니다). 초기화한 뒤 내려받아 둔 CSV가 있으면 불러오세요.")
        if st.button("⚠️ 기록 파일 초기화"):
            confirm_clear()
        st.stop()

    filled = [row for row in log if row["actual_gpa"] != ""]
    ui.stats(
        [
            ("🗂️", "전체 기록", f"{len(log)}줄"),
            ("📝", "실제 결과까지 기록", f"{len(filled)}줄"),
            ("📅", "기록된 학기", f"{len({row['term'] for row in log})}개"),
        ]
    )

    with st.expander("📥 내려받아 둔 CSV로 기록 불러오기 (백업 복원)", expanded=not log):
        st.caption(
            "이 시스템에서 내려받은 simulation_log.csv를 올리면 기록을 옮기거나 되살립니다. "
            "웹 버전 기록은 이 브라우저에만 저장되니, 기기를 바꿀 때 이 기능을 쓰세요."
        )
        upload = st.file_uploader("CSV 파일 올리기", type=["csv"], key=f"backup_{st.session_state.get('delete_round', 0)}")
        if upload is not None:
            try:
                incoming = scenario_mod.read_backup(upload.getvalue())
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(
                    f"파일 확인 완료: {len(incoming)}줄 · 학기 {len({r['term'] for r in incoming})}개 · "
                    f"실제 결과 {sum(1 for r in incoming if r['actual_gpa'])}줄"
                )
                mode = st.radio(
                    "불러오는 방법", ["합치기", "바꾸기"], horizontal=True,
                    captions=["지금 기록에 더합니다. 같은 학기 · 선택지는 실제 결과가 있는 쪽을 남깁니다.", "지금 기록을 모두 지우고 파일 내용으로 바꿉니다."],
                )
                agree = mode == "합치기" or st.checkbox("지금 기록을 모두 지우고 파일 내용으로 바꾸는 데 동의합니다")
                if st.button("📥 불러오기", type="primary", disabled=not agree):
                    result = scenario_mod.import_rows(incoming, "merge" if mode == "합치기" else "replace")
                    if mode == "바꾸기":
                        st.session_state.table = None
                    st.session_state.delete_round = st.session_state.get("delete_round", 0) + 1
                    go_to(
                        "🗂️ 기록 관리",
                        f"불러왔습니다. 새로 추가 {result['added']}줄 · 실제 결과 채움 {result['updated']}줄 · 건너뜀 {result['skipped']}줄",
                    )

    if not log:
        st.info("저장된 기록이 없습니다. 선택지를 입력하면 여기에 쌓입니다.")
        if st.button("🔀 선택지 입력하러 가기", type="primary"):
            go_to("🔀 선택지" if st.session_state.profile else "👤 프로필")
        st.stop()

    st.subheader("저장된 기록")
    st.caption("지울 줄의 **지우기** 칸을 체크하세요. 한 줄 = 한 학기 · 한 선택지입니다.")
    edited = st.data_editor(
        [
            {
                "지우기": False,
                "학기": row["term"],
                "선택지": row["scenario_option"],
                "투입 시간": f"{float(row['scenario_hours']):g}시간",
                "세부 조건": row["scenario_condition"],
                "실제 학점": row["actual_gpa"] or "—",
                "만족도": row["satisfaction"] or "—",
                "자유 평가": row["user_review"] or "—",
            }
            for row in log
        ],
        hide_index=True,
        use_container_width=True,
        disabled=["학기", "선택지", "투입 시간", "세부 조건", "실제 학점", "만족도", "자유 평가"],
        column_config={"지우기": st.column_config.CheckboxColumn("지우기", width="small")},
        key=f"log_editor_{st.session_state.get('delete_round', 0)}",
    )
    picked = [index for index, row in enumerate(edited) if row["지우기"]]
    labels = [
        f"{log[index]['term']} · {log[index]['scenario_option']} (주 {float(log[index]['scenario_hours']):g}시간)"
        + (" — 실제 결과 있음" if log[index]["actual_gpa"] else "")
        for index in picked
    ]

    c1, c2, c3 = st.columns([1.3, 1, 1])
    if c1.button(
        f"🗑️ 선택한 기록 지우기 ({len(picked)}줄)", type="primary", disabled=not picked, use_container_width=True
    ):
        confirm_delete(picked, labels)
    if c2.button("⚠️ 모든 기록 지우기", use_container_width=True):
        confirm_clear()
    with open(scenario_mod.LOG_PATH, "rb") as f:
        c3.download_button(
            "⬇️ CSV 내려받기", f.read(), file_name="simulation_log.csv", mime="text/csv", use_container_width=True
        )
    ui.callout(
        "💡",
        "실제 결과까지 기록한 줄을 지우면 예측 오차 기록과 다음 학기 AI 보정에 쓰이는 지난 학기 기록에서도 빠집니다. "
        "지운 기록은 되돌릴 수 없으니 필요하면 먼저 CSV로 내려받아 두세요.",
    )

