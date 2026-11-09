# -*- coding: utf-8 -*-
"""
산업연관표 분석 엔진 (model.py)
- 브라우저(Pyodide)와 일반 Python(CPython) 모두에서 동작
- 자료: 한국은행 2023년 산업연관표(연장표) 투입산출표(생산자가격)
        기본부문(380)·통합소분류(165)·통합중분류(83)·통합대분류(33), 2020 기준년 상품분류표, 별첨 통계표
- 금액 단위: 백만원(원표 그대로). 계수는 무단위(산출 또는 최종수요 1단위당), 취업·고용 관련 계수는 명/10억원.
- 모든 공개 함수는 JSON 문자열을 반환함.
"""
import io
import json
import math
import re

import numpy as np
import openpyxl

# ---------------------------------------------------------------- 상수
LEVEL_LABEL = {
    "basic": "기본부문(380)",
    "small": "통합소분류(165)",
    "mid": "통합중분류(83)",
    "large": "통합대분류(33)",
}
LEVEL_ORDER = ["basic", "small", "mid", "large"]
FD_CODES = ["9111", "9112", "9121", "9122", "9131", "9132", "9140"]
FD_NAMES = {
    "9111": "민간소비지출", "9112": "정부소비지출", "9121": "민간고정자본형성",
    "9122": "정부고정자본형성", "9131": "재고증감", "9132": "귀중품순취득", "9140": "수출",
}
FD_GROUPS = [  # (이름, 구성 항목)
    ("소비", ["9111", "9112"]),
    ("민간소비지출", ["9111"]),
    ("정부소비지출", ["9112"]),
    ("투자", ["9121", "9122", "9131", "9132"]),
    ("민간고정자본형성", ["9121"]),
    ("정부고정자본형성", ["9122"]),
    ("재고증감", ["9131"]),
    ("귀중품순취득", ["9132"]),
    ("수출", ["9140"]),
    ("최종수요계", FD_CODES),
]
VA_CODES = ["9610", "9621", "9622", "9630"]
VA_NAMES = {"9610": "피용자보수", "9621": "영업잉여", "9622": "고정자본소모", "9630": "생산세(보조금공제)"}

SHEET_TOTAL = "A표_총거래표(생산자)"
SHEET_IMP = "A표_수입거래표(생산자)"
SHEET_DOM = "A표_국산거래표(생산자)"

# 한국은행 보도자료(2025.9.24) 부문 통합 기준: 7부문, 13부문 (대분류 코드로 정의)
_C = lambda a, b: ["C%02d" % k for k in range(a, b + 1)]
GROUP7 = [
    ("농림수산품", ["A"]), ("광산품", ["B"]), ("공산품", _C(1, 14)),
    ("전력·가스·수도 및 폐기물", ["D", "E"]), ("건설", ["F"]),
    ("서비스", list("GHIJKLMNOPQRS")), ("기타", ["T"]),
]
GROUP13 = [
    ("농림수산품", ["A"]), ("광산품", ["B"]),
    ("소비재제품", _C(1, 3) + ["C13"]), ("기초소재제품", _C(4, 8)),
    ("조립가공제품", _C(9, 12)), ("제조임가공·산업용 장비 수리", ["C14"]),
    ("전력·가스·수도 및 폐기물", ["D", "E"]), ("건설", ["F"]),
    ("도소매 및 운송", ["G", "H"]), ("생산자서비스", list("JKLMN")),
    ("사회서비스", list("OPQ")), ("소비자서비스", list("IRS")), ("기타", ["T"]),
]

# 보도자료 본문 수치(2023년) — 자료로 재계산하여 대조
PRESS_MACRO = [
    ("총공급(=총수요)", "조원", 6802.7), ("총산출", "조원", 5786.7), ("수입", "조원", 1016.0),
    ("중간투입", "조원", 3403.4), ("부가가치", "조원", 2383.3), ("수출", "조원", 999.8),
    ("국내 최종수요(소비+투자)", "조원", 2399.4),
    ("중간투입률", "%", 58.8), ("부가가치율", "%", 41.2), ("수입의존도(수입 중간투입률)", "%", 13.6),
    ("국산화율", "%", 77.0), ("국산 중간투입률", "%", 45.2), ("수출률", "%", 17.3), ("수입률", "%", 14.9),
    ("대외거래 비중", "%", 29.6), ("피용자보수 비중(부가가치 중)", "%", 49.1),
    ("영업잉여 비중(부가가치 중)", "%", 20.8),
]

# ---------------------------------------------------------------- 전역 상태
LV = {}        # 분류 수준별 Level 객체
AUX = {"cls": None, "stats": None, "emp": None, "parent": {}}


# ---------------------------------------------------------------- 유틸
def emit(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False)


def fnum(v, nd=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd) if nd is not None else v


def clean(v):
    """셀 문자열 정리: 전각/특수 공백 제거, 앞뒤 공백 제거."""
    if v is None:
        return None
    s = str(v).replace("　", " ").replace("\xa0", " ").strip()
    return s or None


def norm(s):
    """명칭 비교용 정규화(공백·구두점·'및'·각주 제거)."""
    s = clean(s) or ""
    s = re.sub(r"\d\)\s*$", "", s.strip())
    s = re.sub(r"[\s,·․ㆍ\.\-]", "", s)
    s = s.replace("및", "")
    return s


def has_footnote(s):
    return bool(re.search(r"\d\)\s*$", str(s or "").strip()))


def is_agg_code(c):
    """합계·항목 코드(9xxx 4자리) 여부."""
    return c is not None and len(c) == 4 and c.isdigit() and c[0] == "9"


def safe_div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    out = np.zeros(np.broadcast(a, b).shape)
    np.divide(a, b, out=out, where=(b != 0))
    return out


def read_book(raw):
    wb = openpyxl.load_workbook(io.BytesIO(bytes(raw)), read_only=True, data_only=True)
    book = {s: [tuple(r) for r in wb[s].values] for s in wb.sheetnames}
    wb.close()
    return book


