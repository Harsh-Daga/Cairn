(function () {
  "use strict";

  var global = typeof window !== "undefined" ? window : globalThis;

  var SPLIT_FILE_MESSAGE =
    "This is a --split bundle. Browsers block loading external data from file://. " +
    "Serve this folder over HTTP (e.g. run: python -m http.server in this directory) " +
    "or re-render without --split for a self-contained index.html.";

  function showFatal(message) {
    var err = document.createElement("p");
    err.className = "truncate-note";
    err.textContent = message;
    document.body.replaceChildren(err);
  }

  function loadSplitPayload(dataPath) {
  return fetch(dataPath)
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status);
        }
        return resp.json();
      });
  }

  function bootstrapCapture(data) {
    var events = data.events || [];
    var files = data.files || [];
    var graph = data.graph || { nodes: [], edges: [] };
    var session = data.session || {};
    var listEl = document.getElementById("node-list");
    var detailEl = document.getElementById("node-detail");
    var summaryEl = document.getElementById("run-summary");
    var tabsEl = document.getElementById("view-tabs");
    var activeView = "files";
    var selectedFile = files.length ? files[0].path_rel : null;
    var selectedSeq = events.length ? events[0].seq : null;

    function clear(el) {
      while (el.firstChild) el.removeChild(el.firstChild);
    }

    function eventBySeq(seq) {
      for (var i = 0; i < events.length; i++) {
        if (events[i].seq === seq) return events[i];
      }
      return null;
    }

    function relatedEventsForFile(pathRel) {
      var out = [];
      events.forEach(function (ev) {
        if (ev.type === "file_snapshot" && ev.path_rel === pathRel) {
          out.push(ev);
        }
        if (ev.type === "tool_call" && ev.args_inline) {
          var args = ev.args_inline;
          var p = args.path || args.file_path || args.target_file;
          if (p && String(p).indexOf(pathRel) >= 0) out.push(ev);
        }
      });
      return out;
    }

    function formatSessionSummary() {
      var parts = [
        session.source || "capture",
        session.id || "",
        session.started_at || "",
      ];
      if (session.usage) {
        parts.push(
          String(session.usage.input_tokens || 0) +
            " in / " +
            String(session.usage.output_tokens || 0) +
            " out"
        );
      }
      return parts.filter(Boolean).join(" · ");
    }

    summaryEl.textContent = formatSessionSummary();

    function renderFilesSidebar() {
      clear(listEl);
      if (!files.length) {
        var empty = document.createElement("p");
        empty.className = "empty-note";
        empty.textContent = "No file artifacts in this session.";
        listEl.appendChild(empty);
        return;
      }
      files.forEach(function (file) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "node-btn" + (file.path_rel === selectedFile ? " active" : "");
        btn.setAttribute("data-file", file.path_rel);
        var idSpan = document.createElement("span");
        idSpan.className = "id";
        idSpan.textContent = file.path_rel;
        btn.appendChild(idSpan);
        var meta = document.createElement("span");
        meta.className = "meta";
        var hashes = [];
        if (file.before_hash) hashes.push("before");
        if (file.after_hash) hashes.push("after");
        meta.textContent = hashes.join(" / ") || "path only";
        btn.appendChild(meta);
        btn.addEventListener("click", function () {
          selectedFile = file.path_rel;
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

      var h2 = document.createElement("h2");
      h2.textContent = file.path_rel;
      detailEl.appendChild(h2);

      var dl = document.createElement("dl");
      dl.className = "kv";
      [
        ["Before hash", file.before_hash || "—"],
        ["After hash", file.after_hash || "—"],
        ["Event seqs", (file.event_seqs || []).join(", ")],
      ].forEach(function (pair) {
        var dt = document.createElement("dt");
        dt.textContent = pair[0];
        var dd = document.createElement("dd");
        dd.textContent = pair[1];
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      detailEl.appendChild(dl);

      var h3 = document.createElement("h3");
      h3.textContent = "Related events";
      detailEl.appendChild(h3);
      var ul = document.createElement("ul");
      ul.className = "inputs-list";
      relatedEventsForFile(file.path_rel).forEach(function (ev) {
        var li = document.createElement("li");
        var link = document.createElement("a");
        link.href = "#";
        link.textContent = "#" + ev.seq + " " + ev.type + (ev.name ? " (" + ev.name + ")" : "");
        link.addEventListener("click", function (e) {
          e.preventDefault();
          activeView = "timeline";
          selectedSeq = ev.seq;
          updateTabs();
          renderTimeline();
        });
        li.appendChild(link);
        ul.appendChild(li);
      });
      detailEl.appendChild(ul);
    }

    function renderTimeline() {
      clear(listEl);
      events.forEach(function (ev) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "node-btn" + (ev.seq === selectedSeq ? " active" : "");
        var idSpan = document.createElement("span");
        idSpan.className = "id";
        idSpan.textContent = "#" + ev.seq + " " + ev.type;
        btn.appendChild(idSpan);
        var meta = document.createElement("span");
        meta.className = "meta";
        if (ev.type === "user_prompt" && ev.text_inline) {
          meta.textContent = ev.text_inline.slice(0, 60);
        } else if (ev.name) {
          meta.textContent = ev.name;
        } else if (ev.path_rel) {
          meta.textContent = ev.path_rel;
        } else {
          meta.textContent = "";
        }
        btn.appendChild(meta);
        btn.addEventListener("click", function () {
          selectedSeq = ev.seq;
          renderTimeline();
          renderTimelineDetail();
        });
        listEl.appendChild(btn);
      });
      renderTimelineDetail();
    }

    function renderTimelineDetail() {
      clear(detailEl);
      var ev = eventBySeq(selectedSeq);
      if (!ev) {
        detailEl.appendChild(document.createTextNode("Select an event."));
        return;
      }
      var h2 = document.createElement("h2");
      h2.textContent = "#" + ev.seq + " " + ev.type;
      detailEl.appendChild(h2);
      var pre = document.createElement("pre");
      pre.className = "code";
      pre.textContent = JSON.stringify(ev, null, 2);
      detailEl.appendChild(pre);
    }

    function renderGraph() {
      clear(listEl);
      var nodes = graph.nodes || [];
      var nodeMap = {};
      nodes.forEach(function (n) {
        nodeMap[n.id] = n;
      });
      nodes.forEach(function (n) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "node-btn";
        btn.setAttribute("data-node", n.id);
        var idSpan = document.createElement("span");
        idSpan.className = "id";
        idSpan.textContent = n.id;
        btn.appendChild(idSpan);
        var meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = n.type + " · " + n.label;
        btn.appendChild(meta);
        btn.addEventListener("click", function () {
          renderGraphDetail(n, graph.edges || []);
        });
        listEl.appendChild(btn);
      });
      if (nodes.length) {
        renderGraphDetail(nodes[0], graph.edges || []);
      } else {
        clear(detailEl);
        detailEl.appendChild(document.createTextNode("No graph nodes."));
      }
    }

    function renderGraphDetail(node, edges) {
      clear(detailEl);
      var h2 = document.createElement("h2");
      h2.textContent = node.label || node.id;
      detailEl.appendChild(h2);
      var h3 = document.createElement("h3");
      h3.textContent = "Edges";
      detailEl.appendChild(h3);
      var ul = document.createElement("ul");
      ul.className = "inputs-list";
      edges.forEach(function (edge) {
        if (edge.from !== node.id && edge.to !== node.id) return;
        var li = document.createElement("li");
        li.textContent = edge.kind + ": " + edge.from + " → " + edge.to;
        ul.appendChild(li);
      });
      detailEl.appendChild(ul);
    }

    function updateTabs() {
      if (!tabsEl) return;
      tabsEl.querySelectorAll(".tab-btn").forEach(function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-view") === activeView);
      });
      if (activeView === "files") {
        renderFilesSidebar();
        renderFilesDetail();
      } else if (activeView === "timeline") {
        renderTimeline();
      } else {
        renderGraph();
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

    updateTabs();
  }

  function bootstrap(data) {
    var nodes = data.nodes || [];
    var nodesById = {};
    nodes.forEach(function (n) {
      nodesById[n.node_id] = n;
    });

    var listEl = document.getElementById("node-list");
    var detailEl = document.getElementById("node-detail");
    var summaryEl = document.getElementById("run-summary");

    function clear(el) {
      while (el.firstChild) el.removeChild(el.firstChild);
    }

    function addSection(parent, title) {
      var section = document.createElement("div");
      section.className = "section";
      var h3 = document.createElement("h3");
      h3.textContent = title;
      section.appendChild(h3);
      parent.appendChild(section);
      return section;
    }

    function addPre(parent, text) {
      var pre = document.createElement("pre");
      pre.className = "code";
      pre.textContent = text == null ? "" : String(text);
      parent.appendChild(pre);
      return pre;
    }

    function addKv(parent, pairs) {
      var dl = document.createElement("dl");
      dl.className = "kv";
      pairs.forEach(function (pair) {
        var dt = document.createElement("dt");
        dt.textContent = pair[0];
        var dd = document.createElement("dd");
        if (pair[2] === "pre") {
          var pre = document.createElement("pre");
          pre.textContent = pair[1];
          dd.appendChild(pre);
        } else if (pair[2] === "code") {
          var code = document.createElement("code");
          code.textContent = pair[1];
          dd.appendChild(code);
        } else {
          dd.textContent = pair[1];
        }
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      parent.appendChild(dl);
      return dl;
    }

    function formatRunSummary(run) {
      if (!run) return "";
      var parts = ["Run " + run.run_id, run.status, run.started_at];
      if (run.total_cost != null) {
        parts.push("$" + Number(run.total_cost).toFixed(4));
      }
      parts.push(
        String(run.total_input_tokens || 0) +
          " in / " +
          String(run.total_output_tokens || 0) +
          " out tokens"
      );
      return parts.join(" · ");
    }

    summaryEl.textContent = formatRunSummary(data.run);

    function renderDetail(node) {
      clear(detailEl);
      if (!node) {
        var p = document.createElement("p");
        p.textContent = "Select a node.";
        detailEl.appendChild(p);
        return;
      }

      var h2 = document.createElement("h2");
      h2.textContent = node.node_id;
      detailEl.appendChild(h2);

      var badge = document.createElement("span");
      badge.className = "badge " + (node.status === "cached" ? "cached" : "ran");
      badge.textContent = node.status;
      detailEl.appendChild(badge);

      var modelSection = addSection(detailEl, "Model & params");
      var kvPairs = [
        ["Model", node.model, "text"],
        ["Params", JSON.stringify(node.params, null, 2), "pre"],
        ["Tokens", node.input_tokens + " in / " + node.output_tokens + " out", "text"],
      ];
      if (node.cost != null) {
        kvPairs.push(["Cost", "$" + Number(node.cost).toFixed(6), "text"]);
      }
      if (node.output_hash) {
        kvPairs.push(["Output hash", node.output_hash, "code"]);
      }
      addKv(modelSection, kvPairs);

      var inputsSection = addSection(detailEl, "Inputs");
      var ul = document.createElement("ul");
      ul.className = "inputs-list";
      (node.inputs || []).forEach(function (inp) {
        var li = document.createElement("li");
        if (inp.kind === "upstream" && inp.node_id) {
          var link = document.createElement("a");
          link.href = "#";
          link.textContent = "↑ " + inp.node_id;
          link.addEventListener("click", function (ev) {
            ev.preventDefault();
            selectNode(inp.node_id);
          });
          li.appendChild(link);
          li.appendChild(document.createTextNode(" "));
          var code = document.createElement("code");
          code.textContent = inp.output_hash || "";
          li.appendChild(code);
        } else if (inp.kind === "source") {
          li.appendChild(document.createTextNode("📄 " + inp.path + " "));
          var hashCode = document.createElement("code");
          hashCode.textContent = inp.content_hash;
          li.appendChild(hashCode);
        }
        ul.appendChild(li);
      });
      inputsSection.appendChild(ul);

      var sysSection = addSection(detailEl, "System prompt");
      addPre(sysSection, node.system_prompt || "");

      var promptSection = addSection(detailEl, "Rendered prompt");
      addPre(promptSection, node.rendered_prompt || "");

      var outSection = addSection(detailEl, "Output");
      var out = node.output || {};
      addPre(outSection, out.text || "");
      if (out.truncated) {
        var note = document.createElement("p");
        note.className = "truncate-note";
        note.textContent =
          "Output truncated for inline viewing (" +
          out.full_size_bytes +
          " bytes in CAS). Hash: " +
          out.output_hash;
        outSection.appendChild(note);
      }
    }

    function selectNode(nodeId) {
      listEl.querySelectorAll(".node-btn").forEach(function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-node") === nodeId);
      });
      renderDetail(nodesById[nodeId]);
    }

    nodes.forEach(function (node) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "node-btn";
      btn.setAttribute("data-node", node.node_id);

      var idSpan = document.createElement("span");
      idSpan.className = "id";
      idSpan.textContent = node.node_id;
      btn.appendChild(idSpan);

      var metaSpan = document.createElement("span");
      metaSpan.className = "meta";
      metaSpan.textContent = node.step + " · " + node.status;
      btn.appendChild(metaSpan);

      btn.addEventListener("click", function () {
        selectNode(node.node_id);
      });
      listEl.appendChild(btn);
    });

    if (nodes.length) {
      selectNode(nodes[0].node_id);
    } else {
      renderDetail(null);
    }
  }

  var el = document.getElementById("cairn-data");
  if (!el) return;

  var stub;
  try {
    stub = JSON.parse(el.textContent);
  } catch (e) {
    showFatal("Failed to parse embedded provenance data.");
    return;
  }

  function start(data) {
    if (data && data.cairn_bundle_version === 3 && global.CairnCapture) {
      global.CairnCapture.boot(data);
      return;
    }
    if (data && (data.kind === "capture" || data.cairn_bundle_version === 2)) {
      bootstrapCapture(data);
      return;
    }
    bootstrap(data);
  }

  function connectLive(eventsUrl, dataPath) {
    if (!eventsUrl || typeof EventSource === "undefined") return;
    var es = new EventSource(eventsUrl);
    var refresh = function () {
      loadSplitPayload(dataPath)
        .then(function (data) {
          start(data);
        })
        .catch(function () {});
    };
    es.addEventListener("append", refresh);
    es.addEventListener("refresh", refresh);
    es.addEventListener("finish", function () {
      es.close();
      refresh();
    });
  }

  if (stub && stub.data_path) {
    loadSplitPayload(stub.data_path)
      .then(function (data) {
        start(data);
        connectLive(stub.live_events_url, stub.data_path);
      })
      .catch(function () {
        showFatal(SPLIT_FILE_MESSAGE);
      });
    return;
  }

  start(stub);
})();
