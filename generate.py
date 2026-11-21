#!/usr/bin/env python3
"""structure.yaml 을 읽어 위키독스(GitHub 연동) 책 구조를 자동 생성합니다.

사용법:
    python generate.py            # 폴더·페이지 생성 + TOC.md / README.md 갱신
    python generate.py --check    # 무엇이 생길지 미리 보기 (파일 변경 없음)
    python generate.py --status   # 페이지별 작성 상태 표시

규칙:
- 이미 존재하는 페이지 파일은 절대 덮어쓰지 않습니다 (내용 보호).
- TOC.md 와 README.md 는 매번 structure.yaml 기준으로 다시 만듭니다.
- structure.yaml 에서 빠진 기존 파일은 지우지 않고 '고아 파일'로 알려줍니다.
- 페이지별로 `template: recipe` 처럼 다른 템플릿을 지정할 수 있습니다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
STATUS_RE = re.compile(r"\*\*상태\*\*:\s*([^\n]+?)\s*$", re.M)


def load_structure() -> dict:
    with open(ROOT / "structure.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    seen = set()
    for ch in data["chapters"]:
        for key in ("id", "slug", "title"):
            if key not in ch:
                sys.exit(f"[오류] 장(chapter)에 '{key}' 가 없습니다: {ch}")
        for p in ch.get("pages", []):
            path = page_path(ch, p)
            if path in seen:
                sys.exit(f"[오류] 중복 페이지 경로: {path}")
            seen.add(path)
            tpl = TEMPLATES / f"{p.get('template', 'page')}.md"
            if not tpl.exists():
                sys.exit(f"[오류] 템플릿 없음: {tpl.name} ({path})")
    return data


def chapter_dir(ch: dict) -> str:
    return f"{ch['id']}-{ch['slug']}"


def page_path(ch: dict, p: dict) -> str:
    return f"{chapter_dir(ch)}/{p['slug']}.md"


def chapter_index_path(ch: dict) -> str:
    return f"{chapter_dir(ch)}/index.md"


def render(template: str, **kw) -> str:
    text = (TEMPLATES / template).read_text(encoding="utf-8")
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def related_links(ch: dict, current: dict) -> str:
    lines = [f"- {p['title']}" for p in ch.get("pages", []) if p["slug"] != current["slug"]]
    for link in current.get("see_also", []):  # 다른 책 연결
        lines.append(f"- 📚 {link}")
    return "\n".join(lines) or "- "


def build_toc(data: dict) -> str:
    # ⚠ 위키독스 TOC.md 형식이 이 출력과 다르면 이 함수만 고치면 됩니다.
    #    (위키독스가 처음 만든 TOC.md 는 _관리/wikidocs-original/ 에 보관됩니다.)
    lines = []
    for ch in data["chapters"]:
        lines.append(f"- [{ch['id']}. {ch['title']}]({chapter_index_path(ch)})")
        for p in ch.get("pages", []):
            lines.append(f"    - [{p['title']}]({page_path(ch, p)})")
    return "\n".join(lines) + "\n"


def build_readme(data: dict, statuses: dict[str, str]) -> str:
    b = data["book"]
    total = sum(len(ch.get("pages", [])) for ch in data["chapters"])
    done = sum(1 for s in statuses.values() if "완료" in s)
    out = [
        f"# {b['title']}",
        "",
        f"**{b.get('subtitle', '')}**",
        "",
        b.get("description", "").strip(),
        "",
        f"- 저자: {b.get('author', '')}",
        f"- 대상 독자: {b.get('audience', '')}",
        f"- 진행률: {done}/{total} 페이지 완료",
        f"- 구조 갱신: {dt.date.today().isoformat()}",
        "",
        "## 목차",
        "",
    ]
    for ch in data["chapters"]:
        out.append(f"### {ch['id']}. {ch['title']}")
        for p in ch.get("pages", []):
            st = statuses.get(page_path(ch, p), "🟡 작성 중")
            out.append(f"- {p['title']} — {st}")
        out.append("")
    series = data.get("series")
    if series:
        out += [f"## 「{series['name']}」 시리즈의 다른 책", ""]
        for s in series.get("books", []):
            if s["title"] == b["title"]:
                continue
            out.append(f"- [{s['title']}]({s['url']})" if s.get("url") else f"- {s['title']}")
        out.append("")
    out += [
        "---",
        "> 이 README 와 TOC.md 는 `generate.py` 가 자동 생성합니다. "
        "구조를 바꾸려면 `structure.yaml` 을 수정하세요.",
        "",
    ]
    return "\n".join(out)


def read_status(path: Path) -> str:
    if not path.exists():
        return "⚪ 없음"
    m = STATUS_RE.search(path.read_text(encoding="utf-8"))
    return m.group(1).strip() if m else "❔ 미표시"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="변경 없이 미리 보기")
    ap.add_argument("--status", action="store_true", help="페이지 상태만 출력")
    args = ap.parse_args()
    dry = args.check or args.status

    data = load_structure()
    today = dt.date.today().isoformat()
    created, expected = [], set()

    for ch in data["chapters"]:
        d = ROOT / chapter_dir(ch)
        idx = ROOT / chapter_index_path(ch)
        expected.add(chapter_index_path(ch))
        if not idx.exists():
            created.append(chapter_index_path(ch))
            if not dry:
                d.mkdir(parents=True, exist_ok=True)
                page_list = "\n".join(f"- [{p['title']}]({p['slug']}.md)" for p in ch.get("pages", []))
                idx.write_text(render("chapter.md", chapter_title=f"{ch['id']}. {ch['title']}",
                                      chapter_summary=ch.get("summary", "이 장에서 다루는 내용입니다."),
                                      page_list=page_list), encoding="utf-8")
        for p in ch.get("pages", []):
            rel = page_path(ch, p)
            expected.add(rel)
            f = ROOT / rel
            if f.exists():
                continue
            created.append(rel)
            if dry:
                continue
            d.mkdir(parents=True, exist_ok=True)
            f.write_text(render(f"{p.get('template', 'page')}.md",
                                title=p["title"],
                                chapter_title=f"{ch['id']}. {ch['title']}",
                                tags=" ".join(f"#{t}" for t in p.get("tags", [])),
                                date=today,
                                related=related_links(ch, p)), encoding="utf-8")

    statuses = {page_path(ch, p): read_status(ROOT / page_path(ch, p))
                for ch in data["chapters"] for p in ch.get("pages", [])}

    if args.status:
        for path, st in statuses.items():
            print(f"{st:<10} {path}")
        return

    orphans = sorted(
        str(p.relative_to(ROOT)) for p in ROOT.glob("[0-9][0-9]-*/*.md")
        if str(p.relative_to(ROOT)) not in expected
    )

    if not args.check:
        (ROOT / "TOC.md").write_text(build_toc(data), encoding="utf-8")
        (ROOT / "README.md").write_text(build_readme(data, statuses), encoding="utf-8")

    label = "생성 예정" if args.check else "새로 생성"
    print(f"[{label}] {len(created)}개")
    for c in created:
        print(f"  + {c}")
    if orphans:
        print(f"[고아 파일] structure.yaml 에 없는 파일 {len(orphans)}개 (삭제하지 않음)")
        for o in orphans:
            print(f"  ? {o}")
    if not args.check:
        print("[갱신] TOC.md, README.md")


if __name__ == "__main__":
    main()