# ---------------------------------------------------------------- 투입산출표 시트 해석
class Sheet:
    """원표 시트: 4행=열 코드, 5행=열 명칭, 6행부터 자료(0열 코드, 1열 명칭)."""

    def __init__(self, name, rows):
        self.name = name
        self.rows = rows
        hr = self._find_header(rows)
        self.hr = hr
        hdr = rows[hr]
        names = rows[hr + 1] if hr + 1 < len(rows) else ()
        self.cols = []   # (열 index, 코드, 명칭)
        for i in range(2, len(hdr)):
            c = clean(hdr[i])
            if c is None:
                continue
            nm = clean(names[i]) if i < len(names) else None
            self.cols.append((i, c, (nm or "").replace("\n", " ")))
        self.data = []   # (행 index, 코드, 명칭)
        for k in range(hr + 2, len(rows)):
            r = rows[k]
            if not r or clean(r[0]) is None:
                continue
            self.data.append((k, clean(r[0]), (clean(r[1]) if len(r) > 1 else "") or ""))
        self.ci = {c: i for i, c, _ in self.cols}
        self.ri = {c: k for k, c, _ in self.data}
        self.title = clean(rows[0][0]) if rows and rows[0] else name
        self.unit_text = clean(rows[3][0]) if len(rows) > 3 and rows[3] else None

    @staticmethod
    def _find_header(rows):
        for k in range(min(12, len(rows))):
            r = rows[k]
            vals = [clean(x) for x in r[2:]] if r else []
            if sum(1 for v in vals if v) >= 3 and r and r[0] is not None and "상품" in str(r[0]):
                return k
        return 4

    def value(self, rcode, ccode):
        r = self.rows[self.ri[rcode]]
        i = self.ci[ccode]
        v = r[i] if i < len(r) else None
        return v

    def matrix(self, rcodes, ccodes):
        out = np.zeros((len(rcodes), len(ccodes)))
        cidx = [self.ci[c] for c in ccodes]
        for a, rc in enumerate(rcodes):
            r = self.rows[self.ri[rc]]
            for b, i in enumerate(cidx):
                v = r[i] if i < len(r) else None
                if v is None:
                    continue
                if isinstance(v, str):
                    v = v.replace(",", "").strip()
                    if v in ("", "-"):
                        continue
                out[a, b] = float(v)
        return out


def cell_unit(sheet, rcode, ccode):
    """원자료 셀의 단위(시트·행·열 코드 기준)."""
    s = sheet
    if "거래표" in s:
        return "백만원"
    if "항목별" in s:
        if rcode == "9812":
            return "%"
        if rcode == "9811":
            return "배(유발계수)"
        return "백만원"
    if "투입계수" in s:
        if ccode == "9090":
            return "비율(행 합계÷전산업 총투입)"
        return "계수(투입액÷총투입액)"
    if "유발계수" in s:
        if rcode == "9801" or ccode == "9802":
            return "지수(전산업 평균=1)"
        if rcode == "9590":
            return "열합(계수)"
        if ccode == "9090":
            return "행합(계수)"
        kind = "생산" if s.startswith("생산") else ("수입" if s.startswith("수입") else "부가가치")
        return "계수(최종수요 1단위당 %s유발)" % kind
    return "원표 표기 확인"


# ---------------------------------------------------------------- 분류 수준 객체
class Level:
    def __init__(self, key, book):
        self.key = key
        self.label = LEVEL_LABEL.get(key, key)
        self.book = book
        self.sheets = {n: Sheet(n, rows) for n, rows in book.items()}
        for need in (SHEET_TOTAL, SHEET_IMP, SHEET_DOM):
            if need not in self.sheets:
                raise ValueError("필수 시트가 없습니다: " + need)
        T = self.sheets[SHEET_TOTAL]
        D = self.sheets[SHEET_DOM]
        M = self.sheets[SHEET_IMP]
        self.codes = [c for _, c, _ in T.data if not is_agg_code(c)]
        self.names = [n for _, c, n in T.data if not is_agg_code(c)]
        colcodes = [c for _, c, _ in T.cols if not is_agg_code(c)]
        if colcodes != self.codes:
            raise ValueError("행·열 부문 코드가 일치하지 않습니다.")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError("부문 코드가 중복됩니다.")
        self.n = n = len(self.codes)
        self.idx = {c: i for i, c in enumerate(self.codes)}
        cs = self.codes
        # 거래표
        self.Z = T.matrix(cs, cs)
        self.Zd = D.matrix(cs, cs)
        self.Zm = M.matrix(cs, cs)
        self.F = T.matrix(cs, FD_CODES)
        self.Fd = D.matrix(cs, FD_CODES)
        self.Fm = M.matrix(cs, FD_CODES)
        tc = ["9090", "9190", "9290", "9310", "9321", "9322", "9329", "9331", "9332", "9390"]
        X = T.matrix(cs, tc)
        (self.int_dem, self.fin_dem, self.tot_dem, self.x, self.imp, self.imp_tax,
         self.imp_tot, self.margin, self.freight, self.tot_sup) = [X[:, k] for k in range(len(tc))]
        self.VA = T.matrix(VA_CODES, cs)            # 4 x n
        self.va = T.matrix(["9690"], cs)[0]
        self.int_in = T.matrix(["9590"], cs)[0]
        # 계수
        self.Ad = safe_div(self.Zd, self.x[None, :])
        self.Am = safe_div(self.Zm, self.x[None, :])
        self.A = safe_div(self.Z, self.x[None, :])
        self.v = safe_div(self.va, self.x)
        self.vcomp = safe_div(self.VA, self.x[None, :])   # 4 x n
        self.L = np.linalg.inv(np.eye(n) - self.Ad)
        self.Mi = self.Am @ self.L
        self.Vi = self.v[:, None] * self.L
        self.zero_output = [cs[i] for i in range(n) if self.x[i] == 0]
        self.check = self._validate()

    # 원표와 재계산 결과 대조
    def _validate(self):
        res = {}
        cs = self.codes
        res["총거래=국산+수입(중간)"] = float(np.abs(self.Z - self.Zd - self.Zm).max())
        res["총거래=국산+수입(최종)"] = float(np.abs(self.F - self.Fd - self.Fm).max())
        res["산출=국산 중간+최종수요"] = float(np.abs(self.Zd.sum(1) + self.Fd.sum(1) - self.x).max())
        res["총투입=중간투입+부가가치"] = float(np.abs(self.Z.sum(0) + self.va - self.x).max())
        res["총공급=총수요"] = float(np.abs(self.tot_sup - self.tot_dem).max())
        res["수입계=수입 중간+최종"] = float(np.abs(self.Zm.sum(1) + self.Fm.sum(1) - self.imp_tot).max())
        coef = {}

        def cmp(sheet, mat):
            if sheet not in self.sheets:
                return None
            S = self.sheets[sheet]
            try:
                return float(np.abs(S.matrix(cs, cs) - mat).max())
            except KeyError:
                return None

        coef["총투입계수(A)"] = cmp("총투입계수(A)", self.A)
        coef["국산투입계수(Ad)"] = cmp("국산투입계수(Ad)", self.Ad)
        coef["수입투입계수(Am)"] = cmp("수입투입계수(Am)", self.Am)
        coef["생산유발계수 L=(I-Ad)^-1"] = cmp("생산유발계수", self.L)
        coef["수입유발계수 Am·L"] = cmp("수입유발계수", self.Mi)
        coef["부가가치유발계수 v̂·L"] = cmp("부가가치유발계수", self.Vi)
        if "생산유발계수" in self.sheets:
            S = self.sheets["생산유발계수"]
            cs_ = self.L.sum(0)
            rs_ = self.L.sum(1)
            try:
                inf = S.matrix(["9801"], cs)[0]
                sen = S.matrix(cs, ["9802"])[:, 0]
                coef["영향력계수"] = float(np.abs(cs_ / cs_.mean() - inf).max())
                coef["감응도계수"] = float(np.abs(rs_ / rs_.mean() - sen).max())
            except KeyError:
                pass
        prod = self.L @ self.Fd
        for sheet, mat in (("최종수요 항목별 생산유발액", prod),
                           ("최종수요 항목별 부가가치유발액", self.v[:, None] * prod),
                           ("최종수요 항목별 수입유발액", self.Am @ prod + self.Fm)):
            if sheet in self.sheets:
                try:
                    official = self.sheets[sheet].matrix(cs, FD_CODES)
                    scale = max(1.0, float(np.abs(official).max()))
                    coef[sheet + "(상대오차)"] = float(np.abs(official - mat).max() / scale)
                except KeyError:
                    pass
        worst = max([v for v in coef.values() if v is not None] + [0.0])
        ok_id = max(res.values()) < 0.5   # 백만원 정수 자료: 반올림 허용 0.5
        return {"identities": res, "coefficients": coef, "max_coef_residual": worst,
                "passed": bool(ok_id and worst < 1e-6)}

    # 공통 계수
    def multipliers(self):
        prod = self.L.sum(0)
        rows = self.L.sum(1)
        return {
            "prod": prod,
            "va": self.v @ self.L,
            "imp": self.Am.sum(0) @ self.L,
            "influence": prod / prod.mean(),
            "sensitivity": rows / rows.mean(),
        }

    def emp_coef(self):
        """(취업계수, 고용계수, 정확여부) — 명/백만원. 대분류는 통계표 취업자수로 정확, 하위 분류는 대분류 계수 적용."""
        emp = AUX.get("emp")
        if not emp:
            return None
        large = emp["large_codes"]
        e_l = dict(zip(large, emp["e"]))
        w_l = dict(zip(large, emp["w"]))
        if self.key == "large":
            e = np.array([e_l.get(c, 0.0) for c in self.codes])
            w = np.array([w_l.get(c, 0.0) for c in self.codes])
            return e, w, True
        par = AUX["parent"].get(self.key)
        if not par:
            return None
        e = np.array([e_l.get(par.get(c), 0.0) for c in self.codes])
        w = np.array([w_l.get(par.get(c), 0.0) for c in self.codes])
        return e, w, False

    def sectors(self):
        return [{"code": c, "name": n} for c, n in zip(self.codes, self.names)]


