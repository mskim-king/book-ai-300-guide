#!/usr/bin/env python3
"""tools/diagrams.yaml 에 정의한 설명 이미지를 assets/*.png 로 만듭니다.

사용법:
    python tools/build_diagrams.py            # 전체 다시 만들기
    python tools/build_diagrams.py ch01       # 파일 이름에 'ch01' 이 들어간 것만

필요한 것: Python(pyyaml), Node.js + Playwright(Chromium), 한글 글꼴(Noto Sans CJK KR)
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

COLORS = {  # (진한 색, 연한 배경)
    "blue": ("#2563EB", "#EFF6FF"), "green": ("#16A34A", "#F0FDF4"),
    "orange": ("#EA580C", "#FFF7ED"), "purple": ("#7C3AED", "#F5F3FF"),
    "red": ("#DC2626", "#FEF2F2"), "teal": ("#0D9488", "#F0FDFA"),
    "gray": ("#475569", "#F1F5F9"),
}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #fff; font-family: 'Noto Sans CJK KR', 'Noto Sans KR', sans-serif; color: #0F172A; }
#c { width: 1200px; padding: 48px 56px 44px; background: linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 100%); }
h1 { font-size: 40px; font-weight: 700; letter-spacing: -0.5px; }
.sub { margin-top: 10px; font-size: 22px; color: #475569; }
.body { margin-top: 36px; }
.icon { font-size: 44px; line-height: 1; font-family: 'Noto Color Emoji', sans-serif; }
.t { font-size: 24px; font-weight: 700; margin-top: 14px; }
.d { font-size: 18px; color: #334155; margin-top: 10px; line-height: 1.5; white-space: pre-line; }
.note { margin-top: 32px; padding: 18px 24px; border-radius: 14px; background: #0F172A; color: #fff;
        font-size: 20px; font-weight: 500; }
.note b { color: #FDE68A; }
/* flow */
.flow { display: flex; align-items: stretch; }
.step { flex: 1; background: #fff; border-radius: 18px; padding: 26px 18px 24px; text-align: center;
        border: 2px solid var(--c); box-shadow: 0 4px 14px rgba(15,23,42,.06); position: relative; }
.step .t { color: var(--c); }
.num { position: absolute; top: -16px; left: 50%; transform: translateX(-50%); width: 32px; height: 32px;
       border-radius: 50%; background: var(--c); color: #fff; font-size: 17px; font-weight: 700;
       display: flex; align-items: center; justify-content: center; }
.arrow { width: 44px; display: flex; align-items: center; justify-content: center; color: #94A3B8; font-size: 34px; flex: none; }
/* cards */
.grid { display: grid; gap: 20px; }
.card { background: var(--b); border-radius: 18px; padding: 26px 22px; border-top: 6px solid var(--c); }
.card .t { color: var(--c); }
/* compare */
.cmp { display: grid; grid-template-columns: 1fr 70px 1fr; align-items: stretch; }
.col { border-radius: 18px; padding: 26px 28px; }
.col h2 { font-size: 26px; margin-bottom: 16px; }
.col li { list-style: none; font-size: 20px; line-height: 1.5; padding: 12px 16px; margin-top: 10px;
          background: #fff; border-radius: 10px; }
.bad { background: #FEF2F2; border: 2px solid #FCA5A5; } .bad h2 { color: #DC2626; }
.good { background: #F0FDF4; border: 2px solid #86EFAC; } .good h2 { color: #16A34A; }
.bad li::before { content: '✕  '; color: #DC2626; font-weight: 700; }
.good li::before { content: '✓  '; color: #16A34A; font-weight: 700; }
.mid { display: flex; align-items: center; justify-content: center; font-size: 40px; color: #94A3B8; }
/* matrix */
.mx { display: grid; grid-template-columns: 200px 1fr 1fr; grid-template-rows: 56px 1fr 1fr; gap: 16px; }
.ax { display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 700;
      color: #334155; background: #E2E8F0; border-radius: 12px; text-align: center; padding: 8px; }
.cell { background: var(--b); border: 2px solid var(--c); border-radius: 18px; padding: 26px; text-align: center; }
.cell .t { color: var(--c); }
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def style(color: str) -> str:
    c, b = COLORS.get(color or "blue", COLORS["blue"])
    return f"--c:{c};--b:{b}"


def note_html(note: str | None) -> str:
    return f'<div class="note">💡 {esc(note)}</div>' if note else ""


def flow(d: dict) -> str:
    parts = []
    for i, s in enumerate(d["steps"], 1):
        if i > 1:
            parts.append('<div class="arrow">➜</div>')
        parts.append(f'<div class="step" style="{style(s.get("color"))}"><div class="num">{i}</div>'
                     f'<div class="icon">{esc(s.get("icon"))}</div><div class="t">{esc(s["title"])}</div>'
                     f'<div class="d">{esc(s.get("desc"))}</div></div>')
    return f'<div class="flow">{"".join(parts)}</div>'


def cards(d: dict) -> str:
    cols = d.get("columns", 3)
    items = "".join(
        f'<div class="card" style="{style(c.get("color"))}"><div class="icon">{esc(c.get("icon"))}</div>'
        f'<div class="t">{esc(c["title"])}</div><div class="d">{esc(c.get("desc"))}</div></div>'
        for c in d["cards"])
    return f'<div class="grid" style="grid-template-columns:repeat({cols},1fr)">{items}</div>'


def compare(d: dict) -> str:
    def col(side: dict, cls: str) -> str:
        lis = "".join(f"<li>{esc(x)}</li>" for x in side["items"])
        return f'<div class="col {cls}"><h2>{esc(side["title"])}</h2><ul>{lis}</ul></div>'
    return f'<div class="cmp">{col(d["left"], "bad")}<div class="mid">➜</div>{col(d["right"], "good")}</div>'


def matrix(d: dict) -> str:
    x, y, c = d["x_axis"], d["y_axis"], d["cells"]

    def cell(k: dict) -> str:
        return (f'<div class="cell" style="{style(k.get("color"))}"><div class="icon">{esc(k.get("icon"))}</div>'
                f'<div class="t">{esc(k["title"])}</div><div class="d">{esc(k.get("desc"))}</div></div>')
    return (f'<div class="mx"><div></div><div class="ax">{esc(x[0])}</div><div class="ax">{esc(x[1])}</div>'
            f'<div class="ax">{esc(y[0])}</div>{cell(c[0])}{cell(c[1])}'
            f'<div class="ax">{esc(y[1])}</div>{cell(c[2])}{cell(c[3])}</div>')


LAYOUTS = {"flow": flow, "cards": cards, "compare": compare, "matrix": matrix}


def page(d: dict) -> str:
    sub = f'<div class="sub">{esc(d["subtitle"])}</div>' if d.get("subtitle") else ""
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
            f'<div id="c"><h1>{esc(d["title"])}</h1>{sub}<div class="body">{LAYOUTS[d["layout"]](d)}</div>'
            f'{note_html(d.get("note"))}</div></body></html>')


SHOT_JS = """
const { chromium } = require('playwright');
const jobs = JSON.parse(process.argv[2]);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: 2 });
  for (const j of jobs) {
    await page.goto('file://' + j.html);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#c').screenshot({ path: j.png });
    console.log('  ✓ ' + j.name);
  }
  await browser.close();
})();
"""


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    data = yaml.safe_load((ROOT / "tools" / "diagrams.yaml").read_text(encoding="utf-8"))
    ASSETS.mkdir(exist_ok=True)
    jobs = []
    with tempfile.TemporaryDirectory() as tmp:
        for d in data["diagrams"]:
            if only and only not in d["file"]:
                continue
            if d["layout"] not in LAYOUTS:
                sys.exit(f"[오류] 알 수 없는 layout: {d['layout']} ({d['file']})")
            h = Path(tmp) / (Path(d["file"]).stem + ".html")
            h.write_text(page(d), encoding="utf-8")
            jobs.append({"html": str(h), "png": str(ASSETS / d["file"]), "name": d["file"]})
        if not jobs:
            sys.exit("만들 이미지가 없습니다.")
        print(f"[이미지 생성] {len(jobs)}개")
        js = Path(tmp) / "shot.js"
        js.write_text(SHOT_JS, encoding="utf-8")
        subprocess.run(["node", str(js), json.dumps(jobs)], check=True, cwd=tmp)


if __name__ == "__main__":
    main()
