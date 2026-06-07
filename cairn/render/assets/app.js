(function () {
  "use strict";

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

  if (stub && stub.data_path) {
    loadSplitPayload(stub.data_path)
      .then(function (data) {
        bootstrap(data);
      })
      .catch(function () {
        showFatal(SPLIT_FILE_MESSAGE);
      });
    return;
  }

  bootstrap(stub);
})();