# ---------------------------------------------------------------- 불러오기
def load_level(key, raw):
    if key not in LEVEL_LABEL:
        raise ValueError("알 수 없는 분류: " + str(key))
    book = read_book(raw)
    lv = Level(key, book)
    expect = {"basic": 380, "small": 165, "mid": 83, "large": 33}[key]
    if lv.n != expect:
        raise ValueError("%s 파일의 부문 수가 %d개입니다(기대값 %d)." % (lv.label, lv.n, expect))
    LV[key] = lv
    return emit(level_info(key))


def level_info(key):
    lv = LV[key]
    T = lv.sheets[SHEET_TOTAL]
    return {
        "key": key, "label": lv.label, "n": lv.n, "sectors": lv.sectors(),
        "sheets": list(lv.sheets.keys()), "check": lv.check,
        "zero_output": lv.zero_output, "title": T.title,
        "totals": {"output": float(lv.x.sum()), "va": float(lv.va.sum()),
                   "imports": float(lv.imp_tot.sum()), "final_demand": float(lv.F.sum())},
    }


def load_aux(cls_raw, stats_raw):
    """부문분류표 + 통계표 불러오기 (어느 분류든 처음 불러올 때 함께 읽음)."""
    if cls_raw is not None:
        _parse_classification(read_book(cls_raw))
    if stats_raw is not None:
        AUX["stats"] = read_book(stats_raw)
        _parse_employment()
    return emit({"classification": AUX["cls"] is not None and len(AUX["cls"]["rows"]),
                 "stats_sheets": list(AUX["stats"].keys()) if AUX["stats"] else [],
                 "employment": bool(AUX["emp"])})


def _parse_classification(book):
    name = list(book.keys())[0]
    rows = book[name]
    cur = [None] * 8
    out = []
    for r in rows[3:]:
        c0 = clean(r[0]) if r else None
        if c0 is None or is_agg_code(c0):
            continue
        for j in range(4):
            c = clean(r[2 * j]) if len(r) > 2 * j else None
            n = clean(r[2 * j + 1]) if len(r) > 2 * j + 1 else None
            if c:
                cur[2 * j] = c
                cur[2 * j + 1] = n
        out.append({"basic": cur[0], "basic_name": cur[1], "small": cur[2], "small_name": cur[3],
                    "mid": cur[4], "mid_name": cur[5], "large": cur[6], "large_name": cur[7]})
    if len(out) != 380:
        raise ValueError("부문분류표 해석 오류: 기본부문 %d개" % len(out))
    AUX["cls"] = {"sheet": name, "rows": out}
    par = {"basic": {}, "small": {}, "mid": {}}
    for r in out:
        par["basic"][r["basic"]] = r["large"]
        par["small"][r["small"]] = r["large"]
        par["mid"][r["mid"]] = r["large"]
    AUX["parent"] = par


STATS_UNITS = {
    "1": "조원, %, %p", "2": "조원, %, %p", "3": "%, %p", "4": "%, %p", "5": "%, %p", "6": "%, %p",
    "7": "조원, %, %p", "8": "조원, %, %p", "9": "%, %p", "10": "%, %p",
    "11": "계수(최종수요 1단위당)", "12": "계수(최종수요 1단위당)", "13": "계수(최종수요 1단위당)",
    "14": "지수(전산업 평균=1)", "15": "조원(유발액), 계수, %(의존도)",
    "16": "천명, %, %p", "17": "천명, %, %p", "18": "명/10억원", "19": "명/10억원", "20": "명/10억원",
}


def _stats_rows(sheet):
    """통계표 시트를 (라벨, 숫자목록) 행 목록으로."""
    out = []
    for r in AUX["stats"].get(sheet, []):
        if not r:
            continue
        label = None
        nums = []
        for v in r:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if label is not None:
                    nums.append(float(v))
            elif v is not None and clean(v) and label is None and not nums:
                label = str(v)
        if label is not None and nums:
            out.append((label, nums))
    return out


def _find_stats_sheet(prefix):
    for s in (AUX["stats"] or {}):
        if s.startswith(prefix + "."):
            return s
    return None


