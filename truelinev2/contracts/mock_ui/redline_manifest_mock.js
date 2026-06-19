/* TrueLine v2 — Redline Manifest contract mock UI (renderer).
 *
 * CONTRACT MOCK ONLY. This script is manifest-driven: every rendered value comes
 * from the redline manifest contract. It fetches the sibling committed example
 * (the documented local-preview way) and renders header, accountability cards,
 * filters, and the per-log list from that data alone.
 *
 * It deliberately consumes ONLY the manifest. It never reads the parent source
 * model, never reads stale model status fields, and never infers status from PNG
 * filenames or on-disk artifacts — those rules live in manifest.consumption_rules,
 * which this UI renders verbatim.
 *
 * Local preview (fetch is blocked on file://, so serve the folder):
 *     cd truelinev2/contracts && python -m http.server 8000
 *     open http://localhost:8000/mock_ui/redline_manifest_mock.html
 */
(function () {
  "use strict";

  // Single data source: the committed example manifest, fetched at runtime.
  var EXAMPLE_MANIFEST_PATH = "../examples/brenham_50_of_58_redline_manifest.example.json";

  var STATUS_META = {
    DRAWN_REDLINE: { label: "Drawn redline", klass: "k-drawn" },
    COVERED_BY_EXISTING_REDLINE: { label: "Covered", klass: "k-covered" },
    OWNER_LOCKED_ABSTAIN: { label: "Owner-locked abstain", klass: "k-owner" },
    SOURCE_GAP_BLOCKED: { label: "Source gap", klass: "k-source" },
    MISSING_SOURCE_SHEET_BLOCKED: { label: "Missing source sheet", klass: "k-missing" }
  };

  var PROVENANCE_LABEL = {
    DETERMINISTIC_AUTO: "Deterministic auto",
    OWNER_CONFIRMED_HUMAN_ADJUSTABLE: "Owner-confirmed · human-adjustable",
    COVERED_BY_EXISTING_REDLINE: "Covered by existing redline",
    BLOCKED_OWNER_LOCKED: "Blocked · owner-locked",
    BLOCKED_SOURCE_GAP: "Blocked · source gap",
    BLOCKED_MISSING_SOURCE: "Blocked · missing source"
  };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") node.className = attrs[k];
        else if (k === "html") node.innerHTML = attrs[k];
        else if (k === "text") node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function indicatorWord(log) {
    if (log.drawn) return "drawn";
    if (log.covered) return "covered";
    if (log.blocked) return "blocked";
    return "—";
  }

  // ---- Header -------------------------------------------------------------
  function renderHeader(m, sourceLabel, isFallback) {
    document.getElementById("projectName").textContent = m.project_name;

    var chiprow = document.getElementById("chiprow");
    chiprow.innerHTML = "";
    chiprow.appendChild(el("span", { class: "chip" + (isFallback ? " src-fallback" : "") }, [
      el("span", { class: "led" }), el("span", { text: sourceLabel })
    ]));
    chiprow.appendChild(el("span", { class: "chip" }, [
      el("span", { text: "render commit " }), el("b", { text: m.engine.render_commit })
    ]));
    chiprow.appendChild(el("span", { class: "chip" }, [
      el("span", { text: "branch " }), el("b", { text: m.engine.branch })
    ]));
    chiprow.appendChild(el("span", { class: "chip" }, [
      el("span", { text: "schema " }), el("b", { text: "v" + m.schema_version })
    ]));

    var s = m.summary;
    document.getElementById("frontierBig").innerHTML =
      '<span class="drawn">' + s.drawn_count + "</span>" +
      '<span class="of">/' + s.total_logs + "</span>";
    document.getElementById("frontierCap").textContent =
      s.frontier + " — redlines drawn of logs accounted (never shown as " +
      s.total_logs + "/" + s.total_logs + ")";
    var pct = Math.round((s.drawn_count / s.total_logs) * 100);
    document.getElementById("frontierBar").style.width = pct + "%";

    var tiles = document.getElementById("heroTiles");
    tiles.innerHTML = "";
    [["t-drawn", s.drawn_count, "drawn"],
     ["t-covered", s.covered_count, "covered"],
     ["t-blocked", s.blocked_count, "blocked"]].forEach(function (t) {
      tiles.appendChild(el("div", { class: "tile " + t[0] }, [
        el("div", { class: "num", text: String(t[1]) }),
        el("div", { class: "lbl", text: t[2] })
      ]));
    });
  }

  // ---- Accountability summary cards (also act as filters) -----------------
  function renderCards(m, applyFilter) {
    var sc = m.status_counts;
    var defs = [
      ["k-drawn", "Drawn", sc.DRAWN_REDLINE, "drawn"],
      ["k-covered", "Covered", sc.COVERED_BY_EXISTING_REDLINE, "covered"],
      ["k-owner", "Owner-locked", sc.OWNER_LOCKED_ABSTAIN, "status:OWNER_LOCKED_ABSTAIN"],
      ["k-source", "Source gap", sc.SOURCE_GAP_BLOCKED, "status:SOURCE_GAP_BLOCKED"],
      ["k-missing", "Missing source", sc.MISSING_SOURCE_SHEET_BLOCKED, "status:MISSING_SOURCE_SHEET_BLOCKED"]
    ];
    var host = document.getElementById("summaryCards");
    host.innerHTML = "";
    defs.forEach(function (d) {
      var card = el("button", { class: "card " + d[0], type: "button", "aria-pressed": "false", "data-filter": d[3] }, [
        el("div", { class: "c-num", text: String(d[2]) }),
        el("div", { class: "c-lbl", text: d[1] })
      ]);
      card.addEventListener("click", function () { applyFilter(d[3]); });
      host.appendChild(card);
    });
  }

  // ---- Per-log row --------------------------------------------------------
  function renderRow(log) {
    var meta = STATUS_META[log.status] || { label: log.status, klass: "" };
    var row = el("div", { class: "row " + meta.klass, "data-log": log.log_id });

    var isGeom = log.provenance === "OWNER_CONFIRMED_HUMAN_ADJUSTABLE";
    var top = el("div", { class: "row-top" }, [
      el("span", { class: "dot" }),
      el("span", { class: "logid", text: log.log_id }),
      el("span", { class: "pill", text: meta.label }),
      el("span", { class: "pill prov" + (isGeom ? " geom" : ""), text: PROVENANCE_LABEL[log.provenance] || log.provenance }),
      el("span", { class: "indic", text: indicatorWord(log) })
    ]);
    row.appendChild(top);

    // Meta line: span, source sheets, parent, drawn lane.
    var metaLine = el("div", { class: "meta" });
    metaLine.appendChild(el("span", {}, [
      el("span", { class: "m-k", text: "span" }),
      el("span", { class: "station", text: log.span.label })
    ]));
    var sheetWrap = el("span", { class: "sheets" });
    (log.source_sheets || []).forEach(function (n) {
      sheetWrap.appendChild(el("span", { class: "sheet", text: "s" + n }));
    });
    metaLine.appendChild(el("span", {}, [el("span", { class: "m-k", text: "sheets" }), sheetWrap]));
    metaLine.appendChild(el("span", {}, [
      el("span", { class: "m-k", text: "parent" }),
      el("span", { class: "station", text: log.parent_id })
    ]));
    if (log.drawn_lane) {
      metaLine.appendChild(el("span", {}, [
        el("span", { class: "m-k", text: "lane" }),
        el("span", { class: "station", text: log.drawn_lane })
      ]));
    }
    row.appendChild(metaLine);

    // log3 special: owner-confirmed GEOMETRY, human-adjustable — NOT deterministic auto.
    if (isGeom) {
      row.appendChild(el("div", { class: "note-line note-geom" }, [
        el("span", { class: "ic", text: "◈" }),
        el("span", { html: "<b>Owner-confirmed geometry</b> — human-adjustable lane, <b>not deterministic auto</b>." })
      ]));
    }

    // Coverage summary (covered-by, downstream coverage).
    if (log.coverage) {
      var cov = log.coverage;
      if (cov.covered_by) {
        row.appendChild(el("div", { class: "note-line note-cover" }, [
          el("span", { class: "ic", text: "↻" }),
          el("span", { html: "Covered by <b>" + cov.covered_by + "</b> — already on the plan, <b>no duplicate artifact</b> (not a missing redline)." })
        ]));
      }
      if (cov.downstream_covered_by && cov.downstream_covered_by.length) {
        row.appendChild(el("div", { class: "note-line note-cover" }, [
          el("span", { class: "ic", text: "→" }),
          el("span", { html: "Downstream covered by <b>" + cov.downstream_covered_by.join(", ") + "</b>." })
        ]));
      }
    }

    // Blocker + exact unlock requirement (the call-to-action).
    if (log.blocker) {
      row.appendChild(el("div", { class: "note-line note-block" }, [
        el("span", { class: "ic", text: "⚠" }),
        el("span", {}, [
          el("span", { html: "<b>Blocked:</b> " + log.blocker.name + " — " }),
          el("span", { class: "req", text: "Action needed: " + log.blocker.unlock_requirement })
        ])
      ]));
    }

    // Warnings — surfaced as advisories, never used as placement truth.
    (log.warnings || []).forEach(function (w) {
      row.appendChild(el("div", { class: "note-line note-warn" }, [
        el("span", {}, [
          el("span", { class: "tag", text: "warning — advisory, not placement truth" }),
          el("span", { text: w })
        ])
      ]));
    });

    // Artifacts — placeholders until a checksum is present.
    var arts = el("div", { class: "arts" });
    if (!log.artifacts || !log.artifacts.length) {
      arts.appendChild(el("span", { class: "arts-none", text: "no artifacts" }));
    } else {
      log.artifacts.forEach(function (a) {
        var hasChecksum = !!a.sha256;
        arts.appendChild(el("span", { class: "art" }, [
          el("span", { text: a.kind }),
          el("span", { text: a.path }),
          hasChecksum
            ? el("span", { class: "ck", text: "sha256 ✓" })
            : el("span", { class: "ph", text: "placeholder (no checksum)" })
        ]));
      });
    }
    row.appendChild(arts);

    return row;
  }

  // ---- Footer -------------------------------------------------------------
  function renderFooter(m, sourceLabel) {
    var f = document.getElementById("footer");
    f.innerHTML = "";
    f.appendChild(el("h3", { text: "Manifest disclaimer" }));
    f.appendChild(el("div", { class: "disclaimer", text: m.disclaimer }));

    f.appendChild(el("h3", { text: "Consumption rules (from the manifest)", style: "margin-top:22px" }));
    var ul = el("ul");
    (m.consumption_rules || []).forEach(function (r) { ul.appendChild(el("li", { text: r })); });
    f.appendChild(ul);

    f.appendChild(el("div", { class: "arts-label", text: "Artifact paths are placeholders unless checksum is present." }));
    f.appendChild(el("div", { style: "margin-top:10px;color:var(--muted-2);font-family:var(--mono);font-size:12px" }, [
      el("span", { text: "data source: " + sourceLabel + " · " + EXAMPLE_MANIFEST_PATH })
    ]));
  }

  // ---- Filtering ----------------------------------------------------------
  function matches(log, key) {
    if (key === "all") return true;
    if (key === "drawn") return !!log.drawn;
    if (key === "covered") return !!log.covered;
    if (key === "blocked") return !!log.blocked;
    if (key === "warnings") return (log.warnings || []).length > 0;
    if (key.indexOf("status:") === 0) return log.status === key.slice(7);
    return true;
  }

  function wire(m) {
    var logs = m.logs;
    var current = "all";

    function paint() {
      var list = document.getElementById("logList");
      list.innerHTML = "";
      var shown = 0;
      logs.forEach(function (log) {
        if (!matches(log, current)) return;
        var row = renderRow(log);
        row.style.animationDelay = (shown * 22) + "ms";
        list.appendChild(row);
        shown += 1;
      });
      document.getElementById("showingCount").textContent =
        "showing " + shown + " of " + logs.length;

      // Sync toolbar + card pressed states.
      Array.prototype.forEach.call(document.querySelectorAll(".fbtn"), function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-filter") === current ? "true" : "false");
      });
      Array.prototype.forEach.call(document.querySelectorAll(".card"), function (c) {
        c.setAttribute("aria-pressed", c.getAttribute("data-filter") === current ? "true" : "false");
      });
    }

    function applyFilter(key) { current = key; paint(); }

    renderHeader(m, m._sourceLabel, m._isFallback);
    renderCards(m, applyFilter);
    renderFooter(m, m._sourceLabel);

    Array.prototype.forEach.call(document.querySelectorAll(".fbtn"), function (b) {
      b.addEventListener("click", function () { applyFilter(b.getAttribute("data-filter")); });
    });

    paint();
    document.getElementById("loadState").hidden = true;
    document.getElementById("app").hidden = false;
  }

  function showFetchHelp(err) {
    var ls = document.getElementById("loadState");
    ls.innerHTML = "";
    ls.appendChild(el("h2", { text: "Serve this folder to preview" }));
    ls.appendChild(el("p", { text:
      "This is a contract mock that fetches the committed example manifest. Browsers block " +
      "fetch() on file://, so open it through a local static server:" }));
    ls.appendChild(el("pre", { text:
      "cd truelinev2/contracts\n" +
      "python -m http.server 8000\n" +
      "# then open:\n" +
      "http://localhost:8000/mock_ui/redline_manifest_mock.html" }));
    ls.appendChild(el("p", { class: "", text: "(" + (err && err.message ? err.message : err) + ")" }));
  }

  function start() {
    fetch(EXAMPLE_MANIFEST_PATH, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status + " for " + EXAMPLE_MANIFEST_PATH);
        return r.json();
      })
      .then(function (m) {
        m._sourceLabel = "example manifest (fetched)";
        m._isFallback = false;
        wire(m);
      })
      .catch(function (err) { showFetchHelp(err); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
