# ui 모듈 — 화면 꾸미기 전용(CSS와 HTML 조각). 계산 · 저장 로직은 다른 모듈에 있습니다.
from html import escape

import streamlit as st

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]   # 선택지 1 · 2 · 3 색
STEPS = [("👤", "프로필"), ("🔀", "선택지"), ("📊", "결과·보고서"), ("📝", "학기 말 기록")]

CSS = """
<style>
:root {
  --cs-brand: #3b5bdb; --cs-brand-2: #7048e8; --cs-soft: #edf2ff; --cs-card: #ffffff; --cs-line: #e2e8f0;
  --cs-fg: #0f172a; --cs-fg-2: #334155; --cs-muted: #64748b; --cs-track: #e9edf5;
  --cs-warn: #b45309; --cs-warn-soft: #fff7e6; --cs-good: #2b8a3e; --cs-good-soft: #ebfbee;
  --cs-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06);
}
.block-container { max-width: 1120px; padding-top: 2.2rem; padding-bottom: 4rem; }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3 { letter-spacing: -0.02em; }

/* 사이드바 메뉴: 라디오를 메뉴 버튼처럼 */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([role="radiogroup"]),
[data-testid="stSidebar"] [data-testid="stRadio"] { width: 100% !important; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 4px; width: 100%; }
[data-testid="stSidebar"] [role="radiogroup"] > div { width: 100% !important; max-width: none !important; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  width: 100% !important; max-width: none !important; box-sizing: border-box; padding: 10px 12px; border-radius: 10px; margin: 0; transition: background .15s;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(145,167,255,.10); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background: linear-gradient(90deg, rgba(145,167,255,.30), rgba(165,139,255,.10));
  box-shadow: inset 3px 0 0 #91a7ff;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { font-weight: 700; color: #fff; }
[data-testid="stSidebar"] [role="radiogroup"] label div:has(+ [data-testid="stMarkdownContainer"]) { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] p { font-size: 15px; }

/* 공통 조각 */
.cs-brand { display: flex; align-items: center; gap: 10px; margin: 4px 0 18px; }
.cs-logo { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; font-size: 20px;
  background: linear-gradient(135deg, #3b5bdb, #7048e8); box-shadow: 0 6px 16px rgba(59,91,219,.45); }
.cs-brand b { display: block; font-size: 16px; line-height: 1.25; color: #fff; }
.cs-brand span { font-size: 12px; color: #8e9ab5; }
.cs-side-label { font-size: 11px; font-weight: 800; letter-spacing: .08em; color: #8e9ab5; margin: 4px 0 6px; }
.cs-side-progress { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.cs-side-progress div { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #c5cde0; }
.cs-side-progress i { width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; font-style: normal;
  font-size: 11px; border: 1.5px solid #4a5583; color: #8e9ab5; }
.cs-side-progress .done i { background: #91a7ff; border-color: #91a7ff; color: #141b3a; font-weight: 800; }

.cs-hero { position: relative; overflow: hidden; border-radius: 22px; padding: 40px 40px 36px; color: #fff;
  background: linear-gradient(135deg, #3b5bdb 0%, #5f3dc4 60%, #7048e8 100%); box-shadow: 0 20px 50px rgba(59,91,219,.28); }
.cs-hero::before { content: ""; position: absolute; width: 340px; height: 340px; right: -90px; top: -120px; border-radius: 50%;
  background: rgba(255,255,255,.10); }
.cs-hero::after { content: ""; position: absolute; width: 220px; height: 220px; right: 140px; bottom: -130px; border-radius: 50%;
  background: rgba(255,255,255,.07); }
.cs-hero .k { display: inline-block; font-size: 13px; font-weight: 700; background: rgba(255,255,255,.18); padding: 4px 12px;
  border-radius: 999px; }
.cs-hero h1 { color: #fff; font-size: clamp(28px, 4.4vw, 42px); line-height: 1.2; margin: 14px 0 10px; padding: 0; }
.cs-hero p { color: rgba(255,255,255,.88); font-size: 17px; max-width: 620px; margin: 0; }
.cs-hero .emoji { position: absolute; right: 44px; top: 50%; transform: translateY(-50%); font-size: 88px; opacity: .9; }
@media (max-width: 760px) { .cs-hero { padding: 28px 22px; } .cs-hero .emoji { display: none; } }

.cs-page { display: flex; align-items: center; gap: 16px; margin: 0 0 18px; }
.cs-page .ic { flex: none; width: 54px; height: 54px; border-radius: 16px; display: grid; place-items: center; font-size: 26px;
  background: var(--cs-soft); }
.cs-page .s { font-size: 13px; font-weight: 800; color: var(--cs-brand); letter-spacing: .04em; }
.cs-page h2 { margin: 0; padding: 0; font-size: 28px; }
.cs-page p { margin: 2px 0 0; color: var(--cs-muted); font-size: 15px; }

.cs-stepper { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 0 0 24px; }
.cs-step { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; background: var(--cs-card);
  border: 1px solid var(--cs-line); font-size: 14px; color: var(--cs-muted); }
.cs-step i { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-style: normal;
  font-size: 13px; font-weight: 800; background: var(--cs-track); color: var(--cs-muted); }
.cs-step.done i { background: var(--cs-good-soft); color: var(--cs-good); }
.cs-step.now { border-color: var(--cs-brand); color: var(--cs-fg); font-weight: 700; box-shadow: 0 0 0 3px rgba(59,91,219,.12); }
.cs-step.now i { background: var(--cs-brand); color: #fff; }
@media (max-width: 760px) { .cs-stepper { grid-template-columns: 1fr 1fr; } }

.cs-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 22px 0 8px; }
.cs-stat { background: var(--cs-card); border: 1px solid var(--cs-line); border-radius: 16px; padding: 18px 20px; box-shadow: var(--cs-shadow);
  display: flex; gap: 14px; align-items: center; }
.cs-stat .ic { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; font-size: 21px; background: var(--cs-soft); }
.cs-stat span { font-size: 13px; color: var(--cs-muted); display: block; }
.cs-stat b { font-size: 22px; letter-spacing: -0.02em; color: var(--cs-fg); }
@media (max-width: 760px) { .cs-stats { grid-template-columns: 1fr; } }

.cs-flow { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 10px 0; }
.cs-flow > div { background: var(--cs-card); border: 1px solid var(--cs-line); border-radius: 16px; padding: 18px; box-shadow: var(--cs-shadow); }
.cs-flow .n { font-size: 12px; font-weight: 800; color: var(--cs-brand); }
.cs-flow b { display: block; font-size: 16px; margin: 4px 0; color: var(--cs-fg); }
.cs-flow p { margin: 0; font-size: 14px; color: var(--cs-fg-2); line-height: 1.55; }
.cs-flow .e { font-size: 24px; }
@media (max-width: 860px) { .cs-flow { grid-template-columns: 1fr 1fr; } }

.cs-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }
.cs-chip { background: var(--cs-card); border: 1px solid var(--cs-line); border-radius: 999px; padding: 6px 14px; font-size: 14px; color: var(--cs-fg-2); }
.cs-chip b { color: var(--cs-fg); }

.cs-dot { display: inline-block; width: 11px; height: 11px; border-radius: 4px; margin-right: 8px; vertical-align: 0; }
.cs-opt-title { font-weight: 800; font-size: 17px; color: var(--cs-fg); }

.cs-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 6px 0 20px; }
.cs-card { position: relative; background: var(--cs-card); border: 1px solid var(--cs-line); border-radius: 18px; padding: 20px 20px 16px;
  box-shadow: var(--cs-shadow); overflow: hidden; }
.cs-card::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 5px; background: var(--c); }
.cs-card .t { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-weight: 800; font-size: 17px; color: var(--cs-fg); }
.cs-card .big { font-size: 40px; font-weight: 800; letter-spacing: -0.03em; color: var(--cs-fg); margin: 10px 0 0; line-height: 1.1; }
.cs-card .big small { font-size: 13px; font-weight: 600; color: var(--cs-muted); margin-left: 6px; letter-spacing: 0; }
.cs-card .rng { font-size: 13px; color: var(--cs-muted); margin-top: 4px; font-variant-numeric: tabular-nums; }
.cs-dots .band { position: absolute; top: 11px; height: 10px; border-radius: 5px; opacity: .18; }
.cs-card .kv { display: flex; justify-content: space-between; font-size: 14px; padding: 7px 0; border-top: 1px dashed var(--cs-line); color: var(--cs-fg-2); }
.cs-card .kv:first-of-type { margin-top: 12px; }
.cs-card .kv b { color: var(--cs-fg); font-variant-numeric: tabular-nums; }
.cs-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; min-height: 24px; }
.cs-pill { font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 999px; white-space: nowrap; }
.cs-pill.warn { background: var(--cs-warn-soft); color: var(--cs-warn); }
.cs-pill.ok { background: var(--cs-good-soft); color: var(--cs-good); }
.cs-pill.info { background: var(--cs-soft); color: var(--cs-brand); }

.cs-chart { background: var(--cs-card); border: 1px solid var(--cs-line); border-radius: 18px; padding: 22px 22px 16px; box-shadow: var(--cs-shadow); margin-bottom: 16px; }
.cs-chart h4 { margin: 0; padding: 0; font-size: 16px; color: var(--cs-fg); }
.cs-chart .cap { font-size: 13px; color: var(--cs-muted); margin: 2px 0 26px; }
.cs-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--cs-fg-2); margin: -12px 0 18px; }
.cs-row { display: grid; grid-template-columns: 110px 1fr; gap: 12px; align-items: center; margin-bottom: 16px; }
.cs-row .nm { font-size: 14px; font-weight: 700; color: var(--cs-fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cs-track { position: relative; height: 26px; }
.cs-track .bg { position: absolute; inset: 0; border-radius: 4px; background: var(--cs-track); }
.cs-track .seg { position: absolute; top: 0; bottom: 0; border-radius: 0 4px 4px 0; }
.cs-track .over { position: absolute; top: 0; bottom: 0; border-radius: 0 4px 4px 0; opacity: .8;
  background: repeating-linear-gradient(135deg, #b45309 0 3px, transparent 3px 7px); }
.cs-track .lim { position: absolute; top: -6px; bottom: -6px; width: 2px; background: var(--cs-fg); opacity: .7; }
.cs-track .liml { position: absolute; top: -24px; transform: translateX(-50%); font-size: 12px; color: var(--cs-muted); white-space: nowrap; }
.cs-val { font-size: 13px; color: var(--cs-fg-2); margin-top: 4px; font-variant-numeric: tabular-nums; }
.cs-val .cs-pill { margin-left: 6px; }
.cs-dots { position: relative; height: 32px; }
.cs-dots .ax { position: absolute; left: 0; right: 0; top: 15px; height: 2px; background: var(--cs-line); }
.cs-dots .ref { position: absolute; top: 2px; bottom: 2px; border-left: 2px dashed var(--cs-muted); opacity: .6; }
.cs-dots .ln { position: absolute; top: 14px; height: 4px; border-radius: 2px; opacity: .35; }
.cs-dots .pt { position: absolute; top: 8px; width: 16px; height: 16px; margin-left: -8px; border-radius: 50%;
  border: 2px solid #fff; box-shadow: 0 0 0 1px var(--cs-line); }
.cs-dots .ring { position: absolute; top: 9px; width: 14px; height: 14px; margin-left: -7px; border-radius: 50%; background: #fff; border: 2px solid; }
.cs-dots .lb { position: absolute; top: -4px; font-size: 13px; font-weight: 800; white-space: nowrap; color: var(--cs-fg);
  transform: translateX(14px); font-variant-numeric: tabular-nums; }
.cs-dots .lb.left { transform: translateX(calc(-100% - 14px)); }
.cs-ticks { position: relative; height: 18px; margin-left: 122px; font-size: 12px; color: var(--cs-muted); }
.cs-ticks span { position: absolute; transform: translateX(-50%); }
.cs-note { font-size: 12px; color: var(--cs-muted); margin: 8px 0 0 122px; }

.cs-target .kv { flex-direction: column; gap: 2px; }
.cs-target .kv .v { color: var(--cs-fg); }
.cs-target .t { align-items: flex-start; }
.cs-total { font-size: 14px; color: var(--cs-fg-2); }
.cs-total b { color: var(--cs-fg); }
.cs-acts { margin: 10px 0 2px; display: flex; flex-direction: column; gap: 4px; }
.cs-acts div { display: flex; justify-content: space-between; font-size: 13px; color: var(--cs-fg-2); }
.cs-callout { display: flex; gap: 12px; align-items: flex-start; background: var(--cs-soft); border-radius: 14px; padding: 14px 16px;
  font-size: 14px; color: var(--cs-fg-2); margin: 8px 0 16px; }
.cs-callout .e { font-size: 20px; line-height: 1.2; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def label(row: dict) -> str:
    """화면에 보여 줄 선택지 이름(활동이 여러 개면 '인턴 병행 + 공부')."""
    return row.get("label") or row["scenario_option"]


def color(index: int) -> str:
    return SERIES[index % len(SERIES)]


def fmt(value) -> str:
    return f"{round(float(value), 2):g}"


def sidebar_brand(title: str) -> None:
    html(
        f'<div class="cs-brand"><div class="cs-logo">🎓</div>'
        f"<div><b>{escape(title)}</b><span>학기 선택 비교 도우미</span></div></div>"
        '<div class="cs-side-label">MENU</div>'
    )


def sidebar_progress(done: list) -> None:
    items = "".join(
        f'<div class="{"done" if ok else ""}"><i>{"✓" if ok else index + 1}</i>{escape(name)}</div>'
        for index, ((_, name), ok) in enumerate(zip(STEPS, done))
    )
    html(f'<div class="cs-side-label">진행 상황</div><div class="cs-side-progress">{items}</div>')


def hero(kicker: str, title: str, text: str, emoji: str = "🎓") -> None:
    html(
        f'<div class="cs-hero"><span class="k">{escape(kicker)}</span><h1>{title}</h1>'
        f'<p>{text}</p><div class="emoji">{emoji}</div></div>'
    )


def page_header(icon: str, step: str, title: str, text: str) -> None:
    html(
        f'<div class="cs-page"><div class="ic">{icon}</div><div><div class="s">{escape(step)}</div>'
        f"<h2>{escape(title)}</h2><p>{escape(text)}</p></div></div>"
    )


def stepper(current: int, done: list) -> None:
    cells = []
    for index, ((_, name), ok) in enumerate(zip(STEPS, done)):
        state = "now" if index == current else ("done" if ok else "")
        mark = "✓" if ok and index != current else index + 1
        cells.append(f'<div class="cs-step {state}"><i>{mark}</i>{escape(name)}</div>')
    html(f'<div class="cs-stepper">{"".join(cells)}</div>')


def stats(items: list) -> None:
    """items: [(아이콘, 이름, 값), ...]"""
    cells = "".join(
        f'<div class="cs-stat"><div class="ic">{icon}</div><div><span>{escape(label)}</span><b>{escape(str(value))}</b></div></div>'
        for icon, label, value in items
    )
    html(f'<div class="cs-stats">{cells}</div>')


def flow() -> None:
    steps = [
        ("👤", "① 프로필", "이번 학기 내 상황", "학기 · 현재 학점 · 수강 학점 · 주간 자유 시간"),
        ("🔀", "② 선택지", "비교할 선택지 1~3개", "주간 투입 시간과 세부 조건(글)"),
        ("📊", "③ 결과·보고서", "같은 기준의 비교", "남는 시간 · 예상 학점 · 시간 부족 경고"),
        ("📝", "④ 학기 말 기록", "실제 결과 기록", "실제 학점 · 만족도 · 후기 → 다음 학기 반영"),
    ]
    cells = "".join(
        f'<div><div class="e">{e}</div><div class="n">{n}</div><b>{b}</b><p>{p}</p></div>' for e, n, b, p in steps
    )
    html(f'<div class="cs-flow">{cells}</div>')


def chips(items: list) -> None:
    html('<div class="cs-chips">' + "".join(f'<span class="cs-chip">{escape(k)} <b>{escape(v)}</b></span>' for k, v in items) + "</div>")


def option_title(index: int, text: str) -> None:
    html(f'<div class="cs-opt-title"><span class="cs-dot" style="background:{color(index)}"></span>{escape(text)}</div>')


def activity_total(container, total: float, study: float, free: float) -> None:
    parts = [f"합계 <b>{fmt(total)}시간</b>"]
    if study:
        parts.append(f"📚 공부 {fmt(study)}시간")
    if total > free:
        parts.append(f'<span class="cs-pill warn">⚠️ 자유 시간 {fmt(free)}시간보다 {fmt(total - free)}시간 많음</span>')
    container.markdown(f'<div class="cs-total">{" · ".join(parts)}</div>', unsafe_allow_html=True)


def callout(emoji: str, text: str) -> None:
    html(f'<div class="cs-callout"><span class="e">{emoji}</span><div>{text}</div></div>')


def option_cards(table: dict) -> None:
    rows = table["rows"]
    top_gpa = max(row["expected_gpa"] for row in rows)
    top_free = max(row["free_left"] for row in rows)
    cards = []
    for index, row in enumerate(rows):
        badges = []
        if row["short"]:
            badges.append(f'<span class="cs-pill warn">⚠️ {fmt(-row["free_left"])}시간 부족</span>')
        else:
            badges.append('<span class="cs-pill ok">✓ 시간 안에 가능</span>')
        if row.get("all_study"):
            badges.append('<span class="cs-pill info">📚 공부 시간으로 계산</span>')
        elif row.get("study"):
            badges.append(f'<span class="cs-pill info">📚 공부 {fmt(row["study_hours"])}시간 포함</span>')
        if len(rows) > 1 and row["expected_gpa"] == top_gpa:
            badges.append('<span class="cs-pill info">예상 학점 가장 높음</span>')
        if len(rows) > 1 and row["free_left"] == top_free:
            badges.append('<span class="cs-pill info">남는 시간 가장 많음</span>')
        ai = f"{row['adjust']:+.2f}" if row["ai_used"] else "없음"
        acts = row.get("activities") or []
        breakdown = (
            '<div class="cs-acts">' + "".join(
                f'<div><span>{"📚 " if a["study"] else "· "}{escape(a["name"])}</span><span>{fmt(a["hours"])}시간</span></div>'
                for a in acts
            ) + "</div>"
            if len(acts) > 1 else ""
        )
        cards.append(
            f'<div class="cs-card" style="--c:{color(index)}">'
            f'<div class="t"><span><span class="cs-dot" style="background:{color(index)}"></span>{escape(label(row))}</span></div>'
            f'<div class="big">{row["expected_gpa"]:.2f}<small>예상 학점</small></div>'
            + (f'<div class="rng">예상 범위 {row["range"][0]:.2f} ~ {row["range"][1]:.2f}</div>' if row.get("range") else "")
            + breakdown +
            f'<div class="kv"><span>주간 투입 시간</span><b>{fmt(row["scenario_hours"])}시간</b></div>'
            f'<div class="kv"><span>남는 자유 시간</span><b>{fmt(row["free_left"])}시간</b></div>'
            f'<div class="kv"><span>계산식 · 내 기록 · AI</span><b>{row["base_gpa"]:.2f} · {row.get("personal_adjust", 0):+.2f} · {ai}</b></div>'
            f'<div class="cs-badges">{"".join(badges)}</div></div>'
        )
    html(f'<div class="cs-cards">{"".join(cards)}</div>')


def legend(names: list) -> str:
    return '<div class="cs-legend">' + "".join(
        f'<span><span class="cs-dot" style="background:{color(i)}"></span>{escape(n)}</span>' for i, n in enumerate(names)
    ) + "</div>"


def time_chart(table: dict) -> None:
    rows, free = table["rows"], table["weekly_free_hours"]
    scale = max([free] + [row["scenario_hours"] for row in rows] + [1])
    pct = lambda v: v / scale * 100   # noqa: E731
    lines = []
    for index, row in enumerate(rows):
        hours = row["scenario_hours"]
        used, over = min(hours, free), max(hours - free, 0)
        tag = (
            f'<span class="cs-pill warn">⚠️ {fmt(over)}시간 부족</span>' if over else '<span class="cs-pill ok">✓ 가능</span>'
        )
        lines.append(
            f'<div class="cs-row" title="{escape(row["scenario_option"])}: 투입 {fmt(hours)}시간, 남는 {fmt(row["free_left"])}시간">'
            f'<div class="nm">{escape(label(row))}</div><div>'
            f'<div class="cs-track"><div class="bg"></div>'
            f'<div class="seg" style="left:0;width:{pct(used):.2f}%;background:{color(index)}"></div>'
            + (f'<div class="over" style="left:calc({pct(free):.2f}% + 2px);width:calc({pct(over):.2f}% - 2px)"></div>' if over else "")
            + f'<div class="lim" style="left:{pct(free):.2f}%"></div>'
            + (f'<div class="liml" style="left:{pct(free):.2f}%">자유 시간 {fmt(free)}h</div>' if index == 0 else "")
            + f'</div><div class="cs-val">투입 {fmt(hours)}h · 남는 시간 <b>{fmt(row["free_left"])}h</b>{tag}</div></div></div>'
        )
    html(
        '<div class="cs-chart"><h4>⏱️ 시간 예산</h4>'
        '<div class="cap">막대 = 주간 투입 시간 · 세로선 = 주간 자유 시간. 선을 넘은 빗금 부분이 부족한 시간입니다.</div>'
        + "".join(lines) + "</div>"
    )


def _axis(values: list) -> tuple:
    lo = max(0.0, int((min(values) - 0.2) * 2) / 2)
    hi = min(4.5, -int(-(max(values) + 0.2) * 2) / 2)
    if hi - lo < 1:
        hi = min(4.5, lo + 1)
        lo = max(0.0, hi - 1)
    return lo, hi


def _ticks(lo: float, hi: float) -> str:
    return '<div class="cs-ticks">' + "".join(
        f'<span style="left:{t * 100:g}%">{lo + (hi - lo) * t:.2f}</span>' for t in (0, 0.25, 0.5, 0.75, 1)
    ) + "</div>"


def gpa_chart(table: dict, current_gpa: float) -> None:
    rows = table["rows"]
    lo, hi = _axis(
        [r["expected_gpa"] for r in rows] + [r["base_gpa"] for r in rows] + [current_gpa]
        + [v for r in rows for v in r.get("range", ())]
    )
    pos = lambda v: (min(max(v, lo), hi) - lo) / (hi - lo) * 100   # noqa: E731
    lines = []
    for index, row in enumerate(rows):
        base, final = pos(row["base_gpa"]), pos(row["expected_gpa"])
        side = "left" if final > 80 else ""
        lines.append(
            f'<div class="cs-row" title="{escape(row["scenario_option"])}: 보정 전 {row["base_gpa"]:.2f} → 예상 {row["expected_gpa"]:.2f}">'
            f'<div class="nm">{escape(label(row))}</div><div class="cs-dots"><div class="ax"></div>'
            f'<div class="ref" style="left:{pos(current_gpa):.2f}%"></div>'
            + (
                f'<div class="band" style="left:{pos(row["range"][0]):.2f}%;width:{pos(row["range"][1]) - pos(row["range"][0]):.2f}%;background:{color(index)}"></div>'
                if row.get("range") else ""
            )
            + (
                f'<div class="ln" style="left:{min(base, final):.2f}%;width:{abs(final - base):.2f}%;background:{color(index)}"></div>'
                f'<div class="ring" style="left:{base:.2f}%;border-color:{color(index)}"></div>'
                if row["expected_gpa"] != row["base_gpa"] else ""
            )
            + f'<div class="pt" style="left:{final:.2f}%;background:{color(index)}"></div>'
            f'<div class="lb {side}" style="left:{final:.2f}%">{row["expected_gpa"]:.2f}</div></div></div>'
        )
    html(
        '<div class="cs-chart"><h4>🎯 예상 학점</h4>'
        '<div class="cap">● 예상 학점 · ○ 계산식(보정 전) · 옅은 띠 = 예상 범위 · 점선 = 현재 학점</div>'
        + "".join(lines) + _ticks(lo, hi)
        + f'<div class="cs-note">┆ 현재 학점 {fmt(current_gpa)}</div></div>'
    )


def history_chart(rows: list) -> None:
    values = [float(r["actual_gpa"]) for r in rows] + [r["predicted_gpa"] for r in rows]
    lo, hi = _axis(values)
    pos = lambda v: (min(max(v, lo), hi) - lo) / (hi - lo) * 100   # noqa: E731
    lines = []
    for row in rows:
        pred, actual = pos(row["predicted_gpa"]), pos(float(row["actual_gpa"]))
        name = f'{row["term"]} · {row["scenario_option"]}'
        lines.append(
            f'<div class="cs-row" title="{escape(name)}: 예상 {row["predicted_gpa"]:.2f} → 실제 {float(row["actual_gpa"]):g}">'
            f'<div class="nm">{escape(name)}</div><div class="cs-dots"><div class="ax"></div>'
            f'<div class="ln" style="left:{min(pred, actual):.2f}%;width:{abs(actual - pred):.2f}%;background:#3b5bdb"></div>'
            f'<div class="ring" style="left:{pred:.2f}%;border-color:#3b5bdb"></div>'
            f'<div class="pt" style="left:{actual:.2f}%;background:#3b5bdb"></div>'
            f'<div class="lb {"left" if actual > 80 else ""}" style="left:{actual:.2f}%">{row["error"]:+.2f}</div></div></div>'
        )
    html(
        '<div class="cs-chart"><h4>📏 예측 vs 실제</h4>'
        '<div class="cap">○ 계산식 예상 학점 · ● 실제 학점 · 숫자 = 예측 오차(실제 − 예상)</div>'
        + "".join(lines) + _ticks(lo, hi) + "</div>"
    )


def _term_key(term: str) -> tuple:
    """'2026-2' 같은 학기를 시간 순서로 정렬하기 위한 키(숫자는 숫자로 비교)."""
    import re
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(term)))


def trend_chart(rows: list) -> None:
    """학기별 추이: 계산식 예상 학점과 실제 학점(학기에 기록이 여러 줄이면 평균)."""
    terms = {}
    for row in rows:
        terms.setdefault(row["term"], []).append(row)
    order = sorted(terms, key=_term_key)
    points = [
        {
            "term": term,
            "pred": sum(r["predicted_gpa"] for r in terms[term]) / len(terms[term]),
            "actual": sum(float(r["actual_gpa"]) for r in terms[term]) / len(terms[term]),
            "n": len(terms[term]),
        }
        for term in order
    ]
    lo, hi = _axis([p["pred"] for p in points] + [p["actual"] for p in points])
    width, height, left, right, top, bottom = 640, 250, 46, 60, 18, 52
    x = lambda i: left + (width - left - right) * (0.5 if len(points) == 1 else i / (len(points) - 1))   # noqa: E731
    y = lambda v: top + (height - top - bottom) * (1 - (v - lo) / (hi - lo))   # noqa: E731
    grid = "".join(
        f'<line x1="{left}" x2="{width - right}" y1="{y(lo + (hi - lo) * t):.1f}" y2="{y(lo + (hi - lo) * t):.1f}" stroke="#e2e8f0"/>'
        f'<text x="{left - 8}" y="{y(lo + (hi - lo) * t) + 4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{lo + (hi - lo) * t:.2f}</text>'
        for t in (0, 0.25, 0.5, 0.75, 1)
    )

    def series(key: str, color_: str, dashed: bool, filled: bool, name: str) -> str:
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(p[key]):.1f}" for i, p in enumerate(points))
        line = (
            f'<path d="{path}" fill="none" stroke="{color_}" stroke-width="2"{" stroke-dasharray=\"5 4\"" if dashed else ""}/>'
            if len(points) > 1 else ""
        )
        dots = "".join(
            f'<circle cx="{x(i):.1f}" cy="{y(p[key]):.1f}" r="5" fill="{color_ if filled else "#fff"}" stroke="{color_}" stroke-width="2">'
            f'<title>{escape(p["term"])} {name} {p[key]:.2f}</title></circle>'
            for i, p in enumerate(points)
        )
        return line + dots

    labels = "".join(
        f'<text x="{x(i):.1f}" y="{height - bottom + 20}" text-anchor="middle" font-size="12" font-weight="700" fill="#0f172a">{escape(p["term"])}</text>'
        f'<text x="{x(i):.1f}" y="{height - bottom + 37}" text-anchor="middle" font-size="11" fill="#64748b">오차 {p["actual"] - p["pred"]:+.2f}</text>'
        for i, p in enumerate(points)
    )
    last = points[-1]
    tags = (
        f'<text x="{x(len(points) - 1) + 9:.1f}" y="{y(last["actual"]) + 4:.1f}" font-size="12" font-weight="700" fill="#3b5bdb">{last["actual"]:.2f}</text>'
        f'<text x="{x(len(points) - 1) + 9:.1f}" y="{y(last["pred"]) + 4:.1f}" font-size="12" fill="#64748b">{last["pred"]:.2f}</text>'
    )
    svg = (
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="학기별 계산식 예상 학점과 실제 학점 추이">'
        + grid + series("pred", "#94a3b8", True, False, "계산식 예상") + series("actual", "#3b5bdb", False, True, "실제")
        + labels + tags + "</svg>"
    )
    note = "" if len(points) > 1 else '<div class="cs-note" style="margin-left:0">학기 기록이 2개 이상 쌓이면 선으로 이어져 추이가 보입니다.</div>'
    html(
        '<div class="cs-chart"><h4>📈 학기별 추이</h4>'
        '<div class="cap">학기마다 계산식 예상 학점과 실제 학점을 비교합니다. 한 학기에 기록이 여러 줄이면 평균입니다.</div>'
        '<div class="cs-legend" style="margin-top:-14px"><span><span class="cs-dot" style="background:#3b5bdb"></span>실제 학점</span>'
        '<span><span class="cs-dot" style="background:#fff;border:2px solid #94a3b8"></span>계산식 예상 학점(점선)</span></div>'
        + svg + note + "</div>"
    )


def _target_lines(plan: dict) -> str:
    if plan["max_other"] is None:
        other = "공부 외 활동 없음"
    elif plan["max_other"] < 0:
        other = "공부 외 활동을 모두 빼도 목표에 못 미칩니다"
    else:
        diff = plan["other"] - plan["max_other"]
        other = f"주 <b>{fmt(plan['max_other'])}시간</b>까지 (지금 {fmt(plan['other'])}시간" + (
            f" → <b>{fmt(diff)}시간 줄이기</b>)" if diff > 0 else ", 여유 있음)"
        )
    if plan["min_study"] is None:
        study = f"남은 자유 시간 {fmt(plan['study_limit'])}시간을 모두 공부해도 목표에 못 미칩니다"
    else:
        more = plan["min_study"] - plan["study"]
        study = f"주 <b>{fmt(plan['min_study'])}시간</b> 이상 (지금 {fmt(plan['study'])}시간" + (
            f" → <b>{fmt(more)}시간 늘리기</b>)" if more > 0 else ", 충분함)"
        ) if plan["min_study"] > 0 else f"공부를 따로 하지 않아도 목표에 닿습니다 (지금 {fmt(plan['study'])}시간)"
    return (
        f'<div class="kv"><span>공부 외 활동 한도</span><span class="v">{other}</span></div>'
        f'<div class="kv"><span>필요한 공부 시간</span><span class="v">{study}</span></div>'
    )


def target_cards(items: list) -> None:
    """items: [(이름, 색 번호, target_plan 결과), ...]"""
    cards = []
    for name, index, plan in items:
        pill = (
            '<span class="cs-pill ok">✓ 목표 달성 예상</span>' if plan["ok"]
            else f'<span class="cs-pill warn">✗ {fmt(plan["gap"])} 부족</span>'
        )
        cards.append(
            f'<div class="cs-card cs-target" style="--c:{color(index)}">'
            f'<div class="t"><span><span class="cs-dot" style="background:{color(index)}"></span>{escape(name)}</span>{pill}</div>'
            f'<div class="rng">지금 계획 예상 {plan["now"]:.2f} → 목표 {plan["target"]:.2f}</div>'
            + _target_lines(plan) + "</div>"
        )
    html(f'<div class="cs-cards">{"".join(cards)}</div>')


def compare_plan(plan_row: dict, now_row: dict) -> None:
    """학기 중 점검: 계획과 지금 상황을 나란히 보여 줍니다."""
    delta = now_row["expected_gpa"] - plan_row["expected_gpa"]
    tone = "ok" if delta >= 0 else "warn"
    sign = "▲" if delta > 0 else ("▼" if delta < 0 else "＝")

    def card(title: str, row: dict, accent: str) -> str:
        acts = "".join(
            f'<div><span>{"📚 " if a["study"] else "· "}{escape(a["name"])}</span><span>{fmt(a["hours"])}시간</span></div>'
            for a in row["activities"]
        )
        status = (
            f'<span class="cs-pill warn">⚠️ {fmt(-row["free_left"])}시간 부족</span>' if row["free_left"] < 0
            else '<span class="cs-pill ok">✓ 시간 안에 가능</span>'
        )
        return (
            f'<div class="cs-card" style="--c:{accent}"><div class="t"><span>{title}</span>{status}</div>'
            f'<div class="big">{row["expected_gpa"]:.2f}<small>예상 학점</small></div>'
            f'<div class="cs-acts">{acts}</div>'
            f'<div class="kv"><span>주간 투입 시간</span><b>{fmt(row["scenario_hours"])}시간</b></div>'
            f'<div class="kv"><span>남는 자유 시간</span><b>{fmt(row["free_left"])}시간</b></div></div>'
        )

    html(
        '<div class="cs-cards">'
        + card("📋 학기 초 계획", plan_row, "#94a3b8")
        + card("⏱️ 지금 상황", now_row, "#3b5bdb")
        + f'<div class="cs-card cs-delta"><div class="t"><span>변화</span></div>'
        f'<div class="big"><span class="cs-pill {tone}" style="font-size:22px;padding:6px 14px">{sign} {delta:+.2f}</span></div>'
        f'<div class="rng">예상 학점 {plan_row["expected_gpa"]:.2f} → {now_row["expected_gpa"]:.2f}</div></div>'
        "</div>"
    )