def _parse_employment():
    """통계표 16(취업자수)·17(임금근로자수)에서 2023년 대분류별 인원 추출 → 취업·고용계수."""
    AUX["emp"] = None
    s16, s17 = _find_stats_sheet("16"), _find_stats_sheet("17")
    if not s16 or not s17 or "large" not in LV:
        return
    lv = LV["large"]
    target = {norm(n): c for c, n in zip(lv.codes, lv.names)}

    def pick(sheet):
        got = {}
        for label, nums in _stats_rows(sheet):
            k = norm(label)
            if k in target and len(nums) >= 7 and target[k] not in got:
                got[target[k]] = nums[6] * 1000.0   # 2023년 값, 천명 → 명
        return got

    e16, e17 = pick(s16), pick(s17)
    if len(e16) != 33 or len(e17) != 33:
        return
    workers = np.array([e16[c] for c in lv.codes])
    wage = np.array([e17[c] for c in lv.codes])
    AUX["emp"] = {"large_codes": lv.codes, "workers": workers, "wage": wage,
                  "e": safe_div(workers, lv.x), "w": safe_div(wage, lv.x)}


def ensure_employment():
    if AUX["emp"] is None and AUX["stats"] is not None and "large" in LV:
        _parse_employment()
    return AUX["emp"] is not None


# ---------------------------------------------------------------- 1. 원자료 탐색
def explore(dataset, sheet, mode, code):
    if dataset == "stats":
        return emit(_explore_stats(sheet))
    if dataset == "cls":
        return emit(_explore_cls())
    lv = LV[dataset]
    S = lv.sheets[sheet]
    rows = [{"code": c, "name": n} for _, c, n in S.data]
    cols = [{"code": c, "name": n} for _, c, n in S.cols]
    if mode == "col":
        ccode = code if code in S.ci else S.cols[0][1]
        i = S.ci[ccode]
        cells = []
        for k, c, n in S.data:
            r = S.rows[k]
            v = r[i] if i < len(r) else None
            cells.append({"code": c, "name": n, "value": _cell(v), "unit": cell_unit(sheet, c, ccode)})
        name = next(n for _, c, n in S.cols if c == ccode)
        return emit({"mode": "col", "rows": rows, "cols": cols, "selected": ccode, "name": name,
                     "cells": cells, "title": S.title, "unit": S.unit_text or "계수표(무단위) — 셀별 단위 열 참조"})
    rcode = code if code in S.ri else S.data[0][1]
    r = S.rows[S.ri[rcode]]
    cells = []
    for i, c, n in S.cols:
        v = r[i] if i < len(r) else None
        cells.append({"code": c, "name": n, "value": _cell(v), "unit": cell_unit(sheet, rcode, c)})
    name = next(n for _, c, n in S.data if c == rcode)
    return emit({"mode": "row", "rows": rows, "cols": cols, "selected": rcode, "name": name,
                 "cells": cells, "title": S.title, "unit": S.unit_text or "계수표(무단위) — 셀별 단위 열 참조"})


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return fnum(v)
    return str(v)


def _explore_stats(sheet):
    rows = AUX["stats"][sheet]
    grid = []
    for r in rows:
        vals = [_cell(v) for v in r]
        while vals and (vals[-1] is None or vals[-1] == ""):
            vals.pop()
        if any(v not in (None, "") and str(v).strip() for v in vals):
            grid.append([("" if v is None else v) for v in vals])
    width = max((len(g) for g in grid), default=0)
    # 완전히 빈 열 제거
    keep = [j for j in range(width) if any(j < len(g) and str(g[j]).strip() != "" for g in grid)]
    grid = [[(g[j] if j < len(g) else "") for j in keep] for g in grid]
    num = sheet.split(".")[0]
    return {"mode": "grid", "grid": grid, "title": sheet, "unit": STATS_UNITS.get(num, "시트 상단 표기 참조")}


def _explore_cls():
    return {"mode": "cls", "rows": AUX["cls"]["rows"] if AUX["cls"] else []}


def search(q):
    """4개 분류 연계 검색: 코드·명칭 일부로 기본부문~대분류 계층을 찾음."""
    q = (q or "").strip()
    if not AUX["cls"]:
        return emit({"rows": []})
    out = []
    ql = q.lower()
    for r in AUX["cls"]["rows"]:
        hay = " ".join(str(r[k]) for k in r).lower()
        if not q or ql in hay:
            out.append(dict(r))
    out = out[:400]
    for r in out:
        for key, col in (("basic", "basic"), ("small", "small"), ("mid", "mid"), ("large", "large")):
            lv = LV.get(key)
            if lv and r[col] in lv.idx:
                r[key + "_x"] = float(lv.x[lv.idx[r[col]]])
    return emit({"rows": out, "loaded": [k for k in LEVEL_ORDER if k in LV]})


# ---------------------------------------------------------------- 2. 산업구조 지표
def structure(key):
    lv = LV[key]
    zcol = lv.Z.sum(0)
    zdcol = lv.Zd.sum(0)
    zmcol = lv.Zm.sum(0)
    exp = lv.F[:, FD_CODES.index("9140")]
    cons = lv.F[:, 0] + lv.F[:, 1]
    inv = lv.F[:, 2:6].sum(1)
    rows = []
    for i, (c, n) in enumerate(zip(lv.codes, lv.names)):
        x = lv.x[i]
        rows.append({
            "code": c, "name": n,
            "output": fnum(x), "va": fnum(lv.va[i]), "int_in": fnum(zcol[i]),
            "imports": fnum(lv.imp_tot[i]), "exports": fnum(exp[i]), "supply": fnum(lv.tot_sup[i]),
            "va_rate": fnum(safe_div(lv.va[i], x) * 100),
            "int_rate": fnum(safe_div(zcol[i], x) * 100),
            "dom_rate": fnum(safe_div(zdcol[i], zcol[i]) * 100),
            "dom_int_rate": fnum(safe_div(zdcol[i], x) * 100),
            "imp_dep": fnum(safe_div(zmcol[i], x) * 100),
            "export_rate": fnum(safe_div(exp[i], x) * 100),
            "import_rate": fnum(safe_div(lv.imp_tot[i], lv.tot_sup[i]) * 100),
            "int_dem_rate": fnum(safe_div(lv.int_dem[i], lv.tot_dem[i]) * 100),
            "wage_share": fnum(safe_div(lv.VA[0, i], lv.va[i]) * 100),
            "output_share": fnum(safe_div(x, lv.x.sum()) * 100),
            "va_share": fnum(safe_div(lv.va[i], lv.va.sum()) * 100),
            "cons": fnum(cons[i]), "inv": fnum(inv[i]),
        })
    return emit({"level": key, "label": lv.label, "rows": rows, "macro": _macro(lv)})


