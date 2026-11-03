/* 焊接传热学知识库 · 站点交互：主题 / 搜索 / KaTeX / mermaid / 目录 */
(function () {
  var ROOT = (window.__ROOT__ === undefined ? "" : window.__ROOT__);
  var doc = document.documentElement;

  /* ---------------- 主题 ---------------- */
  try {
    var saved = localStorage.getItem("wht-theme");
    if (saved) doc.setAttribute("data-theme", saved);
  } catch (e) {}
  var themeBtn = document.getElementById("themeBtn");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = doc.getAttribute("data-theme") === "dark" ? "light" : "dark";
      doc.setAttribute("data-theme", next);
      try { localStorage.setItem("wht-theme", next); } catch (e) {}
      if (next === "light") {
        document.querySelectorAll(".mermaid[data-processed]").forEach(function (n) {
          n.removeAttribute("data-processed");
        });
        if (window.mermaid) window.mermaid.run({ querySelector: ".mermaid" });
      }
    });
  }

  /* ---------------- 移动端目录 ---------------- */
  var menuBtn = document.getElementById("menuBtn");
  var sidebar = document.getElementById("sidebar");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", function () { sidebar.classList.toggle("open"); });
    sidebar.addEventListener("click", function (e) {
      if (e.target.tagName === "A") sidebar.classList.remove("open");
    });
  }

  /* ---------------- 当前页高亮 ---------------- */
  (function () {
    var here = decodeURI(location.pathname.split("/").pop() || "");
    document.querySelectorAll(".side-link").forEach(function (a) {
      var href = decodeURI(a.getAttribute("href") || "");
      if (href && here && href.split("/").pop() === here) a.classList.add("active");
    });
  })();

  /* ---------------- KaTeX ---------------- */
  function renderMath() {
    if (!window.renderMathInElement) return;
    try {
      window.renderMathInElement(document.querySelector(".content, .hero") || document.body, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false }
        ],
        throwOnError: false,
        strict: false,
        trust: true,
        macros: { "\\dd": "\\mathrm{d}", "\\e": "\\mathrm{e}" }
      });
    } catch (e) { console.warn("katex", e); }
  }
  function boot() {
    renderMath();
    if (window.mermaid) {
      try {
        window.mermaid.initialize({
          startOnLoad: false,
          theme: doc.getAttribute("data-theme") === "light" ? "default" : "dark",
          flowchart: { htmlLabels: true, curve: "basis" },
          securityLevel: "loose"
        });
        window.mermaid.run({ querySelector: ".mermaid" });
      } catch (e) { console.warn("mermaid", e); }
    }
  }
  if (document.readyState === "complete") boot();
  else window.addEventListener("load", boot);

  /* ---------------- 搜索 ---------------- */
  var input = document.getElementById("searchInput");
  var box = document.getElementById("searchResults");
  if (!input || !box) return;
  var data = null, loading = false, active = -1, results = [];

  function load(cb) {
    if (data) return cb();
    if (loading) return setTimeout(function () { load(cb); }, 120);
    loading = true;
    fetch(ROOT + "assets/search.json")
      .then(function (r) { return r.json(); })
      .then(function (j) { data = j; loading = false; cb(); })
      .catch(function () { loading = false; data = []; cb(); });
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function search(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    var terms = q.split(/\s+/);
    var hits = [];
    for (var i = 0; i < data.length; i++) {
      var d = data[i];
      var title = d.t.toLowerCase(), body = d.x.toLowerCase(), dir = (d.d || "").toLowerCase();
      var score = 0, ok = true;
      for (var k = 0; k < terms.length; k++) {
        var t = terms[k];
        if (title.indexOf(t) >= 0) score += 12;
        else if (dir.indexOf(t) >= 0) score += 4;
        else if (body.indexOf(t) >= 0) score += 2;
        else { ok = false; break; }
      }
      if (!ok) continue;
      if (title === q) score += 40;
      if (title.indexOf(q) === 0) score += 12;
      hits.push({ d: d, s: score });
    }
    hits.sort(function (a, b) { return b.s - a.s; });
    return hits.slice(0, 24);
  }

  function render(list) {
    active = -1;
    results = list;
    if (!list.length) {
      box.innerHTML = '<div class="empty">没有匹配的笔记</div>';
      box.classList.add("open");
      return;
    }
    box.innerHTML = list.map(function (h, i) {
      return '<a href="' + ROOT + h.d.u + '" data-i="' + i + '">' +
        esc(h.d.t) + '<span class="s-dir">' + esc(h.d.d || "") + "</span></a>";
    }).join("");
    box.classList.add("open");
  }

  var timer = null;
  input.addEventListener("input", function () {
    var q = input.value;
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (!q.trim()) { box.classList.remove("open"); return; }
      load(function () { render(search(q)); });
    }, 70);
  });
  input.addEventListener("focus", function () { if (input.value.trim()) load(function () { render(search(input.value)); }); });

  input.addEventListener("keydown", function (e) {
    if (!box.classList.contains("open")) return;
    var links = box.querySelectorAll("a");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active += e.key === "ArrowDown" ? 1 : -1;
      if (active < 0) active = links.length - 1;
      if (active >= links.length) active = 0;
      links.forEach(function (a, i) { a.classList.toggle("active", i === active); });
      if (links[active]) links[active].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      var go = links[active] || links[0];
      if (go) location.href = go.getAttribute("href");
    } else if (e.key === "Escape") {
      box.classList.remove("open");
    }
  });

  document.addEventListener("click", function (e) {
    if (!box.contains(e.target) && e.target !== input) box.classList.remove("open");
  });

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      input.focus();
      input.select();
    }
  });
})();