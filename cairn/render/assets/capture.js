/* Cairn Capture bundle v3 UI (§11.8) — offline, no build step */
(function (global) {
  "use strict";

  var SOURCE_COLORS = {
    "claude-code": "#c45c26",
    codex: "#1a6b4a",
    cursor: "#2d4a7a",
    hermes: "#5a3d7a",
  };

  function boot(data) {
    var events = data.events || [];
    var files = data.files || [];
    var graph = data.graph || { nodes: [], edges: [], width: 800, height: 600 };
    var turns = data.turns || [];
    var session = data.session || {};
    var listEl = document.getElementById("node-list");
    var detailEl = document.getElementById("node-detail");
    var summaryEl = document.getElementById("run-summary");
    var headerEl = document.getElementById("session-header");
    var tabsEl = document.getElementById("view-tabs");
    var activeView = "files";
    var selectedFile = files.length ? files[0].path_rel : null;
    var selectedTurnId = turns.length ? turns[0].turn_id : null;
    var selectedNodeId = graph.nodes && graph.nodes.length ? graph.nodes[0].id : null;
    var graphViewBox = null;

    function clear(el) {
      while (el.firstChild) el.removeChild(el.firstChild);
    }

    function el(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text != null) node.textContent = text;
      return node;
    }

    function shortHash(hash) {
      if (!hash || typeof hash !== "string") return "—";
      return hash.length > 12 ? hash.slice(0, 8) + "…" + hash.slice(-4) : hash;
    }

    function qualityLabel(q) {
      if (q === "exact") return "exact diff";
      if (q === "partial") return "partial snapshot";
      return "path only";
    }

    function qualityHint(q, source) {
      if (q === "exact") return "";
      return (
        "Batch ingest — install cairn live install for exact file snapshots (" +
        (source || "agent") +
        ")."
      );
    }

    function renderSessionHeader() {
      if (!headerEl) return;
      clear(headerEl);
      var row = el("div", "session-header-row");
      var badge = el("span", "source-badge", session.source || "capture");
      badge.style.background = SOURCE_COLORS[session.source] || "#444";
      row.appendChild(badge);
      var titleWrap = el("div", "session-title-wrap");
      titleWrap.appendChild(el("h2", "session-title", session.external_id || session.id || "Session"));
      var keyLine = el("p", "session-key", session.session_key || "");
      titleWrap.appendChild(keyLine);
      row.appendChild(titleWrap);
      headerEl.appendChild(row);

      var meta = el("dl", "session-meta kv");
      var pairs = [
        ["Run id", session.run_id || "—"],
        ["Status", session.status || "—"],
        ["Model", session.model || "—"],
        ["Branch", (session.git && session.git.branch) || "—"],
        ["Commit", (session.git && session.git.commit_short) || "—"],
        ["Started", session.started_at || "—"],
        ["Ended", session.ended_at || "—"],
        ["Events", String(session.event_count || events.length)],
      ];
      if (session.usage) {
        var u = session.usage;
        var tok =
          (u.input_tokens || 0) + " in / " + (u.output_tokens || 0) + " out";
        if (u.cost != null) tok += " · $" + Number(u.cost).toFixed(4);
        pairs.push(["Usage", tok]);
      }
      pairs.forEach(function (pair) {
        meta.appendChild(el("dt", null, pair[0]));
        meta.appendChild(el("dd", null, pair[1]));
      });
      headerEl.appendChild(meta);
    }

    function formatSummaryLine() {
      return [
        session.source,
        session.external_id || session.id,
        session.started_at || "",
        (session.event_count || events.length) + " events",
      ]
        .filter(Boolean)
        .join(" · ");
    }

    function relatedEventsForFile(pathRel) {
      var out = [];
      events.forEach(function (ev) {
        if (ev.type === "file_snapshot" && ev.path_rel === pathRel) out.push(ev);
        if (ev.type === "tool_call" && ev.args_inline) {
          var args = ev.args_inline;
          var p = args.path || args.file_path || args.target_file;
          if (p && String(p).indexOf(pathRel) >= 0) out.push(ev);
        }
      });
      return out;
    }

    function navigateHash() {
      var h = (location.hash || "").replace(/^#/, "");
      if (!h) return;
      var parts = h.split("/");
      var kind = parts[0];
      if (kind === "turn" && parts[1]) {
        activeView = "timeline";
        selectedTurnId = parseInt(parts[1], 10);
        updateTabs();
        return;
      }
      if (kind === "file" && parts[1]) {
        activeView = "files";
        selectedFile = decodeURIComponent(parts.slice(1).join("/"));
        updateTabs();
        return;
      }
      if (kind === "event" && parts[1]) {
        activeView = "timeline";
        var seq = parseInt(parts[1], 10);
        turns.forEach(function (t) {
          if (seq >= t.seq_start && seq <= t.seq_end) selectedTurnId = t.turn_id;
        });
        updateTabs();
        return;
      }
      if (kind === "graph") {
        activeView = "graph";
        if (parts[1]) selectedNodeId = parts[1];
        updateTabs();
        return;
      }
    }

    function setHash(kind, value) {
      if (kind === "file") location.hash = "file/" + encodeURIComponent(value);
      else location.hash = kind + "/" + value;
    }

    function renderFilesSidebar() {
      clear(listEl);
      if (!files.length) {
        listEl.appendChild(el("p", "empty-note", "No file artifacts in this session."));
        return;
      }
      files.forEach(function (file) {
        var btn = el("button", "node-btn" + (file.path_rel === selectedFile ? " active" : ""));
        btn.type = "button";
        btn.appendChild(el("span", "id", file.path_rel));
        var meta = el("span", "meta");
        meta.appendChild(el("span", "quality-badge quality-" + (file.snapshot_quality || "inferred"), qualityLabel(file.snapshot_quality)));
        meta.appendChild(document.createTextNode(" · " + (file.change_type || "edit")));
        btn.appendChild(meta);
        btn.addEventListener("click", function () {
          selectedFile = file.path_rel;
          setHash("file", file.path_rel);
          renderFilesSidebar();
          renderFilesDetail();
        });
        listEl.appendChild(btn);
      });
    }

    function renderFilesDetail() {
      clear(detailEl);
      if (!selectedFile) {
        detailEl.appendChild(document.createTextNode("Select a file."));
        return;
      }
      var file = null;
      files.forEach(function (f) {
        if (f.path_rel === selectedFile) file = f;
      });
      if (!file) return;

      detailEl.appendChild(el("h2", null, file.path_rel));
      var badge = el("span", "quality-badge quality-" + (file.snapshot_quality || "inferred"), qualityLabel(file.snapshot_quality));
      detailEl.appendChild(badge);
      var hint = qualityHint(file.snapshot_quality, session.source);
      if (hint) detailEl.appendChild(el("p", "hint-note", hint));

      var dl = el("dl", "kv");
      [
        ["Change", file.change_type || "edit"],
        ["Before", shortHash(file.before_hash)],
        ["After", shortHash(file.after_hash)],
        ["Event seqs", (file.event_seqs || []).join(", ")],
      ].forEach(function (pair) {
        dl.appendChild(el("dt", null, pair[0]));
        dl.appendChild(el("dd", null, pair[1]));
      });
      detailEl.appendChild(dl);

      if (file.diff_preview) {
        detailEl.appendChild(el("h3", null, "Diff"));
        var pre = el("pre", "code diff-preview", file.diff_preview);
        detailEl.appendChild(pre);
      } else if (file.diff_preview === null && file.snapshot_quality === "inferred" && file.inferred) {
        detailEl.appendChild(el("p", "hint-note", file.inferred));
      } else if (typeof file.diff_preview === "string" || (file.snapshot_quality === "inferred")) {
        var ex = file.diff_preview || _inferredFromEvents(file);
        if (ex) {
          detailEl.appendChild(el("h3", null, "Tool activity"));
          detailEl.appendChild(el("pre", "code", ex));
        }
      }

      detailEl.appendChild(el("h3", null, "Related events"));
      var ul = el("ul", "inputs-list");
      relatedEventsForFile(file.path_rel).forEach(function (ev) {
        var li = el("li");
        var link = el("a", null, "#" + ev.seq + " " + ev.type + (ev.name ? " (" + ev.name + ")" : ""));
        link.href = "#event/" + ev.seq;
        link.addEventListener("click", function (e) {
          e.preventDefault();
          setHash("event", ev.seq);
          navigateHash();
        });
        li.appendChild(link);
        ul.appendChild(li);
      });
      detailEl.appendChild(ul);
    }

    function _inferredFromEvents(file) {
      var rel = relatedEventsForFile(file.path_rel);
      if (!rel.length) return null;
      return rel
        .map(function (ev) {
          return "#" + ev.seq + " " + ev.type + (ev.name ? " (" + ev.name + ")" : "");
        })
        .join("\n");
    }

    function renderTimelineSidebar() {
      clear(listEl);
      if (!turns.length) {
        listEl.appendChild(el("p", "empty-note", "No turns in this session."));
        return;
      }
      turns.forEach(function (turn) {
        var btn = el("button", "node-btn" + (turn.turn_id === selectedTurnId ? " active" : ""));
        btn.type = "button";
        btn.appendChild(el("span", "id", "Turn " + turn.turn_id));
        var preview = (turn.user_text || "").slice(0, 72);
        if ((turn.user_text || "").length > 72) preview += "…";
        var meta = el("span", "meta", preview);
        btn.appendChild(meta);
        btn.addEventListener("click", function () {
          selectedTurnId = turn.turn_id;
          setHash("turn", turn.turn_id);
          renderTimelineSidebar();
          renderTimelineDetail();
        });
        listEl.appendChild(btn);
      });
    }

    function renderToolChip(toolEvent) {
      var chip = el("span", "tool-chip tool-" + (toolEvent.name || toolEvent.type), toolEvent.name || toolEvent.type);
      if (toolEvent.type === "tool_call" && toolEvent.seq) {
        chip.title = "seq " + toolEvent.seq;
      }
      return chip;
    }

    function renderTimelineDetail() {
      clear(detailEl);
      var turn = null;
      turns.forEach(function (t) {
        if (t.turn_id === selectedTurnId) turn = t;
      });
      if (!turn) {
        detailEl.appendChild(document.createTextNode("Select a turn."));
        return;
      }

      detailEl.appendChild(el("h2", null, "Turn " + turn.turn_id));
      detailEl.appendChild(el("p", "turn-range", "Events #" + turn.seq_start + "–#" + turn.seq_end));

      detailEl.appendChild(el("h3", null, "User"));
      var userPre = el("div", "prose user-prompt", turn.user_text || "(empty prompt)");
      detailEl.appendChild(userPre);

      if (turn.assistant_summary) {
        detailEl.appendChild(el("h3", null, "Assistant"));
        detailEl.appendChild(el("div", "prose", turn.assistant_summary));
      }

      if (turn.tool_count > 0) {
        detailEl.appendChild(el("h3", null, "Tools"));
        var chips = el("div", "tool-chips");
        (turn.events || []).forEach(function (ev) {
          if (ev.type === "tool_call") chips.appendChild(renderToolChip(ev));
        });
        detailEl.appendChild(chips);
      }

      if (turn.files_touched && turn.files_touched.length) {
        detailEl.appendChild(el("h3", null, "Files touched"));
        var ful = el("ul", "file-chips");
        turn.files_touched.forEach(function (path) {
          var li = el("li");
          var a = el("a", null, path);
          a.href = "#file/" + encodeURIComponent(path);
          a.addEventListener("click", function (e) {
            e.preventDefault();
            setHash("file", path);
            navigateHash();
          });
          li.appendChild(a);
          ful.appendChild(li);
        });
        detailEl.appendChild(ful);
      }

      var devToggle = el("button", "dev-toggle", "Show event JSON");
      var devPre = el("pre", "code dev-panel hidden");
      devPre.textContent = JSON.stringify(turn.events, null, 2);
      devToggle.addEventListener("click", function () {
        devPre.classList.toggle("hidden");
        devToggle.textContent = devPre.classList.contains("hidden") ? "Show event JSON" : "Hide event JSON";
      });
      detailEl.appendChild(devToggle);
      detailEl.appendChild(devPre);
    }

    function renderGraphSidebar() {
      clear(listEl);
      var nodes = graph.nodes || [];
      if (!nodes.length) {
        listEl.appendChild(el("p", "empty-note", "No graph nodes."));
        return;
      }
      if (graph.mode === "turns") {
        var hint = el(
          "p",
          "hint-note",
          "Showing " + (graph.turn_count || nodes.length) + " turns (" + (graph.event_count || events.length) + " events collapsed)."
        );
        listEl.appendChild(hint);
      }
      nodes.forEach(function (n) {
        var btn = el("button", "node-btn" + (n.id === selectedNodeId ? " active" : ""));
        btn.type = "button";
        var label = n.type === "turn" ? "Turn " + (n.turn_id || n.id) : n.id;
        btn.appendChild(el("span", "id", label));
        var metaText =
          n.type === "turn"
            ? (n.tool_count || 0) + " tools · " + (n.label || "").slice(0, 36)
            : n.type + " · " + (n.label || "").slice(0, 40);
        btn.appendChild(el("span", "meta", metaText));
        btn.addEventListener("click", function () {
          selectedNodeId = n.id;
          setHash("graph", n.id);
          renderGraphSidebar();
          selectGraphNode(n.id, false);
        });
        listEl.appendChild(btn);
      });
    }

    function nodeWidth(n) {
      return n.type === "turn" ? 300 : 160;
    }

    function nodeHeight(n) {
      return n.type === "turn" ? 72 : 40;
    }

    function graphNodeBounds(nodeSubset) {
      var minX = Infinity;
      var minY = Infinity;
      var maxX = -Infinity;
      var maxY = -Infinity;
      nodeSubset.forEach(function (n) {
        if (n.x == null || n.y == null) return;
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x + nodeWidth(n));
        maxY = Math.max(maxY, n.y + nodeHeight(n));
      });
      if (!isFinite(minX)) {
        return { x: 0, y: 0, w: graph.width || 800, h: graph.height || 520 };
      }
      var pad = 32;
      return {
        x: minX - pad,
        y: minY - pad,
        w: maxX - minX + pad * 2,
        h: maxY - minY + pad * 2,
      };
    }

    var graphSvgRef = null;
    var graphLayerRef = null;

    function applyGraphViewBox(box) {
      graphViewBox = box;
      if (graphSvgRef) {
        graphSvgRef.setAttribute("viewBox", box.x + " " + box.y + " " + box.w + " " + box.h);
      }
    }

    function selectGraphNode(nodeId, zoomToNode) {
      var nodeMap = {};
      (graph.nodes || []).forEach(function (n) {
        nodeMap[n.id] = n;
      });
      var node = nodeMap[nodeId];
      if (!node) return;
      highlightGraphNode(nodeId);
      if (node.type === "turn") {
        renderTurnGraphDetail(node);
      } else {
        renderGraphNodeDetail(node);
      }
      if (zoomToNode) {
        applyGraphViewBox(graphNodeBounds([node]));
      }
    }

    function fitGraphView(nodeSubset) {
      applyGraphViewBox(graphNodeBounds(nodeSubset || graph.nodes || []));
    }

    function edgeColor(kind) {
      if (kind === "causal") return "#3d6eb5";
      if (kind === "data") return "#3a7d44";
      if (kind === "delegation") return "#7a4db8";
      return "#999";
    }

    function renderTurnGraphDetail(node) {
      var existing = document.querySelector(".graph-node-detail");
      if (existing) existing.remove();
      var turn = null;
      turns.forEach(function (t) {
        if ("t" + t.turn_id === node.id || t.turn_id === node.turn_id) turn = t;
      });
      var panel = el("div", "graph-node-detail");
      panel.appendChild(el("h3", null, "Turn " + (node.turn_id || node.id)));
      if (turn) {
        panel.appendChild(el("div", "prose user-prompt", turn.user_text || ""));
        if (turn.assistant_summary) {
          panel.appendChild(el("h4", null, "Assistant"));
          panel.appendChild(el("div", "prose", turn.assistant_summary));
        }
        var link = el("a", null, "Open full turn in Timeline");
        link.href = "#turn/" + (turn.turn_id || node.turn_id);
        link.addEventListener("click", function (e) {
          e.preventDefault();
          setHash("turn", turn.turn_id);
          navigateHash();
        });
        panel.appendChild(link);
      }
      detailEl.appendChild(panel);
    }

    function renderGraphCanvas() {
      clear(detailEl);
      graphSvgRef = null;
      graphLayerRef = null;
      var wrap = el("div", "graph-wrap");
      var toolbar = el("div", "graph-toolbar");
      var fitBtn = el("button", "graph-btn", "Fit all");
      var zoomIn = el("button", "graph-btn", "+");
      var zoomOut = el("button", "graph-btn", "−");
      toolbar.appendChild(fitBtn);
      toolbar.appendChild(zoomIn);
      toolbar.appendChild(zoomOut);
      if (graph.mode === "turns") {
        toolbar.appendChild(
          el(
            "span",
            "graph-mode-note",
            (graph.turn_count || 0) + " turns · " + events.length + " events"
          )
        );
      }
      wrap.appendChild(toolbar);

      var svgNs = "http://www.w3.org/2000/svg";
      var svg = document.createElementNS(svgNs, "svg");
      svg.setAttribute("class", "graph-svg");
      svg.setAttribute("width", "100%");
      svg.setAttribute("height", "520");
      svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
      graphSvgRef = svg;

      var g = document.createElementNS(svgNs, "g");
      g.setAttribute("class", "graph-layer");
      graphLayerRef = g;
      svg.appendChild(g);

      var nodeMap = {};
      (graph.nodes || []).forEach(function (n) {
        nodeMap[n.id] = n;
      });

      (graph.edges || []).forEach(function (edge) {
        var from = nodeMap[edge.from];
        var to = nodeMap[edge.to];
        if (!from || !to) return;
        var line = document.createElementNS(svgNs, "line");
        var x1 = from.x + nodeWidth(from) / 2;
        var x2 = to.x + nodeWidth(to) / 2;
        var y1 = from.y + nodeHeight(from) / 2;
        var y2 = to.y + nodeHeight(to) / 2;
        if (graph.mode === "turns" && edge.kind === "temporal" && to.y > from.y) {
          y1 = from.y + nodeHeight(from);
          y2 = to.y;
        }
        line.setAttribute("x1", x1);
        line.setAttribute("y1", y1);
        line.setAttribute("x2", x2);
        line.setAttribute("y2", y2);
        line.setAttribute("stroke", edgeColor(edge.kind));
        line.setAttribute("stroke-width", edge.kind === "temporal" ? "1" : "2");
        line.setAttribute("stroke-dasharray", edge.kind === "temporal" ? "4 3" : "");
        line.setAttribute("data-kind", edge.kind);
        g.appendChild(line);
      });

      (graph.nodes || []).forEach(function (n) {
        var group = document.createElementNS(svgNs, "g");
        group.setAttribute("class", "graph-node");
        group.setAttribute("data-id", n.id);
        group.setAttribute("transform", "translate(" + n.x + "," + n.y + ")");

        var w = nodeWidth(n);
        var h = nodeHeight(n);
        var rect = document.createElementNS(svgNs, "rect");
        rect.setAttribute("width", String(w));
        rect.setAttribute("height", String(h));
        rect.setAttribute("rx", "6");
        rect.setAttribute("fill", n.type === "turn" ? "#f0ebe3" : "#ffffff");
        rect.setAttribute("stroke", "#d8d2c8");
        rect.setAttribute("stroke-width", "1.5");
        rect.setAttribute("class", "node-rect node-type-" + n.type);
        group.appendChild(rect);

        var titleText = n.type === "turn" ? n.title || "Turn " + n.turn_id : n.type;
        var title = document.createElementNS(svgNs, "text");
        title.setAttribute("x", "10");
        title.setAttribute("y", "22");
        title.setAttribute("class", "node-label-type");
        title.textContent = titleText;
        group.appendChild(title);

        var label = document.createElementNS(svgNs, "text");
        label.setAttribute("x", "10");
        label.setAttribute("y", "42");
        label.setAttribute("class", "node-label");
        var labelText = n.type === "turn" ? n.label || "" : n.label || n.id;
        if (n.type === "turn" && n.tool_count) {
          labelText = (n.tool_count + " tools · ") + labelText;
        }
        label.textContent = labelText.slice(0, 42);
        group.appendChild(label);

        if (n.type === "turn") {
          var sub = document.createElementNS(svgNs, "text");
          sub.setAttribute("x", "10");
          sub.setAttribute("y", "60");
          sub.setAttribute("class", "node-sublabel");
          sub.textContent = labelText.length > 42 ? labelText.slice(42, 84) : "";
          group.appendChild(sub);
        }

        group.addEventListener("click", function () {
          selectedNodeId = n.id;
          setHash("graph", n.id);
          renderGraphSidebar();
          selectGraphNode(n.id, false);
        });
        g.appendChild(group);
      });

      wrap.appendChild(svg);
      detailEl.appendChild(wrap);

      fitBtn.addEventListener("click", function () {
        fitGraphView(graph.nodes || []);
      });
      zoomIn.addEventListener("click", function () {
        if (!graphViewBox) return;
        var cx = graphViewBox.x + graphViewBox.w / 2;
        var cy = graphViewBox.y + graphViewBox.h / 2;
        graphViewBox.w *= 0.8;
        graphViewBox.h *= 0.8;
        graphViewBox.x = cx - graphViewBox.w / 2;
        graphViewBox.y = cy - graphViewBox.h / 2;
        applyGraphViewBox(graphViewBox);
      });
      zoomOut.addEventListener("click", function () {
        if (!graphViewBox) return;
        var cx = graphViewBox.x + graphViewBox.w / 2;
        var cy = graphViewBox.y + graphViewBox.h / 2;
        graphViewBox.w *= 1.25;
        graphViewBox.h *= 1.25;
        graphViewBox.x = cx - graphViewBox.w / 2;
        graphViewBox.y = cy - graphViewBox.h / 2;
        applyGraphViewBox(graphViewBox);
      });

      var dragging = false;
      var last = { x: 0, y: 0 };
      svg.addEventListener("mousedown", function (e) {
        dragging = true;
        last = { x: e.clientX, y: e.clientY };
      });
      window.addEventListener("mouseup", function () {
        dragging = false;
      });
      svg.addEventListener("mousemove", function (e) {
        if (!dragging || !graphViewBox) return;
        var rect = svg.getBoundingClientRect();
        var dx = ((e.clientX - last.x) / rect.width) * graphViewBox.w;
        var dy = ((e.clientY - last.y) / rect.height) * graphViewBox.h;
        graphViewBox.x -= dx;
        graphViewBox.y -= dy;
        last = { x: e.clientX, y: e.clientY };
        applyGraphViewBox(graphViewBox);
      });

      fitGraphView(graph.nodes || []);
      if (selectedNodeId && nodeMap[selectedNodeId]) {
        selectGraphNode(selectedNodeId, false);
      }
    }

    function highlightGraphNode(nodeId) {
      document.querySelectorAll(".graph-node").forEach(function (g) {
        g.classList.toggle("selected", g.getAttribute("data-id") === nodeId);
      });
    }

    function renderGraphNodeDetail(node) {
      var existing = document.querySelector(".graph-node-detail");
      if (existing) existing.remove();
      var panel = el("div", "graph-node-detail");
      panel.appendChild(el("h3", null, node.id + " · " + node.type));
      panel.appendChild(el("p", "prose", node.label || ""));
      var edges = (graph.edges || []).filter(function (e) {
        return e.from === node.id || e.to === node.id;
      });
      if (edges.length) {
        panel.appendChild(el("h4", null, "Edges"));
        var ul = el("ul", "inputs-list");
        edges.forEach(function (e) {
          ul.appendChild(el("li", null, e.kind + ": " + e.from + " → " + e.to));
        });
        panel.appendChild(ul);
      }
      var seq = node.seq;
      if (seq) {
        var link = el("a", null, "Open in Timeline");
        link.href = "#event/" + seq;
        link.addEventListener("click", function (e) {
          e.preventDefault();
          setHash("event", seq);
          navigateHash();
        });
        panel.appendChild(link);
      }
      detailEl.appendChild(panel);
    }

    function updateTabs() {
      if (tabsEl) {
        tabsEl.querySelectorAll(".tab-btn").forEach(function (btn) {
          btn.classList.toggle("active", btn.getAttribute("data-view") === activeView);
        });
      }
      if (activeView === "files") {
        renderFilesSidebar();
        renderFilesDetail();
      } else if (activeView === "timeline") {
        renderTimelineSidebar();
        renderTimelineDetail();
      } else {
        renderGraphSidebar();
        renderGraphCanvas();
      }
    }

    if (tabsEl) {
      tabsEl.querySelectorAll(".tab-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          activeView = btn.getAttribute("data-view") || "files";
          updateTabs();
        });
      });
    }

    renderSessionHeader();
    if (summaryEl) summaryEl.textContent = formatSummaryLine();
    window.addEventListener("hashchange", navigateHash);
    navigateHash();
    updateTabs();
  }

  global.CairnCapture = { boot: boot, version: 3 };
})(typeof window !== "undefined" ? window : globalThis);