def _macro(lv):
    tri = 1e6  # 백만원 → 조원
    X = lv.x.sum()
    Zc = lv.Z.sum()
    Zd = lv.Zd.sum()
    Zm = lv.Zm.sum()
    VA = lv.va.sum()
    imp = lv.imp_tot.sum()
    exp = lv.F[:, 6].sum()
    sup = lv.tot_sup.sum()
    dom_fd = lv.F[:, :6].sum()
    m = {
        "총공급(=총수요)": (sup / tri, "조원"), "총산출": (X / tri, "조원"), "수입": (imp / tri, "조원"),
        "중간투입": (Zc / tri, "조원"), "부가가치": (VA / tri, "조원"), "수출": (exp / tri, "조원"),
        "국내 최종수요(소비+투자)": (dom_fd / tri, "조원"),
        "중간투입률": (Zc / X * 100, "%"), "부가가치율": (VA / X * 100, "%"),
        "수입의존도(수입 중간투입률)": (Zm / X * 100, "%"), "국산화율": (Zd / Zc * 100, "%"),
        "국산 중간투입률": (Zd / X * 100, "%"), "수출률": (exp / X * 100, "%"),
        "수입률": (imp / sup * 100, "%"), "대외거래 비중": ((exp + imp) / sup * 100, "%"),
        "피용자보수 비중(부가가치 중)": (lv.VA[0].sum() / VA * 100, "%"),
        "영업잉여 비중(부가가치 중)": (lv.VA[1].sum() / VA * 100, "%"),
    }
    fd_tot = lv.F.sum()
    m["최종수요 중 소비 비중"] = (lv.F[:, :2].sum() / fd_tot * 100, "%")
    m["최종수요 중 투자 비중"] = (lv.F[:, 2:6].sum() / fd_tot * 100, "%")
    m["최종수요 중 수출 비중"] = (exp / fd_tot * 100, "%")
    return [{"name": k, "value": fnum(v), "unit": u} for k, (v, u) in m.items()]


# ---------------------------------------------------------------- 3. 투입·배분 구조
def linkage(key, code, top=15):
    lv = LV[key]
    j = lv.idx[code]
    x = lv.x[j]
    # 투입구조(열): j 부문이 생산을 위해 사들인 것
    inputs = []
    for i in np.argsort(-lv.Z[:, j])[:top]:
        if lv.Z[i, j] == 0:
            break
        inputs.append({"code": lv.codes[i], "name": lv.names[i], "total": fnum(lv.Z[i, j]),
                       "domestic": fnum(lv.Zd[i, j]), "imported": fnum(lv.Zm[i, j]),
                       "coef": fnum(lv.A[i, j]), "dcoef": fnum(lv.Ad[i, j])})
    va = [{"name": VA_NAMES[c], "value": fnum(lv.VA[k, j]), "coef": fnum(lv.vcomp[k, j])}
          for k, c in enumerate(VA_CODES)]
    # 배분구조(행): j 상품이 어디에 팔렸나(총거래 기준)
    sales = []
    for k in np.argsort(-lv.Z[j, :])[:top]:
        if lv.Z[j, k] == 0:
            break
        sales.append({"code": lv.codes[k], "name": lv.names[k], "total": fnum(lv.Z[j, k]),
                      "domestic": fnum(lv.Zd[j, k]), "imported": fnum(lv.Zm[j, k]),
                      "share": fnum(safe_div(lv.Z[j, k], lv.tot_dem[j]) * 100)})
    fd = [{"code": c, "name": FD_NAMES[c], "total": fnum(lv.F[j, a]), "domestic": fnum(lv.Fd[j, a]),
           "imported": fnum(lv.Fm[j, a]), "share": fnum(safe_div(lv.F[j, a], lv.tot_dem[j]) * 100)}
          for a, c in enumerate(FD_CODES)]
    mu = lv.multipliers()
    summary = {
        "output": fnum(x), "int_in": fnum(lv.Z[:, j].sum()), "va": fnum(lv.va[j]),
        "int_rate": fnum(safe_div(lv.Z[:, j].sum(), x) * 100),
        "va_rate": fnum(safe_div(lv.va[j], x) * 100),
        "imp_dep": fnum(safe_div(lv.Zm[:, j].sum(), x) * 100),
        "dom_rate": fnum(safe_div(lv.Zd[:, j].sum(), lv.Z[:, j].sum()) * 100),
        "int_dem": fnum(lv.int_dem[j]), "fin_dem": fnum(lv.fin_dem[j]), "tot_dem": fnum(lv.tot_dem[j]),
        "int_dem_rate": fnum(safe_div(lv.int_dem[j], lv.tot_dem[j]) * 100),
        "imports": fnum(lv.imp_tot[j]), "import_rate": fnum(safe_div(lv.imp_tot[j], lv.tot_sup[j]) * 100),
        "backward_direct": fnum(lv.Ad[:, j].sum()), "forward_direct": fnum(lv.Ad[j, :].sum()),
        "prod_mult": fnum(mu["prod"][j]), "influence": fnum(mu["influence"][j]),
        "sensitivity": fnum(mu["sensitivity"][j]),
    }
    return emit({"code": code, "name": lv.names[j], "summary": summary, "inputs": inputs,
                 "va": va, "sales": sales, "fd": fd})


# ---------------------------------------------------------------- 4. 유발계수·영향력/감응도
def multipliers(key):
    lv = LV[key]
    ensure_employment()
    mu = lv.multipliers()
    em = lv.emp_coef()
    if em:
        e, w, exact = em
        emp = (e @ lv.L) * 1000.0
        wag = (w @ lv.L) * 1000.0
    rows = []
    for i, (c, n) in enumerate(zip(lv.codes, lv.names)):
        inf, sen = mu["influence"][i], mu["sensitivity"][i]
        quad = ("Ⅰ 전·후방 모두 높음" if inf >= 1 and sen >= 1 else
                "Ⅱ 전방연쇄형(감응도↑)" if sen >= 1 else
                "Ⅳ 후방연쇄형(영향력↑)" if inf >= 1 else "Ⅲ 독립형(모두 낮음)")
        r = {"code": c, "name": n, "prod": fnum(mu["prod"][i]), "va": fnum(mu["va"][i]),
             "imp": fnum(mu["imp"][i]), "influence": fnum(inf), "sensitivity": fnum(sen),
             "quadrant": quad, "output": fnum(lv.x[i]), "zero": bool(lv.x[i] == 0)}
        if em:
            r["emp"] = fnum(emp[i])
            r["wage"] = fnum(wag[i])
            r["emp_coef"] = fnum(e[i] * 1000.0)
        rows.append(r)
    return emit({"level": key, "label": lv.label, "rows": rows,
                 "employment": bool(em), "employment_exact": bool(em and em[2])})


