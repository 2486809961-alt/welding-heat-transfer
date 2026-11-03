#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Obsidian vault「焊接传热学」构建成自包含静态站点（GitHub Pages）。

用法: python3 build_site.py [--src VAULT根目录] [--out public目录]
"""
import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

import markdown
import yaml

VAULT_DIRNAME = "焊接传热学"

# ---------------------------------------------------------------- frontmatter
FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def split_frontmatter(text: str):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[m.end():]


# ------------------------------------------------------------------ 数学/代码抽取
BLOCK_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$)([^\n$]+?)(?<!\\)\$")
MERMAID_RE = re.compile(r"```mermaid[ \t]*\n(.*?)```", re.S)


def protect(text: str, store: dict, kind: str, pattern: re.Pattern, wrap):
    def repl(m):
        key = f"@@{kind}{len(store)}@@"
        store[key] = wrap(m.group(1))
        return key
    return pattern.sub(repl, text)


def restore(text: str, store: dict):
    for _ in range(3):
        hit = False
        for k, v in store.items():
            if k in text:
                text = text.replace(k, v)
                hit = True
        if not hit:
            break
    return text


# ---------------------------------------------------------------------- wikilink
def build_linker(alias_map, page_url, titles):
    def repl(m):
        raw = m.group(1)
        target, _, alias = raw.partition("|")
        target = target.strip()
        alias = alias.strip()
        anchor = ""
        if "#" in target:
            target, _, anchor = target.partition("#")
            target = target.strip()
            anchor = anchor.strip()

        if target.lower().endswith(".pdf"):
            page = ""
            mm = re.search(r"page=(\d+)", anchor or "")
            if mm:
                page = f"第 {mm.group(1)} 页"
            label = alias or (f"原书 PDF {page}".strip())
            return f'<span class="pdf-ref" title="原书 PDF 引用（仓库不含 PDF）">📄 {html.escape(label)}</span>'

        if not target:  # [[#标题]] 站内锚点
            return f'<a href="#" class="wikilink">{html.escape(alias or anchor)}</a>'

        key = target.strip()
        url = alias_map.get(key) or alias_map.get(key.lower())
        label = alias or titles.get(key, key)
        if anchor and not anchor.startswith("page="):
            label = alias or f"{titles.get(key, key)} › {anchor}"
        if url:
            frag = f"#{quote(anchor)}" if anchor and not anchor.startswith("page=") else ""
            return (f'<a href="{page_url(url)}" class="wikilink" '
                    f'title="{html.escape(key)}">{html.escape(label)}</a>')
        return f'<span class="wikilink broken" title="库中未找到：{html.escape(key)}">{html.escape(label)}</span>'
    return repl


WIKILINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\][-+]?\s*(.*)$", re.M)


def transform_callouts(text: str) -> str:
    """把 Obsidian callout 变成 <div markdown='1'>。"""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^>\s*\[!(\w+)\][-+]?\s*(.*)$", lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        kind = m.group(1).lower()
        title = m.group(2).strip()
        body = []
        i += 1
        while i < len(lines) and lines[i].startswith(">"):
            body.append(re.sub(r"^>\s?", "", lines[i]))
            i += 1
        inner = "\n".join(body).strip("\n")
        title_html = f'<div class="callout-title">{title}</div>' if title else ""
        if inner:
            out.append(f'<div class="callout callout-{kind}" markdown="1">')
            if title_html:
                out.append(title_html)
            out.append(inner)
            out.append("</div>")
        else:
            out.append(f'<div class="callout callout-{kind}">{title_html}</div>')
    return "\n".join(out)


MD_EXT = ["tables", "fenced_code", "footnotes", "md_in_html", "sane_lists", "attr_list"]


def render_markdown(text: str, alias_map, page_url, titles, demote_h1: bool = False) -> str:
    store: dict[str, str] = {}

    if demote_h1:
        text = re.sub(r"^# (?!#)", "## ", text, flags=re.M)

    # 1) mermaid 必须先于通用代码块（否则 ```mermaid 被当普通代码吞掉）
    def mermaid(body):
        return f'<pre class="mermaid">{html.escape(body.strip())}</pre>'
    text = protect(text, store, "MER", MERMAID_RE, mermaid)

    # 2) 其余代码块保护（避免数学/链接规则污染代码）
    text = protect(text, store, "CODE",
                   re.compile(r"```[^\n`]*\n(.*?)```", re.S),
                   lambda body: f'<pre class="code-raw">{html.escape(body)}</pre>')

    # 3) 数学
    text = protect(text, store, "MB", BLOCK_MATH_RE, lambda b: f'<span class="math-block">$${b}$$</span>')
    text = protect(text, store, "MI", INLINE_MATH_RE, lambda b: f'<span class="math-inline">${b}$</span>')

    # 4) callout
    text = transform_callouts(text)

    # 5) wikilink（渲染前，避免 [] 被当链接语法）
    text = WIKILINK_RE.sub(build_linker(alias_map, page_url, titles), text)

    # 6) 行内杂项
    text = re.sub(r"==(.+?)==", r"<mark>\1</mark>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)

    md = markdown.Markdown(extensions=MD_EXT, output_format="html5")
    out = md.convert(text)
    md.reset()

    # 7) 外链新窗口
    out = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', out)
    # 8) 任务列表
    out = out.replace("<li>[ ] ", '<li class="task open">').replace("<li>[x] ", '<li class="task done">')
    out = restore(out, store)
    # 块公式独占一行（span -> div，避免嵌在 <p> 里）
    out = re.sub(r'<p>\s*(<span class="math-block">.*?</span>)\s*</p>',
                 lambda m: m.group(1).replace('math-block', 'math-block block'), out, flags=re.S)
    out = re.sub(r'<p>\s*(<pre class="(?:code-raw|mermaid)">.*?</pre>)\s*</p>', r'\1', out, flags=re.S)
    return out


# ------------------------------------------------------------------------- 构建
PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 焊接传热学知识库</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title} · 焊接传热学知识库">
<meta property="og:description" content="张文钺《焊接传热学》结构化 Obsidian 知识库：7 章 37 节 + 43 概念卡 + 公式库">
<meta property="og:type" content="article">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Crect width=%2732%27 height=%2732%27 rx=%278%27 fill=%27%237c5cff%27/%3E%3Ctext x=%2716%27 y=%2722%27 font-size=%2716%27 text-anchor=%27middle%27 fill=%27white%27 font-family=%27sans-serif%27%3E焊%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="stylesheet" href="{root}assets/katex/katex.min.css">
</head>
<body>
<header class="topbar">
  <button class="menu-btn" id="menuBtn" aria-label="目录">☰</button>
  <a class="brand" href="{root}index.html">焊接传热学<span class="brand-sub">Obsidian 知识库</span></a>
  <div class="search-wrap">
    <input id="searchInput" type="search" placeholder="搜索笔记 / 概念 / 公式…" autocomplete="off">
    <div id="searchResults" class="search-results"></div>
  </div>
  <a class="btn dl" href="{download}" target="_blank" rel="noopener">⬇︎ 下载整库</a>
  <button class="btn ghost" id="themeBtn" aria-label="切换主题">◐</button>
</header>
<div class="layout">
  <nav class="sidebar" id="sidebar">
    <div class="side-inner">{sidebar}</div>
  </nav>
  <main class="content">
    <article class="note">
{body}
    </article>
    <nav class="pager">{pager}</nav>
    <footer class="foot">
      <a href="{repo}" target="_blank" rel="noopener">GitHub 仓库</a> ·
      <a href="{root}index.html">首页</a> ·
      个人学习笔记，原书版权归作者与出版社所有
    </footer>
  </main>
</div>
<script>window.__ROOT__="{root}";</script>
<script src="{root}assets/katex/katex.min.js"></script>
<script defer src="{root}assets/katex/contrib/auto-render.min.js"></script>
<script src="{root}assets/mermaid.min.js"></script>
<script src="{root}assets/app.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".")
    ap.add_argument("--out", default="public")
    ap.add_argument("--base", default="/welding-heat-transfer/")
    ap.add_argument("--repo", default="https://github.com/2486809961-alt/welding-heat-transfer")
    ap.add_argument("--release", default="https://github.com/2486809961-alt/welding-heat-transfer/releases/latest")
    ap.add_argument("--name", default="焊接传热学")
    ap.add_argument("--deps", default="/tmp/site-deps/node_modules")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    vault = src / VAULT_DIRNAME
    if not vault.is_dir():
        sys.exit(f"找不到 {vault}")
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "notes").mkdir(parents=True)
    (out / "assets" / "katex").mkdir(parents=True, exist_ok=True)

    md_files = sorted(p for p in vault.rglob("*.md"))
    docs, by_name = [], {}
    for i, p in enumerate(md_files, 1):
        raw = p.read_text(encoding="utf-8", errors="replace")
        meta, body = split_frontmatter(raw)
        rel = p.relative_to(vault)
        rel_noext = rel.with_suffix("")
        title = rel_noext.name
        seq = f"{i:03d}"
        safe = re.sub(r"[\s/]+", "-", str(rel_noext))
        slug = f"notes/{seq}-{safe}.html"
        doc = dict(
            path=str(rel), rel=str(rel_noext), dir=str(rel_noext.parent),
            title=title, meta=meta, body=body, slug=slug, seq=i,
        )
        docs.append(doc)
        by_name[title] = slug
        by_name[title.lower()] = slug
        side = str(rel_noext)
        by_name[side] = slug
        by_name[side.lower()] = slug
        for a in (meta.get("aliases") or []):
            a = str(a).strip()
            if a:
                by_name.setdefault(a, slug)
                by_name.setdefault(a.lower(), slug)
    titles = {d["title"]: d["title"] for d in docs}

    # 目录树
    tree: dict[str, list] = {}
    for d in docs:
        tree.setdefault(d["dir"], []).append(d)
    dir_order = sorted(tree.keys(), key=lambda s: s)
    sidebar_html = ['<a class="side-home" href="index.html">🏠 首页</a>']
    for dr in dir_order:
        label = "根目录" if dr == "." else dr
        sidebar_html.append('<div class="side-group">')
        sidebar_html.append(f'<div class="side-group-label">{html.escape(label)}</div>')
        sidebar_html.append("<ul>")
        for d in sorted(tree[dr], key=lambda x: x["seq"]):
            t = d["meta"].get("type") or ""
            cls = "side-link" + (" type-card" if t == "概念" else "")
            sidebar_html.append(
                f'<li><a class="{cls}" href="{quote(d["slug"])}" data-title="{html.escape(d["title"])}">'
                f'{html.escape(d["title"])}</a></li>')
        sidebar_html.append("</ul></div>")
    sidebar = "\n".join(sidebar_html)

    # 侧栏是绝对根路径的，独立页面用相对
    def sidebar_for(root: str) -> str:
        return re.sub(r'href="(index\.html|notes/)', lambda m: f'href="{root}{m.group(1)}', sidebar)

    def page_url(slug: str) -> str:
        """在 notes/ 子目录内的页面里，链接到同目录文件。"""
        return quote(slug).replace("notes/", "", 1)

    def page_url_root(slug: str) -> str:
        """首页（位于站点根）里链接到笔记。"""
        return quote(slug)

    search_index = []
    for idx, d in enumerate(docs):
        for h in ():
            pass
        body_html = render_markdown(d["body"], by_name, page_url, titles, demote_h1=True)
        meta = d["meta"]
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        tag_html = "".join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tags)
        pagepos = ""
        for k, lbl in (("book_page", "书 p."), ("pdf_page", "PDF p."), ("chapter", "第 "), ("section", "")):
            v = meta.get(k)
            if v not in (None, "", 0, "0"):
                if k == "chapter":
                    pagepos += f'<span class="meta-chip">第 {html.escape(str(v))} 章</span>'
                else:
                    pagepos += f'<span class="meta-chip">{lbl}{html.escape(str(v))}</span>'
        crumb = d["rel"].replace("\\", "/")
        head = (f'<div class="note-head"><div class="crumb">{html.escape(crumb)}</div>'
                f'<h1>{html.escape(d["title"])}</h1>'
                f'<div class="meta-row">{tag_html}{pagepos}</div></div>')
        prev_d = docs[idx - 1] if idx > 0 else None
        next_d = docs[idx + 1] if idx + 1 < len(docs) else None
        pager = ""
        if prev_d:
            pager += f'<a class="prev" href="{quote(prev_d["slug"])}">← {html.escape(prev_d["title"])}</a>'
        if next_d:
            pager += f'<a class="next" href="{quote(next_d["slug"])}">{html.escape(next_d["title"])} →</a>'

        # 页面层级：notes/xxx.html → root = "../"
        root = "../"
        (out / d["slug"]).write_text(PAGE_TMPL.format(
            title=html.escape(d["title"]), desc=html.escape(crumb),
            root=root, sidebar=sidebar_for(root), body=head + body_html, pager=pager,
            download=args.release, repo=args.repo,
        ), encoding="utf-8")

        plain = re.sub(r"```.*?```", " ", d["body"], flags=re.S)
        plain = re.sub(r"[#>*`|\[\]()]|(@@\w+\d+@@)", " ", plain)
        plain = re.sub(r"\s+", " ", plain).strip()
        search_index.append({
            "t": d["title"], "u": d["slug"], "d": d["dir"],
            "g": " ".join(str(t) for t in tags), "x": plain[:1500],
        })

    (out / "assets" / "search.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8")

    # ---- 首页
    idx = next((d for d in docs if d["title"] == "焊接传热学 MOC"), docs[0])
    idx_html = render_markdown(idx["body"], by_name, page_url_root, titles)
    cards = []
    for dr in dir_order:
        if dr in (".",):
            continue
        n = len(tree[dr])
        desc = {"00 索引": "总入口 / 目录页码 / 公式总表 / 概念地图",
                "01 绪论": "研究对象与三条技术路线",
                "02 第一章 传热学基础": "热源、热效率、传热方式、温度场、边界条件",
                "03 第二章 温度场数学模型": "厚板/薄板/细棒/中厚板解析解",
                "04 第三章 热循环参数": "t8/5、冷却速度、热循环四参数",
                "05 第四章 数值积分": "加权余值、变分、差分格式",
                "06 第五章 有限差分": "显式/隐式格式与稳定性",
                "07 第六章 有限元": "单元、形函数、高斯热源",
                "08 第七章 热象法": "红外实测与热循环测定",
                "09 概念卡": "43 张原子概念卡，双向链接",
                "10 公式库": "公式总表 + t8/5 推导链",
                "11 附表数据": "erf / K₀ / Ei 查表用法",
                "12 术语": "中英术语对照"}.get(dr, "")
        first = sorted(tree[dr], key=lambda x: x["seq"])[0]
        cards.append(f'<a class="card" href="{quote(first["slug"])}">'
                     f'<div class="card-t">{html.escape(dr)}</div>'
                     f'<div class="card-d">{html.escape(desc)}</div>'
                     f'<div class="card-n">{n} 篇</div></a>')
    landing = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>焊接传热学 · Obsidian 知识库</title>
<meta name="description" content="张文钺《焊接传热学》结构化 Obsidian 知识库：7 章 37 节 + 43 概念卡 + 公式库，网页在线阅读，一键下载。">
<meta property="og:title" content="焊接传热学 · Obsidian 知识库">
<meta property="og:description" content="7 章 37 节 + 43 概念卡 + 公式库，每条结论可回溯原书页码。">
<meta property="og:type" content="website">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Crect width=%2732%27 height=%2732%27 rx=%278%27 fill=%27%237c5cff%27/%3E%3Ctext x=%2716%27 y=%2722%27 font-size=%2716%27 text-anchor=%27middle%27 fill=%27white%27 font-family=%27sans-serif%27%3E焊%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="assets/style.css">
<link rel="stylesheet" href="assets/katex/katex.min.css">
</head>
<body class="landing">
<header class="topbar">
  <a class="brand" href="index.html">焊接传热学<span class="brand-sub">Obsidian 知识库</span></a>
  <div class="search-wrap">
    <input id="searchInput" type="search" placeholder="搜索笔记 / 概念 / 公式…" autocomplete="off">
    <div id="searchResults" class="search-results"></div>
  </div>
  <a class="btn dl" href="{args.release}" target="_blank" rel="noopener">⬇︎ 下载整库</a>
  <button class="btn ghost" id="themeBtn" aria-label="切换主题">◐</button>
</header>
<main class="hero">
  <h1>{args.name}</h1>
  <p class="sub">{len(docs)} 篇笔记 · 7 章 37 节 + 绪论 · 43 张概念卡 · 公式全 LaTeX · 每条结论可回溯原书页码</p>
  <div class="cta">
    <a class="btn primary" href="{quote(idx['slug'])}">开始阅读 →</a>
    <a class="btn" href="{args.release}" target="_blank" rel="noopener">下载 zip（Obsidian 直接打开）</a>
    <a class="btn ghost" href="{args.repo}" target="_blank" rel="noopener">GitHub 仓库</a>
  </div>
  <div class="grid">{''.join(cards)}</div>
  <section class="intro">
{idx_html}
  </section>
  <footer class="foot">
    <a href="{args.repo}" target="_blank" rel="noopener">GitHub</a> ·
    原书版权归作者与出版社所有；本库为个人学习用的结构化笔记，仓库不含原书 PDF。
  </footer>
</main>
<script>window.__ROOT__="";</script>
<script src="assets/katex/katex.min.js"></script>
<script defer src="assets/katex/contrib/auto-render.min.js"></script>
<script src="assets/mermaid.min.js"></script>
<script src="assets/app.js"></script>
</body>
</html>
"""
    (out / "index.html").write_text(landing, encoding="utf-8")

    # ---- 资源
    deps = Path(args.deps)
    katex = deps / "katex" / "dist"
    if katex.is_dir():
        for name in ("katex.min.css", "katex.min.js"):
            shutil.copy(katex / name, out / "assets" / "katex" / name)
        (out / "assets" / "katex" / "contrib").mkdir(exist_ok=True)
        shutil.copy(katex / "contrib" / "auto-render.min.js",
                    out / "assets" / "katex" / "contrib" / "auto-render.min.js")
        fonts_src = katex / "fonts"
        fonts_dst = out / "assets" / "katex" / "fonts"
        fonts_dst.mkdir(exist_ok=True)
        for f in fonts_src.glob("*.woff2"):
            shutil.copy(f, fonts_dst / f.name)
        for f in fonts_src.glob("*.woff"):
            shutil.copy(f, fonts_dst / f.name)
        # 让 css 里的 fonts/ 路径可用
        css = (out / "assets" / "katex" / "katex.min.css").read_text(encoding="utf-8")
        (out / "assets" / "katex" / "katex.min.css").write_text(css, encoding="utf-8")
        print(f"  katex 资源已复制（{len(list(fonts_dst.iterdir()))} 个字体）")
    else:
        print("  ⚠ 未找到 katex dist，公式将无法渲染")

    mermaid_js = deps / "mermaid" / "dist" / "mermaid.min.js"
    if mermaid_js.is_file():
        shutil.copy(mermaid_js, out / "assets" / "mermaid.min.js")
        print("  mermaid 已复制")
    else:
        print("  ⚠ 未找到 mermaid")

    shutil.copy(Path(__file__).with_name("site_assets") / "style.css", out / "assets" / "style.css")
    shutil.copy(Path(__file__).with_name("site_assets") / "app.js", out / "assets" / "app.js")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"✓ 构建完成：{len(docs)} 页 → {out}")


if __name__ == "__main__":
    main()