# ---------------------------------------------------------------- 5. 최종수요 항목별 유발효과
def fd_effects(key, item):
    lv = LV[key]
    ensure_employment()
    em = lv.emp_coef()
    prod_all = lv.L @ lv.Fd                       # n x 7
    imp_all = lv.Am @ prod_all + lv.Fm
    va_all = lv.v[:, None] * prod_all
    emp_all = (em[0][:, None] * prod_all) if em else None
    wag_all = (em[1][:, None] * prod_all) if em else None
    tot = {"prod": prod_all.sum(), "va": va_all.sum(), "imp": imp_all.sum()}
    if em:
        tot["emp"] = emp_all.sum()
        tot["wage"] = wag_all.sum()
    items = []
    for name, codes in FD_GROUPS:
        ks = [FD_CODES.index(c) for c in codes]
        fd_d = lv.Fd[:, ks].sum()
        fd_t = lv.F[:, ks].sum()
        p = prod_all[:, ks].sum()
        v = va_all[:, ks].sum()
        m = imp_all[:, ks].sum()
        r = {"name": name, "codes": codes, "fd_domestic": fnum(fd_d), "fd_total": fnum(fd_t),
             "prod": fnum(p), "va": fnum(v), "imp": fnum(m),
             "prod_coef": fnum(safe_div(p, fd_d)), "va_coef": fnum(safe_div(v, fd_d)),
             "imp_coef": fnum(safe_div(m, fd_t)),
             "prod_dep": fnum(safe_div(p, tot["prod"]) * 100), "va_dep": fnum(safe_div(v, tot["va"]) * 100),
             "imp_dep": fnum(safe_div(m, tot["imp"]) * 100),
             "sub": name not in ("소비", "투자", "수출", "최종수요계")}
        if em:
            ee = emp_all[:, ks].sum()
            ww = wag_all[:, ks].sum()
            r.update({"emp": fnum(ee), "wage": fnum(ww),
                      "emp_coef": fnum(safe_div(ee, fd_d) * 1000), "wage_coef": fnum(safe_div(ww, fd_d) * 1000),
                      "emp_dep": fnum(safe_div(ee, tot["emp"]) * 100), "wage_dep": fnum(safe_div(ww, tot["wage"]) * 100)})
        items.append(r)
    # 선택 항목의 부문별 유발액
    sel = next((c for n, c in FD_GROUPS if n == item), FD_CODES)
    ks = [FD_CODES.index(c) for c in sel]
    sector = []
    for i, (c, n) in enumerate(zip(lv.codes, lv.names)):
        r = {"code": c, "name": n, "fd": fnum(lv.Fd[i, ks].sum()), "prod": fnum(prod_all[i, ks].sum()),
             "va": fnum(va_all[i, ks].sum()), "imp": fnum(imp_all[i, ks].sum())}
        if em:
            r["emp"] = fnum(emp_all[i, ks].sum())
        sector.append(r)
    sector.sort(key=lambda r: -(r["prod"] or 0))
    return emit({"level": key, "label": lv.label, "items": items, "item": item, "sector": sector,
                 "employment": bool(em), "employment_exact": bool(em and em[2])})


# ---------------------------------------------------------------- 6. 수요충격 시뮬레이션
def simulate(key, payload):
    lv = LV[key]
    ensure_employment()
    p = json.loads(payload)
    shocks = p.get("shocks", [])
    mode = p.get("mode", "domestic")   # domestic: 국산품 최종수요 / total: 국산+수입 최종수요
    f_in = np.zeros(lv.n)
    for s in shocks:
        a = float(s["amount"])
        if not math.isfinite(a):
            raise ValueError("수요 변화액은 유한한 숫자여야 합니다.")
        if s["code"] not in lv.idx:
            raise ValueError("현재 분류에 없는 부문 코드: " + str(s["code"]))
        f_in[lv.idx[s["code"]]] += a
    if not np.any(f_in != 0):
        raise ValueError("0이 아닌 수요 변화액을 한 개 이상 입력하세요.")
    if mode == "total":
        ks = [0, 1, 2, 3, 6]     # 소비·고정자본형성·수출(재고·귀중품 제외)
        d = lv.Fd[:, ks].sum(1)
        t = lv.F[:, ks].sum(1)
        share = np.where(t > 0, safe_div(d, t), safe_div(lv.x, lv.x + lv.imp_tot))
    else:
        share = np.ones(lv.n)
    f = f_in * share                    # 국산품 최종수요 변화
    direct_imp = f_in - f               # 수입 완제품으로 충족되는 부분
    x = lv.L @ f
    indirect = x - f
    va_c = lv.vcomp * x[None, :]        # 4 x n
    va = lv.v * x
    imp_ind = lv.Am @ x
    imp = imp_ind + direct_imp
    em = lv.emp_coef()
    rows = []
    for i, (c, n) in enumerate(zip(lv.codes, lv.names)):
        r = {"code": c, "name": n, "demand": fnum(f[i]), "production": fnum(x[i]),
             "indirect": fnum(indirect[i]), "valueAdded": fnum(va[i]), "wage": fnum(va_c[0, i]),
             "imports": fnum(imp[i])}
        if em:
            r["emp"] = fnum(em[0][i] * x[i])
            r["wageEmp"] = fnum(em[1][i] * x[i])
        rows.append(r)
    rows.sort(key=lambda r: -abs(r["production"] or 0))
    tot = {
        "input": fnum(f_in.sum()), "demand": fnum(f.sum()), "directImports": fnum(direct_imp.sum()),
        "production": fnum(x.sum()), "direct": fnum(f.sum()), "indirect": fnum(indirect.sum()),
        "valueAdded": fnum(va.sum()), "imports": fnum(imp.sum()), "importsIndirect": fnum(imp_ind.sum()),
        "va_items": [{"name": VA_NAMES[c], "value": fnum(va_c[k].sum())} for k, c in enumerate(VA_CODES)],
        "prod_multiplier": fnum(safe_div(x.sum(), f.sum())) if f.sum() != 0 else None,
        "va_ratio": fnum(safe_div(va.sum(), f_in.sum())) if f_in.sum() != 0 else None,
    }
    if em:
        tot["emp"] = fnum(float(em[0] @ x))
        tot["wageEmp"] = fnum(float(em[1] @ x))
    return emit({"level": key, "label": lv.label, "mode": mode, "totals": tot, "rows": rows,
                 "employment": bool(em), "employment_exact": bool(em and em[2]),
                 "check": fnum(abs(va.sum() + imp.sum() - f_in.sum()))})


# ---------------------------------------------------------------- 7. 가격파급효과(레온티에프 가격모형)
def price(key, payload):
    """
    p' = p'Ad + pm'Am + v'  (생산자가격 기준, 비용 전가 100% 가정, 수요 불변)
    mode = domestic : 특정 국산품 가격 r% 외생 상승 → Δp_o' = r·Ad[k,o](I−Ad_oo)^-1
           import   : 특정 수입품 가격 r% 상승 → Δp' = r·Am[k,:](I−Ad)^-1
           va       : 부가가치 항목(피용자보수 등) r% 상승 → Δp' = r·(v_item)'(I−Ad)^-1
    """
    lv = LV[key]
    p = json.loads(payload)
    mode = p.get("mode", "import")
    r = float(p.get("rate", 10.0)) / 100.0
    if not math.isfinite(r):
        raise ValueError("상승률을 확인하세요.")
    n = lv.n
    dpm = np.zeros(n)
    if mode == "domestic":
        k = lv.idx[p["code"]]
        others = [i for i in range(n) if i != k]
        Aoo = lv.Ad[np.ix_(others, others)]
        dp_o = r * lv.Ad[k, others] @ np.linalg.inv(np.eye(n - 1) - Aoo)
        dp = np.zeros(n)
        dp[others] = dp_o
        dp[k] = r
        label = "%s(국산품) 가격 %.1f%% 상승" % (lv.names[k], r * 100)
    elif mode == "import":
        k = lv.idx[p["code"]]
        dp = r * lv.Am[k, :] @ lv.L
        dpm[k] = r
        label = "%s(수입품) 가격 %.1f%% 상승" % (lv.names[k], r * 100)
    else:
        item = p.get("item", "9610")
        if item == "all":
            vv = lv.v
            nm = "부가가치 전체"
        else:
            vv = lv.vcomp[VA_CODES.index(item)]
            nm = VA_NAMES[item]
        dp = r * vv @ lv.L
        label = "%s %.1f%% 상승" % (nm, r * 100)
    cons_d = lv.Fd[:, 0]
    cons_m = lv.Fm[:, 0]
    cons_idx = safe_div((cons_d * dp).sum() + (cons_m * dpm).sum(), cons_d.sum() + cons_m.sum())
    prod_idx = safe_div((lv.x * dp).sum(), lv.x.sum())
    fd_d = lv.Fd.sum(1)
    fd_m = lv.Fm.sum(1)
    fd_idx = safe_div((fd_d * dp).sum() + (fd_m * dpm).sum(), fd_d.sum() + fd_m.sum())
    rows = [{"code": c, "name": nm, "dp": fnum(dp[i] * 100), "output": fnum(lv.x[i])}
            for i, (c, nm) in enumerate(zip(lv.codes, lv.names))]
    rows.sort(key=lambda q: -abs(q["dp"] or 0))
    return emit({"level": key, "label": label, "rows": rows,
                 "indices": {"consumer": fnum(cons_idx * 100), "producer": fnum(prod_idx * 100),
                             "final": fnum(fd_idx * 100)}})


# ---------------------------------------------------------------- 8. 분류 수준 비교(집계 편의)
def compare(basic_code, amount):
    if not AUX["cls"]:
        raise ValueError("부문분류표가 필요합니다.")
    ensure_employment()
    row = next((r for r in AUX["cls"]["rows"] if r["basic"] == basic_code), None)
    if row is None:
        raise ValueError("기본부문 코드를 찾을 수 없습니다: " + str(basic_code))
    amount = float(amount)
    out = []
    for key in LEVEL_ORDER:
        lv = LV.get(key)
        code = row[key]
        if lv is None:
            out.append({"level": key, "label": LEVEL_LABEL[key], "loaded": False, "code": code,
                        "name": row[key + "_name"]})
            continue
        j = lv.idx[code]
        mu = lv.multipliers()
        f = np.zeros(lv.n)
        f[j] = amount
        x = lv.L @ f
        em = lv.emp_coef()
        r = {"level": key, "label": lv.label, "loaded": True, "code": code, "name": lv.names[j],
             "output": fnum(lv.x[j]), "va_rate": fnum(safe_div(lv.va[j], lv.x[j]) * 100),
             "imp_dep": fnum(safe_div(lv.Zm[:, j].sum(), lv.x[j]) * 100),
             "prod": fnum(mu["prod"][j]), "va": fnum(mu["va"][j]), "imp": fnum(mu["imp"][j]),
             "influence": fnum(mu["influence"][j]), "sensitivity": fnum(mu["sensitivity"][j]),
             "sim_prod": fnum(x.sum()), "sim_va": fnum(lv.v @ x), "sim_imp": fnum(lv.Am.sum(0) @ x)}
        if em:
            r["sim_emp"] = fnum(em[0] @ x)
            r["emp"] = fnum((em[0] @ lv.L)[j] * 1000)
            r["emp_exact"] = bool(em[2])
        out.append(r)
    # 상위 분류 안에서 기본부문의 비중
    members = {}
    if "basic" in LV:
        b = LV["basic"]
        xb = b.x[b.idx[basic_code]]
        for key in ("small", "mid", "large"):
            grp = [r["basic"] for r in AUX["cls"]["rows"] if r[key] == row[key]]
            tot = sum(b.x[b.idx[c]] for c in grp)
            members[key] = {"count": len(grp), "share": fnum(safe_div(xb, tot) * 100)}
    return emit({"basic": row, "amount": amount, "levels": out, "members": members})


def consistency():
    """불러온 분류 간 정합성: 하위 분류를 부문분류표로 합산 = 상위 분류 공식표?"""
    if not AUX["cls"]:
        return emit({"pairs": []})
    rows = AUX["cls"]["rows"]
    pairs = []
    for a, fine in enumerate(LEVEL_ORDER):
        for coarse in LEVEL_ORDER[a + 1:]:
            if fine not in LV or coarse not in LV:
                continue
            F, C = LV[fine], LV[coarse]
            mp = {}
            for r in rows:
                mp[r[fine]] = r[coarse]
            P = np.zeros((C.n, F.n))
            for i, c in enumerate(F.codes):
                P[C.idx[mp[c]], i] = 1.0
            d = {
                "중간거래(총)": float(np.abs(P @ F.Z @ P.T - C.Z).max()),
                "중간거래(국산)": float(np.abs(P @ F.Zd @ P.T - C.Zd).max()),
                "중간거래(수입)": float(np.abs(P @ F.Zm @ P.T - C.Zm).max()),
                "최종수요": float(np.abs(P @ F.F - C.F).max()),
                "총산출": float(np.abs(P @ F.x - C.x).max()),
                "부가가치": float(np.abs(F.VA @ P.T - C.VA).max()),
                "수입": float(np.abs(P @ F.imp_tot - C.imp_tot).max()),
            }
            pairs.append({"fine": F.label, "coarse": C.label, "diff": d, "passed": max(d.values()) < 0.5})
    return emit({"pairs": pairs})


# ---------------------------------------------------------------- 9. 보도자료·통계표 재현 검증
def _group_table(lv, groups):
    G = np.zeros((len(groups), lv.n))
    for g, (_, mem) in enumerate(groups):
        for c in mem:
            G[g, lv.idx[c]] = 1.0
    x = G @ lv.x
    Zd = G @ lv.Zd @ G.T
    Zm = G @ lv.Zm @ G.T
    va = G @ lv.va
    Ad = safe_div(Zd, x[None, :])
    Am = safe_div(Zm, x[None, :])
    L = np.linalg.inv(np.eye(len(x)) - Ad)
    out = {}
    emp = AUX.get("emp")
    for g, (name, mem) in enumerate(groups):
        d = {"prod": L[:, g].sum(), "va": safe_div(va, x) @ L[:, g], "imp": Am.sum(0) @ L[:, g]}
        if emp:
            wk = G @ emp["workers"]
            wg = G @ emp["wage"]
            d["emp"] = (safe_div(wk, x) @ L[:, g]) * 1000
            d["wage"] = (safe_div(wg, x) @ L[:, g]) * 1000
            d["emp_coef"] = safe_div(wk[g], x[g]) * 1000
            d["wage_coef"] = safe_div(wg[g], x[g]) * 1000
        cs = L.sum(0)
        rs = L.sum(1)
        d["influence"] = cs[g] / cs.mean()
        d["sensitivity"] = rs[g] / rs.mean()
        out[norm(name)] = d
    return out


def press_check():
    if "large" not in LV:
        raise ValueError("통합대분류(33) 자료를 먼저 불러오세요.")
    ensure_employment()
    lv = LV["large"]
    g1 = _group_table(lv, [("전산업", lv.codes)])
    g7 = _group_table(lv, GROUP7)
    g13 = _group_table(lv, GROUP13)
    g33 = _group_table(lv, [(n, [c]) for c, n in zip(lv.codes, lv.names)])
    macro = {m["name"]: m["value"] for m in _macro(lv)}
    checks = []
    for name, unit, val in PRESS_MACRO:
        mine = macro.get(name)
        checks.append({"table": "보도자료 본문(경제구조)", "label": name, "unit": unit, "official": val,
                       "computed": fnum(mine, 4), "ok": mine is not None and abs(round(mine, 1) - val) <= 0.051})

    def lookup(label):
        k = norm(label)
        if has_footnote(label):
            for g in (g1, g7, g13):
                if k in g:
                    return g[k]
        for g in (g33, g7, g13, g1):
            if k in g:
                return g[k]
        return None

    specs = [("11", "생산유발계수", "prod", 3, 3), ("12", "부가가치유발계수", "va", 3, 3),
             ("13", "수입유발계수", "imp", 3, 3), ("19", "취업유발계수", "emp", 3, 3),
             ("20", "고용유발계수", "wage", 3, 3)]
    if AUX["stats"]:
        for num, title, field, col, nd in specs:
            s = _find_stats_sheet(num)
            if not s:
                continue
            for label, nums in _stats_rows(s):
                if len(nums) < 4 or label.startswith("주"):
                    continue
                d = lookup(label)
                if d is None or field not in d:
                    continue
                off = nums[col]
                mine = float(d[field])
                checks.append({"table": "통계표 " + title, "label": clean(re.sub(r"\s+", " ", label)),
                               "unit": "명/10억원" if field in ("emp", "wage") else "계수",
                               "official": round(off, nd), "computed": fnum(mine, 4),
                               "ok": abs(mine - off) <= 0.6 * 10 ** (-nd) + 1e-9})
        s18 = _find_stats_sheet("18")
        if s18:
            for label, nums in _stats_rows(s18):
                d = lookup(label)
                if d is None or "emp_coef" not in d or len(nums) < 8:
                    continue
                for field, off, nm in (("emp_coef", nums[3], "취업계수"), ("wage_coef", nums[7], "고용계수")):
                    mine = float(d[field])
                    checks.append({"table": "통계표 " + nm, "label": clean(re.sub(r"\s+", " ", label)),
                                   "unit": "명/10억원", "official": round(off, 3), "computed": fnum(mine, 4),
                                   "ok": abs(mine - off) <= 0.0006})
        s15 = _find_stats_sheet("15")
        if s15:
            fd = json.loads(fd_effects("large", "최종수요계"))["items"]
            fdm = {norm(i["name"]): i for i in fd}
            block = 0
            for label, nums in _stats_rows(s15):
                k = norm(label)
                if k == "소비":
                    block += 1
                if k not in fdm or len(nums) < 8:
                    continue
                kind = {1: ("prod", "생산"), 2: ("va", "부가가치"), 3: ("imp", "수입")}.get(block)
                if not kind:
                    continue
                f, nm = kind
                it = fdm[k]
                off_amt, off_coef = nums[3], nums[7]
                mine_amt = it[f] / 1e6
                mine_coef = it[f + "_coef"]
                checks.append({"table": "통계표 최종수요 항목별 %s유발액" % nm, "label": clean(label),
                               "unit": "조원", "official": round(off_amt, 3), "computed": fnum(mine_amt, 4),
                               "ok": abs(mine_amt - off_amt) <= 0.0006})
                checks.append({"table": "통계표 최종수요 항목별 %s유발계수" % nm, "label": clean(label),
                               "unit": "계수", "official": round(off_coef, 3), "computed": fnum(mine_coef, 4),
                               "ok": abs(mine_coef - off_coef) <= 0.0006})
    # 보도자료 본문(14~15쪽) 노동유발효과 — 소수 첫째 자리 공표
    if AUX.get("emp"):
        fd = {norm(i["name"]): i for i in json.loads(fd_effects("large", "최종수요계"))["items"]}
        for nm, key, e_off, w_off in (("소비", "소비", 10.2, 7.5), ("투자", "투자", 8.0, 6.4),
                                      ("수출", "수출", 5.4, 4.1), ("전체", "최종수요계", 8.2, 6.2)):
            it = fd[norm(key)]
            for title, f, off in (("취업유발계수", "emp_coef", e_off), ("고용유발계수", "wage_coef", w_off)):
                checks.append({"table": "보도자료 본문(노동유발효과) 최종수요 항목별 " + title, "label": nm,
                               "unit": "명/10억원", "official": off, "computed": fnum(it[f], 4),
                               "ok": abs(round(it[f], 1) - off) <= 0.051})
    notes = {
        "국산 중간투입률": "보도자료 45.2%는 반올림된 중간투입률(58.8%)−수입의존도(13.6%)로 보임. 원자료 정밀값은 45.26%.",
        "전산업": "통계표의 전산업 취업·고용유발계수(8.163·6.164) 산식은 공개되지 않아 재현 불가(불확실). "
                 "총취업자÷국산 최종수요(1부문 통합표)로 계산한 8.205·6.196은 보도자료 본문 8.2명·6.2명과 일치.",
    }
    for c in checks:
        if c["ok"]:
            c["status"] = "일치"
            continue
        diff = abs((c["computed"] or 0) - c["official"])
        c["status"] = "반올림 차이" if diff <= 0.1 and c["unit"] == "%" else "불일치(설명 참조)"
        for k, v in notes.items():
            if k in norm(c["label"]) or k in c["label"]:
                c["note"] = v
    ok = sum(1 for c in checks if c["ok"])
    return emit({"checks": checks, "ok": ok, "total": len(checks),
                 "groups": {"7": [g for g, _ in GROUP7], "13": [g for g, _ in GROUP13]}})
