/* 星火笔·安卓版 v0.11 全功能前端：写作/角色/档案/项目/设置 五大模块 */
(function () {
  var params = new URLSearchParams(location.search);
  var port = params.get("port") || "8000";
  var API = "http://127.0.0.1:" + port + "/api/";
  var mode = "one";
  var _seq = 0;

  function api(path, data, method) {
    if (method === "GET" || data === undefined) {
      var q = data ? Object.keys(data).map(function (k) {
        return encodeURIComponent(k) + "=" + encodeURIComponent(data[k]);
      }).join("&") : "";
      return fetch(API + path + (q ? "?" + q : "")).then(function (r) { return r.json(); });
    }
    return fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {})
    }).then(function (r) { return r.json(); });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function mask(show, msg) {
    document.getElementById("mask").classList.toggle("hidden", !show);
    if (msg) document.getElementById("mask-msg").textContent = msg;
    // v1.52 左侧导航的状态标签（对齐 PC 版「● 空闲 / ● 生成中」）
    var st = document.getElementById("nav-stat");
    if (st) st.textContent = show ? "● 生成中" : "● 空闲";
  }

  function modal(html) {
    document.getElementById("modal-box").innerHTML = html;
    document.getElementById("modal").classList.remove("hidden");
  }
  function closeModal() { document.getElementById("modal").classList.add("hidden"); }
  function err(r) { if (r && r.error) alert(r.error); return r && r.error; }

  function scoresHtml(sc) {
    if (!sc) return "";
    var names = [["immersion", "沉浸"], ["rhythm", "节奏"], ["payout", "爽点"],
                 ["character", "人设"], ["natural", "自然"]];
    return "评分：" + names.map(function (n) {
      return n[1] + (sc[n[0]] != null ? sc[n[0]] : "—");
    }).join("/");
  }

  function metaHtml(review, beats, intent, deai) {
    var h = "";
    if (intent) h += "本章意图（框架裁定）：" + esc(intent) + "<br>";
    if (beats && beats.length) h += "剧情点：" + beats.map(function (b) { return "①" + esc(b); }).join("　") + "<br>";
    if (review) {
      h += "主AI审查：" + (review.approved ? "通过" : "未通过") +
           (review.pacing ? "；节奏：" + esc(review.pacing) : "");
      var sc = scoresHtml(review.scores);
      if (sc) h += "；" + sc;
      if (review.issues && review.issues.length) h += "<br>问题：" + review.issues.map(esc).join("；");
      if (review.cliches && review.cliches.length) h += "<br>套路检测：" + review.cliches.map(esc).join("；");
    }
    if (deai && deai.grade) h += "<br>AI八股治理：命中 " + deai.hits + " 处（等级：" + esc(deai.grade) + "）";
    return h;
  }

  function logsHtml(logs) {
    var box = document.getElementById("logbox");
    var el = document.getElementById("log-list");
    if (!logs || !logs.length) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    el.innerHTML = "";
    logs.forEach(function (l) {
      var d = document.createElement("div");
      if (l.kind === "warn") d.className = "warn";
      d.textContent = l.msg;
      el.appendChild(d);
    });
    el.scrollTop = el.scrollHeight;
  }

  // ================= 写作（v0.12 任务化 + 实时进度） =================
  var _taskTimer = null;
  var _lastLogCount = 0;

  function setMode(m) {
    mode = m;
    // v1.56：只切「生成本章」这条 seg（页面上还有别的 seg，全局选会误改）
    var seg = document.getElementById("mode-seg");
    if (seg) {
      seg.querySelectorAll("button").forEach(function (b) {
        b.classList.toggle("on", b.dataset.mode === m);
      });
    }
    var row = document.getElementById("auto-row");
    if (row) row.classList.toggle("hidden", m !== "auto");
    var btn = document.getElementById("btn-gen");
    if (btn) btn.textContent = m === "auto" ? "全自动连写" : "生成下一章";
  }

  // ================= 一键成书（v0.21：AI 自动立项 + 全自动连写，随时可停止） =================
  var _bookTid = null;
  var _bookLast = 0;
  var _bookTimer = null;
  function bookStart() {
    // v1.56：一键成书是项目页的第 6 个中页签，入口按钮直接切到那个页签
    switchTab("project");
    subTab("project", "p-book");
  }

  // v1.56 一键成书参数面板（对齐 PC gui_book）：
  // 「AI 自动判断章节数」勾上时总章节数输入框交给 AI 定，界面置灰提示
  function bookAutoToggle() {
    var on = document.getElementById("m-book-auton").checked;
    var total = document.getElementById("m-book-total");
    if (total) total.disabled = !!on;
    var n = document.getElementById("m-book-n");
    if (n) n.disabled = !!on;
  }

  function loadBreakStyleOptions() {
    api("breaks_list", {}, "GET").then(function (r) {
      var sel = document.getElementById("m-book-break-style");
      if (!sel) return;
      var cur = sel.value;
      sel.innerHTML = '<option value="">不使用（默认）</option>' + ((r && r.breaks) || [])
        .map(function (b) {
          return '<option value="' + esc(b.name) + '">' + esc(b.name) + '</option>';
        }).join("");
      if (cur) sel.value = cur;
    }).catch(function () {});
  }

  function loadBookSceneList() {
    api("scene_cards_project_list", {}, "GET").then(function (r) {
      var el = document.getElementById("m-book-scene-list");
      if (!el) return;
      var cards = (r && r.cards) || [];
      if (!cards.length) {
        el.innerHTML = "尚未勾选情景写作提示词（可选）：主AI每章会按正文类型从「情景提示词」库挑卡注入。";
        return;
      }
      el.innerHTML = "已加入 " + cards.length + " 张：" +
        cards.map(function (c) { return esc(c.name); }).join("、");
    }).catch(function () {});
  }

  // 情景写作提示词：从总库勾选带进本项目（一键成书与项目库同一份 project.scene_cards）
  function pickBookSceneCards() {
    api("scene_cards_list", {}, "GET").then(function (r) {
      if (err(r)) return;
      var all = (r.cards || []).map(function (c) { return c.name; }).filter(Boolean);
      if (!all.length) {
        alert("总库还没有情景卡——到「情景提示词」页新增 / AI 一键生成 / 导入几张。");
        return;
      }
      api("scene_cards_project_list", {}, "GET").then(function (pr) {
        var have = {};
        ((pr && pr.cards) || []).forEach(function (c) { have[c.name] = true; });
        modal(
          '<div class="row"><b>从总库加入本项目的情景写作提示词</b></div>' +
          '<div class="dim">勾选要带进本项目的卡（已加入的不再重复）。</div>' +
          all.map(function (nm) {
            return '<label class="chk"><input type="checkbox" class="m-sc-cb" value="' +
              esc(nm) + '"' + (have[nm] ? " checked disabled" : "") + "> " + esc(nm) +
              (have[nm] ? "（已在项目库）" : "") + "</label>";
          }).join("") +
          '<div class="btnrow"><button class="primary" onclick="applyBookSceneCards()">加入</button>' +
          '<button onclick="closeModal()">取消</button></div>');
      });
    });
  }

  function applyBookSceneCards() {
    var names = Array.prototype.slice
      .call(document.querySelectorAll("#modal-box .m-sc-cb"))
      .filter(function (b) { return b.checked && !b.disabled; })
      .map(function (b) { return b.value; });
    if (!names.length) { alert("请至少勾选一张卡。"); return; }
    api("scene_cards_project_add", { names: names }, "POST").then(function (r) {
      if (err(r)) return;
      closeModal();
      alert("✓ 已加入 " + (r.added || 0) + " 张（本项目库现有 " + (r.count || 0) + " 张）。");
      loadBookSceneList();
      loadProjectSceneCards();
    });
  }

  // 「✓ 应用以上设置到当前项目」：把面板里的文风/提示词/拆书风格/情景卡写进当前项目
  function applyBookSettings() {
    var patch = {
      style_note: document.getElementById("m-book-style-note").value,
      style_ref: document.getElementById("m-book-style-ref").value,
      main_prompt: document.getElementById("m-book-main-prompt").value,
      writer_prompt: document.getElementById("m-book-writer-prompt").value,
      break_style: document.getElementById("m-book-break-style").value
    };
    mask(true, "应用到当前项目…");
    saveProjectFields(patch).then(function (r) {
      mask(false);
      if (err(r)) return;
      var sc = document.getElementById("m-book-scene-list");
      alert("✓ 已把文风要点/参考样本/主AI提示词/正文AI提示词" +
        (patch.break_style ? "、拆书设计风格《" + patch.break_style + "》" : "") +
        "应用到当前项目（情景卡请在「情景提示词」页加入本项目库）。");
      refreshState();
      loadProjectForm();
      if (sc) loadBookSceneList();
    }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  function bookParams() {
    return {
      book_title: document.getElementById("m-book-title").value.trim(),
      auto_chapters: document.getElementById("m-book-auton").checked,
      total_chapters: parseInt(document.getElementById("m-book-total").value, 10) || 30,
      style_note: document.getElementById("m-book-style-note").value,
      style_ref: document.getElementById("m-book-style-ref").value,
      main_prompt: document.getElementById("m-book-main-prompt").value,
      writer_prompt: document.getElementById("m-book-writer-prompt").value,
      break_style: document.getElementById("m-book-break-style").value,
      scene_cards_active: []
    };
  }

  function bookSubmit() {
    var idea = document.getElementById("m-book-idea").value.trim();
    if (!idea) { alert("请先描述你想写什么小说（一句话也行）。"); return; }
    var n = parseInt(document.getElementById("m-book-n").value, 10) || 5;
    var total = parseInt(document.getElementById("m-book-total").value, 10) || 30;
    var auto = document.getElementById("m-book-auton").checked;
    if (auto && !confirm("已勾选「AI 自动判断章节数」：本次会由 AI 判断全书约多少章，"
        + "并直接一直写到那个章数（可能比输入的本次章数多很多）。继续？")) return;
    var p = bookParams();
    p.idea = idea;
    p.chapters = n;
    api("book_auto", p, "POST").then(function (r) {
      if (err(r)) return;
      _bookTid = r.task_id;
      _bookLast = 0;
      showBookPanel(auto ? 0 : n);
      bookPoll();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function bookContinue() {
    // v0.42 继续写：在「当前项目」上从断点自动连写剩余章节（不重新立项）
    var n = parseInt(document.getElementById("m-book-n").value, 10) || 5;
    if (!confirm("在「当前项目」上从断点继续自动连写，一直写到第 " + n + " 章？\n"
        + "（不会重新立项、不会覆盖已写章节）")) return;
    api("book_auto", { idea: "", chapters: n, continue: true }, "POST").then(function (r) {
      if (err(r)) return;
      _bookTid = r.task_id;
      _bookLast = 0;
      showBookPanel(n);
      bookPoll();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function showBookPanel(total) {
    document.getElementById("book-prog").classList.remove("hidden");
    document.getElementById("book-msg").textContent = "正在立项…";
    document.getElementById("m-book-run").disabled = true;
    document.getElementById("m-book-continue").disabled = true;
    document.getElementById("m-book-stop").disabled = false;
    document.getElementById("book-logs").innerHTML = "";
    var bar = document.getElementById("book-prog");
    bar.querySelector("div").style.width = "0%";
    // 收起按钮文案不变；运行中不允许收起（提示）
  }
  function bookStop() {
    if (!_bookTid) return;
    api("book_stop", { task_id: _bookTid }, "POST").then(function (r) {
      var b = document.getElementById("m-book-stop");
      if (b) { b.disabled = true; b.textContent = "已请求停止（写完当前章后结束）…"; }
      document.getElementById("book-msg").textContent = "正在停止…";
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function bookPoll() {
    if (!_bookTid) return;
    api("task_status", { task_id: _bookTid, since: _bookLast }, "GET").then(function (r) {
      if (r.error) { alert(r.error); _bookTid = null; return; }
      if (r.logs && r.logs.length) {
        _bookLast = r.count;
        var box = document.getElementById("book-logs");
        if (box) {
          r.logs.forEach(function (l) {
            var d = document.createElement("div");
            if (l.kind === "warn") d.className = "warn";
            if (l.kind === "error") d.className = "warn";
            d.textContent = l.msg;
            box.appendChild(d);
            box.scrollTop = box.scrollHeight;
          });
        }
        var m = r.logs[r.logs.length - 1].msg || "";
        if (m.indexOf("一键成书结束") >= 0 || m.indexOf("已收到停止指令") >= 0) {
          var b2 = document.getElementById("book-msg");
          if (b2) b2.textContent = m;
        }
      }
      if (r.pending) { showBeatsConfirm(_bookTid, r); return; }
      if (r.done) {
        _bookTid = null;
        var res = r.result || {};
        if (r.error) { alert(r.error); return; }
        var bar = document.getElementById("book-prog");
        if (bar) bar.querySelector("div").style.width = "100%";
        var msgEl = document.getElementById("book-msg");
        if (msgEl) msgEl.textContent = res.msg ||
          ("《" + (res.title || "") + "》完成 " + (res.chapters || 0) + " 章");
        var stopBtn = document.getElementById("m-book-stop");
        if (stopBtn) { stopBtn.disabled = true; stopBtn.textContent = "已结束"; }
        var runBtn = document.getElementById("m-book-run");
        if (runBtn) runBtn.disabled = false;
        var contBtn = document.getElementById("m-book-continue");
        if (contBtn) contBtn.disabled = false;   // v0.42 完成后可继续写更多章
        setTimeout(function () {
          refreshState(); loadDrafts(); renderProjects(); loadTimeline();
        }, 600);
        return;
      }
      var p = r.progress;
      if (p && p.total) {
        var bar2 = document.getElementById("book-prog");
        if (bar2) bar2.querySelector("div").style.width =
          Math.round(p.done * 100 / p.total) + "%";
        var m2 = document.getElementById("book-msg");
        if (m2) m2.textContent = "已写 " + p.done + " / " + p.total + " 章";
      }
      _bookTimer = setTimeout(bookPoll, 1100);
    }).catch(function (e) { alert("请求失败：" + e); _bookTid = null; });
  }

  // ================= 小说导入成项目（v0.27：txt 小说 → 完整项目还原，随时可停止） =================
  var _importTid = null;
  var _importLast = 0;
  var _importFname = null;
  function importToggle() {
    // v1.56：小说导入成项目是项目页的第 7 个中页签，入口按钮直接切到那个页签
    switchTab("project");
    subTab("project", "p-import");
  }
  // 导入设置：模式切换（简单只留基本参数 / 高级全开；智能显示档位+上下文）
  function setImportMode(mode) {
    var seg = document.getElementById("import-mode-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-mode") === mode);
    });
    var adv = mode === "advanced";
    var smt = mode === "smart" || adv;
    var smart = mode === "smart";
    document.querySelectorAll("#import-card .adv-only").forEach(function (el) {
      el.style.display = adv ? "" : "none";
    });
    document.querySelectorAll("#import-card .smart-only").forEach(function (el) {
      el.style.display = smart ? "" : "none";
    });
    var pn = document.getElementById("m-import-parn");
    if (pn) pn.style.display = smt ? "" : "none";
    var pp = document.getElementById("m-import-prompt");
    if (pp) pp.style.display = smt ? "" : "none";
    var token = document.getElementById("m-import-token");
    if (token) token.style.display = smart ? "none" : "";
  }
  // 导入设置：智能档位切换（保守/正常/激进）
  function setImportSmart(sub) {
    var seg = document.getElementById("import-smart-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-sub") === sub);
    });
  }
  // 导入设置：并行/串行切换（与拆书工坊同键，保存即生效）
  function setImportPar(v) {
    var seg = document.getElementById("import-par-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-par") === v);
    });
  }
  function initImportTab() {
    api("settings_get", {}, "GET").then(function (r) {
      if (err(r)) return;
      setImportMode(r.break_mode || "smart");
      setImportSmart(r.break_smart_sub || "balanced");
      var t = document.getElementById("m-import-token");
      if (t && r.break_token_per_part) t.value = r.break_token_per_part;
      var ctx = document.getElementById("m-import-ctx");
      if (ctx) ctx.value = r.model_context_window == null ? 0 : r.model_context_window;
      var ov = document.getElementById("m-import-overlap");
      if (ov) ov.value = r.break_overlap_token == null ? 0 : r.break_overlap_token;
      var l3 = document.getElementById("m-import-l3");
      if (l3) l3.value = r.break_l3_batch == null ? 0 : r.break_l3_batch;
      var pn = document.getElementById("m-import-parn");
      if (pn && r.break_parallel_n) pn.value = r.break_parallel_n;
      var pp = document.getElementById("m-import-prompt");
      if (pp && r.break_prompt) pp.value = r.break_prompt;
      var ii = document.getElementById("m-import-intro");
      if (ii && r.import_intro) ii.value = r.import_intro;
      setImportPar(r.break_parallel ? "1" : "0");
    }).catch(function () {});
  }
  function saveImportSettings() {
    var mbtn = document.querySelector("#import-mode-seg button.on");
    var mode = mbtn ? mbtn.getAttribute("data-mode") : "smart";
    var sbtn = document.querySelector("#import-smart-seg button.on");
    var sub = sbtn ? sbtn.getAttribute("data-sub") : "balanced";
    var token = parseInt(document.getElementById("m-import-token").value, 10) || 8000;
    var ctx = parseInt(document.getElementById("m-import-ctx").value, 10) || 0;
    var ov = parseInt(document.getElementById("m-import-overlap").value, 10) || 0;
    var l3 = parseInt(document.getElementById("m-import-l3").value, 10) || 0;
    var parn = parseInt(document.getElementById("m-import-parn").value, 10) || 2;
    var par = document.querySelector("#import-par-seg button.on");
    api("settings_save", {
      break_mode: mode,
      break_smart_sub: sub,
      model_context_window: Math.max(0, Math.min(10000000, ctx)),
      break_token_per_part: Math.max(1000, token),
      break_overlap_token: Math.max(0, ov),
      break_l3_batch: Math.max(0, Math.min(60, l3)),
      break_parallel: par && par.getAttribute("data-par") === "1",
      break_parallel_n: Math.max(1, Math.min(8, parn)),
      break_prompt: document.getElementById("m-import-prompt").value.trim(),
      import_intro: document.getElementById("m-import-intro").value.trim()
    }, "POST").then(function (r) {
      if (err(r)) return;
      var tok = mode === "smart"
        ? "按上下文×" + (sub === "conservative" ? "30%" : sub === "aggressive" ? "70%" : "50%") + " 自动定档"
        : "每部分 " + token + " token";
      alert("✓ 导入设置已保存：" + (mode === "advanced" ? "高级" : mode === "simple" ? "简单" : "智能")
        + (mode === "smart" ? "·" + (sub === "conservative" ? "保守" : sub === "aggressive" ? "激进" : "正常") : "")
        + "，" + tok + (ov ? " / 重叠 " + ov : "") + (l3 ? " / L3 分批 " + l3 : "")
        + "；拆书与人物抽取按此执行，小说规划注入各分析环节（防止跑偏）；API 在「设置」页选择。");
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  // 教程页分页切换（v0.29：快速上手/写作/角色/项目/拆书/设置）
  function tutShow(key) {
    var seg = document.getElementById("tut-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.dataset.tut === key);
    });
    ["quick", "write", "char", "project", "chat", "style", "break", "story", "settings"].forEach(function (k) {
      var el = document.getElementById("tut-" + k);
      if (el) el.classList.toggle("hidden", k !== key);
    });
  }

  function importRestart() {
    // v0.39 重新开始导入：清空进度全部重来（不再续传）
    if (!_importFname) { alert("请先选择小说 txt。"); return; }
    if (_importTid) { alert("导入进行中，请先停止或等待完成。"); return; }
    if (!confirm("将清除本次 txt 的导入进度，从头重新导入（不再续传）。确定吗？")) return;
    importSubmit(true);
  }
  function importSubmit(restart) {
    if (!_importFname) { alert("请先选择小说 txt。"); return; }
    if (_importTid) { alert("导入进行中，请先停止或等待完成。"); return; }
    var title = document.getElementById("m-import-title").value.trim();
    api("import_start", {
      fname: _importFname,
      title: title,
      restart: !!restart
    }, "POST").then(function (r) {
      if (err(r)) return;
      _importTid = r.task_id;
      _importLast = 0;
      document.getElementById("import-logs").innerHTML = "";
      document.getElementById("import-prog").classList.remove("hidden");
      document.getElementById("m-import-run").disabled = true;
      document.getElementById("m-import-restart").disabled = true;
      document.getElementById("m-import-stop").disabled = false;
      document.getElementById("import-msg").textContent =
        "正在导入：解析 → 拆书 → 设定合成 → 人物抽取 → 角色卡 → 落库…";
      importPoll();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function importStop() {
    if (!_importTid) return;
    api("import_stop", { task_id: _importTid }, "POST").then(function (r) {
      var b = document.getElementById("m-import-stop");
      if (b) { b.disabled = true; b.textContent = "已请求停止…"; }
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function importPoll() {
    if (!_importTid) return;
    api("task_status", { task_id: _importTid, since: _importLast }, "GET").then(function (r) {
      if (r.error) { alert(r.error); _importTid = null; return; }
      if (r.logs && r.logs.length) {
        _importLast = r.count;
        var box = document.getElementById("import-logs");
        if (box) {
          r.logs.forEach(function (l) {
            var d = document.createElement("div");
            if (l.kind === "warn" || l.kind === "error") d.className = "warn";
            d.textContent = l.msg;
            box.appendChild(d);
            box.scrollTop = box.scrollHeight;
          });
        }
        var lastMsg = r.logs[r.logs.length - 1].msg || "";
        if (lastMsg.indexOf("导入完成") >= 0 || lastMsg.indexOf("已停止") >= 0) {
          document.getElementById("import-msg").textContent = lastMsg;
        }
      }
      if (r.done) {
        _importTid = null;
        var res = r.result || {};
        document.getElementById("import-prog").classList.add("hidden");
        document.getElementById("m-import-run").disabled = false;
        document.getElementById("m-import-restart").disabled = false;
        var stopBtn = document.getElementById("m-import-stop");
        if (stopBtn) { stopBtn.disabled = true; stopBtn.textContent = "停止"; }
        if (r.error) {
          document.getElementById("import-msg").textContent = "✖ " + r.error;
        } else if (res && res.ok) {
          var st = res.stats || {};
          document.getElementById("import-msg").textContent =
            "✓ 已还原为项目《" + (res.title || "") + "》：共 " + (st.chapters || 0) +
            " 章 / " + (st.characters || 0) + " 个角色，已加入书架。" +
            "删除章节后角色卡会自动回退到对应章节。";
          setTimeout(function () { loadProjects(); refreshState(); loadTimeline(); }, 600);
        }
        return;
      }
      var p = r.progress;
      if (p && p.total) {
        var bar = document.getElementById("import-prog");
        if (bar) bar.querySelector("div").style.width =
          Math.round(p.done * 100 / p.total) + "%";
      }
      setTimeout(importPoll, 1100);
    }).catch(function (e) { alert("请求失败：" + e); _importTid = null; });
  }

  // v1.56 生成页：任务 id / 运行态按钮 / 进度条（对齐 PC gui_generate）
  var _genTid = null;

  function genRunning(on) {
    var b = document.getElementById("btn-gen");
    if (b) b.disabled = !!on;
    var s = document.getElementById("btn-stop-gen");
    if (s) {
      s.disabled = !on;
      s.textContent = "■ 停止";
    }
    var st = document.getElementById("gen-state");
    if (st) {
      st.textContent = on ? "● 生成中" : "● 空闲";
      st.className = "badge" + (on ? " ok" : "");
    }
    var p = document.getElementById("gen-prog");
    if (p) {
      p.classList.toggle("hidden", !on);
      if (on) p.querySelector("div").style.width = "0%";
    }
  }

  function doGenerate() {
    var directive = document.getElementById("in-directive").value;
    var beats = document.getElementById("in-beats").value.split("\n")
      .map(function (s) { return s.trim(); }).filter(Boolean);
    var draft = document.getElementById("in-draft").value;
    mask(true, mode === "auto" ? "全自动连写中…（逐章生成并定稿）" : "正在生成…（RP 管线运行中）");
    renderSteps(0);
    genRunning(true);
    var hint = document.getElementById("gen-hint");
    if (hint) {
      hint.textContent = mode === "auto"
        ? "全自动连写中：审过一章自动写下一章，可点「■ 停止」（写完当前章后结束）。"
        : "正在生成：主AI决断 → 角色推理 → 综合校验 → 正文写作 → 主AI审查。";
    }
    api("generate", {
      mode: mode,
      chapters: parseInt(document.getElementById("in-auto-n").value, 10) || 3,
      directive: directive, beats: beats, draft: draft,
      confirm_beats: getConfirmBeats()
    }, "POST").then(function (r) {
      if (err(r)) { mask(false); genRunning(false); return; }
      _genTid = r.task_id;
      pollTask(r.task_id);
    }).catch(function (e) { mask(false); genRunning(false); alert("请求失败：" + e); });
  }

  // 生成页「■ 停止」：与一键成书同一停止通道（写完当前章后结束）
  function stopGenerate() {
    if (!_genTid) { alert("当前没有正在生成的任务。"); return; }
    var s = document.getElementById("btn-stop-gen");
    if (s) { s.disabled = true; s.textContent = "正在停止…"; }
    api("book_stop", { task_id: _genTid }, "POST").then(function (r) {
      var h = document.getElementById("gen-hint");
      if (h) h.textContent = "已请求停止：写完当前章后结束（已生成的章节都保留）。";
    }).catch(function (e) { alert("请求失败：" + e); });
  }

  function pollTask(tid) {
    api("task_status", { task_id: tid, since: _lastLogCount }, "GET").then(function (r) {
      if (r.error) { mask(false); alert(r.error); return; }
      if (r.logs && r.logs.length) {
        appendLogs(r.logs);
        _lastLogCount = r.count;
        renderStepsFromLogs(r.logs);
      }
      // v1.56 全自动连写进度（已写 N / 目标 M 章）→ 生成页进度条
      if (r.progress && r.progress.total) {
        var bar = document.getElementById("gen-prog");
        if (bar) {
          bar.classList.remove("hidden");
          bar.querySelector("div").style.width =
            Math.round((r.progress.done || 0) * 100 / r.progress.total) + "%";
        }
        var gh = document.getElementById("gen-hint");
        if (gh) gh.textContent = "全自动连写：已写 " + (r.progress.done || 0) +
          " / " + r.progress.total + " 章（可随时停止）。";
      }
      // v0.15 剧情点确认关卡：任务暂停，弹窗让用户确认/修改主AI规划的剧情点
      if (r.pending) {
        showBeatsConfirm(tid, r);
        return;
      }
      if (!r.done) {
        _taskTimer = setTimeout(function () { pollTask(tid); }, 1100);
        return;
      }
      mask(false);
      _genTid = null;
      genRunning(false);
      if (r.error) {
        alert(r.error);
        renderSteps(0);
        var eh = document.getElementById("gen-hint");
        if (eh) eh.textContent = "✖ " + r.error;
        return;
      }
      handleResult(r.result);
    }).catch(function (e) {
      mask(false);
      _genTid = null;
      genRunning(false);
      alert("请求失败：" + e);
    });
  }

  // ================= 生成前剧情点确认关卡（v0.15） =================
  var _confirmTid = null;
  function showBeatsConfirm(tid, r) {
    _confirmTid = tid;
    mask(false);
    var beats = r.beats || [];
    var dir = r.direction || "";
    modal(
      '<div class="row"><b>生成前确认剧情点</b></div>' +
      (dir ? '<div class="dim">本章走向：' + esc(dir) + '</div>' : '') +
      '<label>主AI规划的剧情点（可增删改，每行一条，将作为本章硬要求）</label>' +
      '<textarea id="m-beats" rows="6">' + esc(beats.join("\n")) + '</textarea>' +
      '<div class="btnrow">' +
      '<button class="primary" onclick="confirmBeatsSubmit()">确认，按此继续生成</button>' +
      '<button onclick="confirmBeatsSkip()">跳过（沿用主AI规划）</button>' +
      '</div>');
  }
  function confirmBeatsSubmit() {
    var beats = document.getElementById("m-beats").value.split("\n")
      .map(function (s) { return s.trim(); }).filter(Boolean);
    taskConfirm(_confirmTid, beats);
  }
  function confirmBeatsSkip() {
    taskConfirm(_confirmTid, null);
  }
  function taskConfirm(tid, beats) {
    closeModal();
    mask(true, "正在生成正文…");
    api("task_confirm", { task_id: tid, beats: beats }, "POST").then(function (r) {
      if (err(r)) { mask(false); return; }
      pollTask(tid);
    }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  function appendLogs(logs) {
    var box = document.getElementById("logbox");
    box.classList.remove("hidden");
    var el = document.getElementById("log-list");
    logs.forEach(function (l) {
      var d = document.createElement("div");
      if (l.kind === "warn") d.className = "warn";
      d.textContent = l.msg;
      el.appendChild(d);
    });
    el.scrollTop = el.scrollHeight;
  }

  var STEPS = ["decide", "reason", "consolidate", "write", "review"];
  var STEP_KW = [
    ["①", "主AI决断", "决断"],
    ["②", "角色推理", "推理"],
    ["③", "综合校验", "校验"],
    ["④", "正文AI写作", "写作"],
    ["⑤", "主AI审查", "审查"]
  ];

  function renderSteps(idx) {
    document.querySelectorAll("#mask-steps .st").forEach(function (el, i) {
      el.classList.toggle("on", i === idx);
      el.classList.toggle("done", i < idx);
    });
  }

  function renderStepsFromLogs(logs) {
    var joined = (logs[logs.length - 1] || {}).msg || "";
    for (var i = 0; i < STEP_KW.length; i++) {
      if (STEP_KW[i].slice(1).some(function (k) { return joined.indexOf(k) >= 0; })) {
        renderSteps(i);
        return;
      }
    }
  }

  function handleResult(r) {
    document.getElementById("log-list").innerHTML = "";
    _lastLogCount = 0;
    if (r.error) { alert(r.error); return; }
    if (r.done && Array.isArray(r.done)) {
      alert("已完成 " + r.done.length + " 章：" + r.done.map(function (c) {
        return "第" + c.seq + "章" + (c.title ? "《" + c.title + "》" : "");
      }).join("、"));
      refreshState(); loadDrafts(); loadChapters(); loadGenChapters(); loadTimeline();
      document.getElementById("in-directive").value = "";
      var gh0 = document.getElementById("gen-hint");
      if (gh0) gh0.textContent = "✓ 连写结束：共 " + r.done.length + " 章。";
      return;
    }
    document.getElementById("result").classList.remove("hidden");
    document.getElementById("result").dataset.seq = String(r.seq || "");
    var oseq = document.getElementById("out-seq");
    if (oseq) oseq.textContent = String(r.seq || "?");
    var ob = document.getElementById("out-badge");
    if (ob) { ob.className = "badge"; ob.textContent = "待定稿"; }
    document.getElementById("out-title").value = r.title || "";
    document.getElementById("out-content").value = r.content || "";
    document.getElementById("out-meta").innerHTML = metaHtml(r.review, r.beats, r.intent, r.deai);
    var gh = document.getElementById("gen-hint");
    if (gh) gh.textContent = "本章草稿已生成——在下面「本章草稿」里改标题/正文，满意后点「✓ 通过并完成本章」。";
    var res = document.getElementById("result");
    if (res) res.scrollIntoView({ block: "start" });
    refreshState();
    loadGenChapters();
  }

  function refreshState() {
    return api("state").then(function (s) {
      if (!s.ok) return;
      window.__lastProject = s.project || null;
      if (s.project) {
        document.getElementById("p-title").textContent = s.project.title;
        document.getElementById("side-proj").textContent = s.project.title;
        document.getElementById("p-meta").textContent =
          "下一章：第 " + s.project.next_chapter + " 章　已写 " + s.project.chapters +
          " 章　角色 " + s.project.characters + " 名";
        var hint = "";
        (s.project.next_chapter || 1);
        document.getElementById("p-plan-hint").textContent =
          s.project.summary ? "管理笔记：" + s.project.summary : "";
        document.getElementById("p-status").className = "badge ok";
        document.getElementById("p-status").textContent = "已建项目";
      } else {
        document.getElementById("p-title").textContent = "未创建项目";
        document.getElementById("side-proj").textContent = "未载入项目";
        document.getElementById("p-meta").textContent = "请到「项目」页填写并保存";
        document.getElementById("p-plan-hint").textContent = "";
        document.getElementById("p-status").textContent = "";
      }
    });
  }

  function doFinalize() {
    var seq = document.getElementById("result").dataset.seq;
    if (!seq) { alert("请先生成本章。"); return; }
    mask(true, "归档中…");
    api("finalize", { seq: seq,
      title: document.getElementById("out-title").value,
      content: document.getElementById("out-content").value }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      document.getElementById("result").classList.add("hidden");
      document.getElementById("in-directive").value = "";
      document.getElementById("in-beats").value = "";
      document.getElementById("in-draft").value = "";
      refreshState(); loadChapters(); loadDrafts();
      alert("第 " + seq + " 章已定稿。");
    }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  function doRegenerate() {
    var seq = document.getElementById("result").dataset.seq;
    if (!seq) { alert("请先生成本章。"); return; }
    mask(true, "按意见重写中…");
    api("regenerate", { seq: seq, feedback: document.getElementById("in-feedback").value }, "POST")
      .then(function (r) {
        mask(false);
        if (err(r)) return;
        document.getElementById("result").dataset.seq = String(r.seq || "");
        document.getElementById("out-title").value = r.title || "";
        document.getElementById("out-content").value = r.content || "";
        document.getElementById("out-meta").innerHTML = metaHtml(r.review, r.beats, r.intent, r.deai);
        logsHtml(r.logs);
      }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  function toggleLogs() {
    document.getElementById("log-list").classList.toggle("hidden");
  }

  function loadDrafts() {
    api("drafts_list").then(function (r) {
      var el = document.getElementById("draft-list");
      document.getElementById("draft-count").textContent = r.ok ? "（" + r.drafts.length + " 份）" : "";
      el.innerHTML = "";
      if (!r.ok || !r.drafts.length) {
        el.innerHTML = '<div class="dim">编辑/删除/重写章节时自动备份，可随时找回。</div>';
        return;
      }
      r.drafts.forEach(function (d) {
        var row = document.createElement("div");
        row.className = "char-item";
        row.innerHTML = "<div><b>第 " + d.index + " 章</b> <span class='dim'>" + esc(d.tag || "") +
          " · " + esc(d.saved_at) + "</span></div>" +
          '<div><button class="mini" onclick="restoreDraft(\'' + d.fname + '\')">恢复</button>' +
          '<button class="mini" onclick="delDraft(\'' + d.fname + '\')">删</button></div>';
        el.appendChild(row);
      });
    });
  }

  // ================= 生成页（v1.56 移植 PC gui_generate） =================
  function initGenerateTab() {
    genRunning(false);
    loadPlansDetail();
    loadGenChapters();
    loadDrafts();
    loadMainPrompt();
  }

  function loadMainPrompt() {
    api("state").then(function (s) {
      var el = document.getElementById("g-main-prompt");
      if (!el) return;
      var p = (s && s.project) || null;
      el.value = p ? (p.main_prompt || "") : "";
    }).catch(function () {});
  }

  function saveMainPrompt() {
    var v = document.getElementById("g-main-prompt").value;
    // project_save 是全量覆盖语义：只改主AI提示词时必须把其余字段带回，否则会被清空
    saveProjectFields({ main_prompt: v }).then(function (r) {
      if (err(r)) return;
      var el = document.getElementById("p-main-prompt");
      if (el) el.value = v;
      alert("✓ 主AI提示词已保存（项目其余设定不受影响）。");
      refreshState();
    });
  }

  function loadGenChapters() {
    api("chapters").then(function (r) {
      var el = document.getElementById("gen-chlist");
      if (!el) return;
      var list = (r && r.chapters) || [];
      var cnt = document.getElementById("gen-count");
      if (cnt) cnt.textContent = "（共 " + list.length + " 章）";
      el.innerHTML = "";
      if (!list.length) {
        el.innerHTML = '<div class="dim">还没有已归档章节。到上面「生成本章」生成第一章，' +
          '或在「码字」页手写一章。</div>';
        return;
      }
      list.sort(function (a, b) { return a.seq - b.seq; });
      list.forEach(function (c) {
        var row = document.createElement("div");
        row.className = "chi";
        row.innerHTML = "<div><b>第 " + c.seq + " 章 · " + esc(c.title || "") + "</b>" +
          "<div class='dim'>" + (c.status === "approved" ? "已定稿" : "草稿") + " · 第 " +
          (c.vol || 1) + " 卷 · " + (c.chars || 0) + " 字</div>" +
          "<div class='dim'>" + esc(c.brief || "") + "</div></div>" +
          '<div class="row" style="flex:0 0 auto">' +
          '<button class="mini" onclick="genOpenChapter(' + c.seq + ')">阅读</button>' +
          '<button class="mini" onclick="genEditChapter(' + c.seq + ')">✎ 编辑</button>' +
          '<button class="mini" onclick="genReviewChapter(' + c.seq + ')">AI 审稿</button>' +
          '<button class="mini" style="color:var(--red)" onclick="genDeleteChapter(' + c.seq +
          ')">🗑 删除</button></div>';
        el.appendChild(row);
      });
    });
  }

  function genOpenChapter(seq) {
    switchTab("archive");
    subTab("archive", "timeline");
    openChapter(seq);
  }

  function genEditChapter(seq) {
    _curChSeq = seq;
    editChapter();
  }

  function genReviewChapter(seq) { openEditorReview(seq); }

  function genDeleteChapter(seq) {
    if (!confirm("删除第 " + seq + " 章？\n正文会先备份到草稿箱；删除后角色卡会自动回退到对应章节。")) return;
    api("chapter_delete", { seq: seq }, "POST").then(function (r) {
      if (err(r)) return;
      alert("已删除第 " + seq + " 章（原版在草稿箱，可随时找回）。");
      loadGenChapters();
      loadWorkList();
      loadDrafts();
      refreshState();
      loadTimeline();
    });
  }

  function openSearchBox() {
    modal('<div class="row"><b>全文搜索</b></div>' +
      '<label>关键词（标题 / 正文 / 梗概）</label>' +
      '<input id="m-search-kw" placeholder="输入关键词后回车">' +
      '<div class="btnrow"><button class="primary" onclick="doSearchBox()">搜索</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function doSearchBox() {
    var kw = (document.getElementById("m-search-kw").value || "").trim();
    if (!kw) { alert("请输入关键词。"); return; }
    closeModal();
    switchTab("archive");
    subTab("archive", "timeline");
    document.getElementById("ch-search-full").value = kw;
    searchChapters(kw);
  }

  // 章节标题重设计（任务化，可停止；只改标题不动正文）
  // v1.58：默认勾选「让 AI 阅读正文后命名」（每章附正文开头摘录，取题更准）；
  // 取消勾选则只看梗概省 token
  var _rtTid = null;
  // v1.65 内置默认章节标题命名规则（与后端 prompts.DEFAULT_TITLE_RULES 同文）
  var DEFAULT_TITLE_RULES = "标题要浓缩本章发生的事，写成『章节钩子』而不是内容复述：亮出冲突、悬念或情绪缺口，不把结果写进标题（剧透）；忌用『真相/秘密/震惊/意外来袭/惊天/大战』这类空泛词；优先用具体动作+物件、身份+关系、反差对撞、具体数字（如『保险柜里的照片有七个人，四个已经死了』）；『xx与xx』式可以用，但两项须是本章真正并列/对照的要素，不硬凑、不连续多章同一句式；长度随本书气质：网文向短句有钩子（约10~18字），文学向含蓄对仗（约2~8字，如『梅雨夜的钢琴声』）；相邻章节句式要有变化。";
  function resetTitleRules() {
    document.getElementById("p-title-rules").value = DEFAULT_TITLE_RULES;
    document.getElementById("rt-title-rules").value = DEFAULT_TITLE_RULES;
    api("project_title_rules", { text: DEFAULT_TITLE_RULES }, "POST").then(function (r) {
      if (err(r)) return;
    });
  }
  function doRetitle() {
    var from = parseInt(document.getElementById("rt-from").value, 10) || 1;
    var to = parseInt(document.getElementById("rt-to").value, 10) || from;
    var withContent = document.getElementById("rt-content").checked;
    if (!confirm("重新设计第 " + from + "~" + to + " 章的章节名？\n" +
        (withContent ? "（AI 会阅读每章完整正文后取题，标题更贴合内容）" :
         "（本次只看梗概取题，省 token）") +
        "\n只改标题、正文与顺序不动；原标题会备份到草稿箱")) return;
    var msg = document.getElementById("rt-msg");
    var btn = document.getElementById("rt-btn");
    if (btn) btn.disabled = true;
    if (msg) msg.textContent = "正在重设计章节名…";
    api("retitle", { start: from, end: to, content: withContent,
      title_rules: document.getElementById("rt-title-rules").value }, "POST").then(function (r) {
      if (err(r)) {
        if (btn) btn.disabled = false;
        if (msg) msg.textContent = "";
        return;
      }
      _rtTid = r.task_id;
      rtPoll();
    }).catch(function (e) {
      if (btn) btn.disabled = false;
      if (msg) msg.textContent = "✖ " + e;
    });
  }

  function rtPoll() {
    if (!_rtTid) return;
    api("task_status", { task_id: _rtTid, since: 0 }, "GET").then(function (r) {
      var msg = document.getElementById("rt-msg");
      var btn = document.getElementById("rt-btn");
      if (r.error) {
        _rtTid = null;
        if (btn) btn.disabled = false;
        if (msg) msg.textContent = "✖ " + r.error;
        return;
      }
      if (r.logs && r.logs.length && msg) msg.textContent = r.logs[r.logs.length - 1].msg || "";
      if (r.done) {
        _rtTid = null;
        if (btn) btn.disabled = false;
        if (r.error) { if (msg) msg.textContent = "✖ " + r.error; return; }
        var res = r.result || {};
        if (msg) msg.textContent = "✓ 完成：成功 " + (res.changed || 0) + " 章，" +
          "未处理 " + (res.failed || 0) + " 章（原标题保留）。";
        loadGenChapters();
        loadTimeline();
        return;
      }
      setTimeout(rtPoll, 1100);
    }).catch(function (e) {
      _rtTid = null;
      var btn = document.getElementById("rt-btn");
      if (btn) btn.disabled = false;
      var msg = document.getElementById("rt-msg");
      if (msg) msg.textContent = "✖ " + e;
    });
  }

  // ================= 码字工作台（v1.56 移植 PC gui_write） =================
  var _wSeq = null;        // 当前编辑的章号
  var _wSaved = "";        // 上次保存的正文（脏检查基线）
  var _wTitleSaved = "";   // 上次保存的标题
  var _wTid = null;        // AI 续写任务 id
  var _wTimer = null;      // 30 秒自动保存定时器

  function updateWorkCount() {
    var el = document.getElementById("w-content");
    var c = document.getElementById("w-count");
    if (el && c) c.textContent = (el.value || "").length + " 字";
  }

  function workDirty() {
    var el = document.getElementById("w-content");
    if (!el) return false;
    var t = document.getElementById("w-title");
    return el.value !== _wSaved || (t ? t.value : "") !== _wTitleSaved;
  }

  function workDirtyOk() {
    if (!workDirty()) return true;
    return confirm("当前正文有未保存的修改，切换章节会丢失这些修改。继续？");
  }

  function loadWorkList() {
    api("chapters").then(function (r) {
      var el = document.getElementById("w-chlist");
      if (!el) return;
      var list = (r && r.chapters) || [];
      el.innerHTML = "";
      if (!list.length) {
        el.innerHTML = '<div class="dim">还没有章节。点「＋ 新建下一章」开始写第一章。</div>';
        return;
      }
      list.sort(function (a, b) { return a.seq - b.seq; });
      list.forEach(function (c) {
        var row = document.createElement("div");
        row.className = "chi" + (c.seq === _wSeq ? " on" : "");
        row.innerHTML = "<div><b>第 " + c.seq + " 章 · " + esc(c.title || "") + "</b>" +
          "<div class='dim'>" + (c.chars || 0) + " 字 · 第 " + (c.vol || 1) + " 卷</div></div>";
        row.onclick = function () { workOpenChapter(c.seq); };
        el.appendChild(row);
      });
    });
  }

  function workOpenChapter(seq) {
    if (seq === _wSeq) return;
    if (!workDirtyOk()) return;
    api("chapter", { seq: seq }, "GET").then(function (r) {
      if (err(r)) return;
      _wSeq = seq;
      _wSaved = r.content || "";
      _wTitleSaved = r.title || "";
      document.getElementById("w-title").value = _wTitleSaved;
      document.getElementById("w-content").value = _wSaved;
      document.getElementById("w-msg").textContent = "";
      updateWorkCount();
      loadWorkList();
    });
  }

  function workNewChapter() {
    if (!workDirtyOk()) return;
    api("chapter_new", {}, "POST").then(function (r) {
      if (err(r)) return;
      _wSeq = r.seq;
      _wSaved = "";
      _wTitleSaved = r.title || "第" + r.seq + "章";
      document.getElementById("w-title").value = _wTitleSaved;
      document.getElementById("w-content").value = "";
      document.getElementById("w-msg").textContent = "已新建第 " + r.seq + " 章（保存后正式归档）。";
      updateWorkCount();
      loadWorkList();
      refreshState();
    });
  }

  function workSave(silent) {
    if (_wSeq === null) {
      api("chapter_new", {}, "POST").then(function (r) {
        if (err(r)) return;
        _wSeq = r.seq;
        _wSaved = "";
        workSave(silent);
      });
      return;
    }
    var text = document.getElementById("w-content").value;
    if (!text.trim()) {
      if (!silent) alert("正文不能为空。");
      return;
    }
    var title = document.getElementById("w-title").value.trim() || ("第" + _wSeq + "章");
    api("chapter_edit", { seq: _wSeq, title: title, content: text }, "POST").then(function (r) {
      if (err(r)) return;
      _wSaved = text;
      _wTitleSaved = title;
      var msg = document.getElementById("w-msg");
      if (msg) msg.textContent = (silent ? "✓ 已自动保存" : "✓ 已保存") +
        "：第 " + r.seq + " 章，" + (r.chars || 0) + " 字（旧稿已备份草稿箱）。";
      updateWorkCount();
      loadWorkList();
      refreshState();
      if (!silent) loadDrafts();
    });
  }

  function toggleWorkAutosave() {
    if (_wTimer) { clearInterval(_wTimer); _wTimer = null; }
    var chk = document.getElementById("w-autosave");
    if (chk && chk.checked) {
      _wTimer = setInterval(function () {
        var c = document.getElementById("w-autosave");
        if (c && c.checked && workDirty()) workSave(true);
      }, 30000);
    }
  }

  function workContinue() {
    if (_wTid) { alert("续写进行中，请先停止或等待完成。"); return; }
    var text = document.getElementById("w-content").value;
    if (!text.trim()) { alert("请先输入正文（续写需要前文衔接）。"); return; }
    var n = parseInt(document.getElementById("w-cont-len").value, 10) || 400;
    api("write_continue", { text: text, hint: document.getElementById("w-cont-hint").value, n: n }, "POST")
      .then(function (r) {
        if (err(r)) return;
        _wTid = r.task_id;
        document.getElementById("w-msg").textContent = "AI 续写中…（以光标后全文为前文衔接）";
        document.getElementById("w-msg").className = "dim";
        workPoll();
      }).catch(function (e) { alert("请求失败：" + e); });
  }

  function workStop() {
    if (!_wTid) { alert("当前没有正在续写的任务。"); return; }
    api("book_stop", { task_id: _wTid }, "POST").then(function (r) {
      document.getElementById("w-msg").textContent = "已请求停止…";
    }).catch(function (e) { alert("请求失败：" + e); });
  }

  function workPoll() {
    if (!_wTid) return;
    api("task_status", { task_id: _wTid, since: 0 }, "GET").then(function (r) {
      if (r.error) { _wTid = null; document.getElementById("w-msg").textContent = "✖ " + r.error; return; }
      if (r.logs && r.logs.length) {
        document.getElementById("w-msg").textContent = r.logs[r.logs.length - 1].msg || "";
      }
      if (r.done) {
        _wTid = null;
        if (r.error) { document.getElementById("w-msg").textContent = "✖ " + r.error; return; }
        var res = r.result || {};
        if (!res.text) { document.getElementById("w-msg").textContent = "✖ 模型返回为空，请重试。"; return; }
        var el = document.getElementById("w-content");
        var base = el.value.replace(/\s+$/, "");
        el.value = base + (base ? "\n\n" : "") + res.text;
        el.scrollTop = el.scrollHeight;
        updateWorkCount();
        document.getElementById("w-msg").textContent =
          "✓ 已续写 " + res.text.length + " 字并插入末尾——记得点「保存」。";
        return;
      }
      setTimeout(workPoll, 1100);
    }).catch(function (e) { _wTid = null; document.getElementById("w-msg").textContent = "✖ " + e; });
  }

  // AI 段落工具（选中文本 → 润色/扩写/缩写/去AI味 → 预览替换）
  function polishWork() {
    var el = document.getElementById("w-content");
    var s = el.selectionStart, e = el.selectionEnd;
    var sel = (s !== e) ? el.value.slice(s, e).trim() : "";
    if (!sel) { alert("请先在正文里选中要处理的一段文字。"); return; }
    modal(
      '<div class="row"><b>AI 段落工具（' + sel.length + " 字）</b></div>" +
      '<label>处理方式</label><select id="m-wp-mode">' +
      '<option value="polish">润色（保持原意，改文笔）</option>' +
      '<option value="expand">扩写（细节更饱满）</option>' +
      '<option value="shorten">缩写（更紧凑）</option>' +
      '<option value="deai">去 AI 味（改掉八股腔）</option></select>' +
      '<div class="btnrow"><button class="primary" onclick="runPolishWork()">开始处理</button>' +
      '<button onclick="closeModal()">取消</button></div>');
    window.__wpRange = [s, e];
  }

  function runPolishWork() {
    var el = document.getElementById("w-content");
    var rg = window.__wpRange || [0, 0];
    var sel = el.value.slice(rg[0], rg[1]);
    mask(true, "AI 处理中…（只改这段文字）");
    api("polish", { text: sel, mode: document.getElementById("m-wp-mode").value }, "POST")
      .then(function (r) {
        mask(false);
        if (err(r)) return;
        window.__wpText = r.text;
        modal(
          '<div class="row"><b>处理结果（可改后替换）</b></div>' +
          '<textarea id="m-wp-out" rows="10">' + esc(r.text) + '</textarea>' +
          '<div class="btnrow"><button class="primary" onclick="applyPolishWork()">替换选中段落</button>' +
          '<button onclick="closeModal()">放弃</button></div>');
      }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  function applyPolishWork() {
    var el = document.getElementById("w-content");
    var rg = window.__wpRange || [0, 0];
    var out = document.getElementById("m-wp-out").value;
    el.value = el.value.slice(0, rg[0]) + out + el.value.slice(rg[1]);
    closeModal();
    updateWorkCount();
    document.getElementById("w-msg").textContent = "已替换选中段落——记得点「保存」。";
  }

  // 码字页任务上下文三开关（与设置页 s-ctx-* 同一份配置，改动即保存）
  function loadWorkCtx() {
    api("settings_get", {}, "GET").then(function (r) {
      if (!r.ok) return;
      var a = document.getElementById("w-ctx-style");
      if (a) a.checked = r.tool_ctx_style !== false;
      var b = document.getElementById("w-ctx-notes");
      if (b) b.checked = r.tool_ctx_notes !== false;
      var c = document.getElementById("w-ctx-rp");
      if (c) c.checked = r.tool_ctx_rp !== false;
    }).catch(function () {});
  }

  function saveWorkCtx() {
    api("settings_save", {
      tool_ctx_style: !!(document.getElementById("w-ctx-style") || {}).checked,
      tool_ctx_notes: !!(document.getElementById("w-ctx-notes") || {}).checked,
      tool_ctx_rp: !!(document.getElementById("w-ctx-rp") || {}).checked
    }, "POST").then(function (r) {
      if (r && r.error) { alert(r.error); return; }
      var a = document.getElementById("s-ctx-style");
      if (a) a.checked = !!(document.getElementById("w-ctx-style") || {}).checked;
      var b = document.getElementById("s-ctx-notes");
      if (b) b.checked = !!(document.getElementById("w-ctx-notes") || {}).checked;
      var c = document.getElementById("s-ctx-rp");
      if (c) c.checked = !!(document.getElementById("w-ctx-rp") || {}).checked;
      var msg = document.getElementById("w-msg");
      if (msg) msg.textContent = "✓ 任务上下文开关已保存（续写/段落工具共用）。";
    });
  }

  function initWriteTab() {
    refreshState();
    loadDrafts();
    loadWorkList();
    loadWorkCtx();
    toggleWorkAutosave();
  }

  // ================= 角色 =================
  var AV_COLORS = ["#e8b95c", "#7fb3d9", "#6a9d7f", "#c47070", "#c9a2d9",
                   "#7d9d6a", "#e08a5c", "#5fb3a0", "#b58a3e", "#8a9ad9"];

  function avatarColor(name) {
    var h = 0;
    for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return AV_COLORS[h % AV_COLORS.length];
  }

  // v1.51 角色页视图：all=全部角色 / discard=废弃角色库（删除章节、回滚世界后移出当前剧情的角色）
  var _charView = "all";

  function setCharView(v) {
    _charView = v;
    var box = document.getElementById("char-view");
    if (box) {
      Array.prototype.forEach.call(box.querySelectorAll("button"), function (b) {
        b.classList.toggle("on", b.getAttribute("data-v") === v);
      });
    }
    renderCharacters();
  }

  function restoreChar(cid) {
    api("character_get", { cid: cid }, "GET").then(function (r) {
      if (err(r)) return;
      var c = r.card;
      c.status = "active";
      api("character_save", { card: c, lib: r.lib || {} }, "POST").then(function (r2) {
        if (err(r2)) return;
        renderCharacters();
        alert("已恢复在籍。");
      });
    });
  }

  function renderCharacters() {
    var kw = document.getElementById("ch-search").value.trim();
    api("characters").then(function (r) {
      var el = document.getElementById("char-list");
      el.innerHTML = "";
      if (!r.ok || !r.characters.length) {
        el.innerHTML = '<div class="card empty"><span class="e-ic ic-chars"></span>' +
          "还没有角色。点「＋新建」或「AI 生成角色」。</div>";
        return;
      }
      var list = r.characters.filter(function (c) {
        if (_charView === "discard" && c.status !== "discarded") return false;
        return !kw || (c.name || "").indexOf(kw) >= 0 || (c.category || "").indexOf(kw) >= 0;
      });
      if (!list.length && _charView === "discard") {
        el.innerHTML = '<div class="card empty">废弃角色库为空——删除章节或从某章重写时，' +
          "移出当前剧情的角色会出现在这里（不再直接删除）。</div>";
        return;
      }
      list.forEach(function (c) {
        var st = c.status === "active" ? "在世" : c.status === "dead" ? "阵亡" :
                 c.status === "traveling" ? "游历" :
                 c.status === "discarded" ? "已废弃" : "已归档";
        var sub = (c.category || "未分类") + " · " + st;
        if (c.status === "discarded") {
          sub += " · " + (c.dch ? "第 " + c.dch + " 章 · " : "") + (c.reason || "无原因记录");
        }
        var row = document.createElement("div");
        row.className = "char-item" + (c.status !== "active" ? " off" : "");
        row.innerHTML = '<div class="avatar" style="background:' + avatarColor(c.name) +
          '">' + esc((c.name || "?").slice(0, 1)) + "</div>" +
          '<div><b>' + esc(c.name) + "</b> <span class='dim'>" + esc(sub) + "</span></div>" +
          '<div class="acts">' +
          (c.status === "discarded" ?
            '<button class="mini" onclick="restoreChar(\'' + c.id + '\')">恢复</button>' : "") +
          '<button class="mini" onclick="openChar(\'' + c.id + '\')">编辑</button>' +
          '<button class="mini" onclick="delChar(\'' + c.id + '\',\'' + esc(c.name) + '\')">删</button></div>';
        el.appendChild(row);
      });
    });
  }

  function newCharacter() {
    var name = prompt("角色姓名（留空则随机生成）：", "");
    if (name === null) return;
    api("character_create", { name: name || "" }, "POST").then(function (r) {
      if (err(r)) return;
      renderCharacters();
      openChar(r.id);
    });
  }

  function openChar(cid) {
    api("character_get", { cid: cid }, "GET").then(function (r) {
      if (err(r)) return;
      var c = r.card, l = r.lib || {};
      modal(
        '<div class="row"><b>编辑角色 · ' + esc(c.name) + '</b></div>' +
        field("name", "姓名", c.name) +
        field("role", "身份/职业", c.role) +
        '<label>状态</label><select id="m-status">' +
        '<option' + (c.status === "active" ? " selected" : "") + ' value="active">在世</option>' +
        '<option' + (c.status === "dead" ? " selected" : "") + ' value="dead">阵亡</option>' +
        '<option' + (c.status === "traveling" ? " selected" : "") + ' value="traveling">游历</option>' +
        '<option' + (c.status === "archived" ? " selected" : "") + ' value="archived">已归档</option>' +
        '<option' + (c.status === "discarded" ? " selected" : "") + ' value="discarded">已废弃</option></select>' +
        field("category", "分类（主要角色/配角/NPC…）", c.category) +
        field("description", "综合描述（外貌+性格+背景+言行）", c.description) +
        '<details><summary>高级设定</summary>' +
        field("personality", "性格", c.personality) +
        field("values", "价值观与底线", c.values) +
        field("goals", "目标与欲望", c.goals) +
        field("fears", "恐惧与弱点", c.fears) +
        field("speech_style", "说话风格", c.speech_style) +
        field("backstory", "背景故事", c.backstory) +
        field("relationships", "与其他角色的关系", c.relationships) +
        field("appearance", "外貌", c.appearance) +
        '</details>' +
        '<details><summary>信息库（外在信息）</summary>' +
        field("lib-scenario", "当前场景/处境", l.scenario) +
        field("lib-notes", "备注", l.notes) +
        field("lib-secrets", "隐秘（每行一条）", (l.secrets || []).join("\n")) +
        '</details>' +
        '<div class="btnrow"><button class="primary" onclick="saveChar(\'' + c.id + '\')">保存</button>' +
        '<button onclick="closeModal()">取消</button></div>');
    });
  }

  function field(id, label, val) {
    return '<label>' + label + '</label><textarea id="m-' + id + '" rows="2">' +
      esc(val || "") + "</textarea>";
  }

  function gv(id) { var el = document.getElementById("m-" + id); return el ? el.value : ""; }

  function saveChar(cid) {
    var card = {
      id: cid, name: gv("name"), role: gv("role"),
      status: document.getElementById("m-status").value,
      category: gv("category"), description: gv("description"),
      personality: gv("personality"), values: gv("values"), goals: gv("goals"),
      fears: gv("fears"), speech_style: gv("speech_style"),
      backstory: gv("backstory"), relationships: gv("relationships"),
      appearance: gv("appearance")
    };
    var lib = {
      scenario: gv("lib-scenario"), notes: gv("lib-notes"),
      secrets: gv("lib-secrets").split("\n").map(function (s) { return s.trim(); }).filter(Boolean)
    };
    mask(true, "保存中…");
    api("character_save", { card: card, lib: lib }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      closeModal(); renderCharacters();
    }).catch(function (e) { mask(false); alert(e); });
  }

  function delChar(cid, name) {
    if (!confirm("确定删除角色「" + name + "」？其信息库也会一并删除。")) return;
    api("character_delete", { cid: cid }, "POST").then(function (r) {
      if (err(r)) return;
      renderCharacters();
    });
  }

  function aiCharacter() {
    var desc = prompt("描述想要的角色（自然语言即可）：\n如：冷面女剑客，沉默寡言，背负灭门之仇");
    if (!desc) return;
    mask(true, "AI 生成角色中…");
    api("character_ai", { desc: desc }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      renderCharacters();
      alert("已生成角色卡：" + r.name + "（" + (r.role || "未定义身份") + "）");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function aiCharacterBatch() {
    var desc = prompt("描述需要的一批角色（数量与分工由 AI 自行拆解）：\n如：主角的师兄师姐、反派势力三名长老");
    if (!desc) return;
    mask(true, "AI 批量生成中…");
    api("character_ai_batch", { desc: desc }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      renderCharacters();
      alert("已创建 " + r.created.length + " 张角色卡。");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function aiClassify() {
    mask(true, "AI 自动分类中…");
    api("classify", {}, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      renderCharacters();
      alert("分类完成。");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function openImportDialog() {
    modal(
      '<div class="row"><b>导入角色卡（酒馆 chara_card_v2 JSON）</b></div>' +
      '<label>粘贴 JSON 文本</label><textarea id="m-import-json" rows="8" placeholder="{&#34;data&#34;:{&#34;name&#34;:&#34;…&#34;,&#34;description&#34;:&#34;…&#34;}}"></textarea>' +
      '<div class="btnrow"><button class="primary" onclick="doImportChar()">导入</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function doImportChar() {
    var t = document.getElementById("m-import-json").value;
    if (!t.trim()) return;
    mask(true, "导入中…");
    api("character_import", { json_text: t }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      closeModal(); renderCharacters();
      alert("已导入：" + r.name);
    }).catch(function (e) { mask(false); alert(e); });
  }

  function batchStatus() {
    api("characters").then(function (r) {
      if (!r.ok) return;
      var html = '<div class="row"><b>批量改状态</b></div>';
      r.characters.forEach(function (c) {
        html += '<label class="chk"><input type="checkbox" class="batch-cb" value="' + c.id + '"> ' +
          esc(c.name) + '</label>';
      });
      html += '<label>设为</label><select id="m-bstatus">' +
        '<option value="active">在世</option><option value="dead">阵亡</option>' +
        '<option value="traveling">游历</option><option value="archived">已归档</option>' +
        '<option value="discarded">已废弃</option></select>' +
        '<div class="btnrow"><button class="primary" onclick="doBatchStatus()">应用</button>' +
        '<button onclick="closeModal()">取消</button></div>';
      modal(html);
    });
  }

  function doBatchStatus() {
    var cids = Array.prototype.map.call(document.querySelectorAll(".batch-cb:checked"),
      function (b) { return b.value; });
    if (!cids.length) { alert("请先勾选角色。"); return; }
    api("character_batch", { cids: cids, status: document.getElementById("m-bstatus").value }, "POST")
      .then(function (r) {
        if (err(r)) return;
        closeModal(); renderCharacters();
        alert("已更新 " + r.count + " 名角色。");
      });
  }

  // ================= 档案 / 项目 / 情景卡：中功能页签（v1.56 对齐电脑端 QTabWidget 那层） =================
  // 结构：左侧大页 → 顶部中功能页签 → 子页面。中页签条是 .subtabs（sticky 常驻），
  // 按钮用 data-sub 标记，面板是 #sub-<name>。避免按按钮下标匹配（改顺序就错位）。
  var SUBTABS = {
    project: ["p-story", "p-style", "p-proof", "p-lore", "p-new", "p-book", "p-import"],
    archive: ["timeline", "fore", "note", "knowledge", "log", "branch", "stats"],
    scenecards: ["sc-lib", "sc-card", "sc-io", "sc-prompt", "sc-proj"]
  };
  var _subName = { project: "p-story", archive: "timeline", scenecards: "sc-lib" };

  function subTab(page, name) {
    var list = SUBTABS[page] || [];
    if (list.indexOf(name) < 0) name = list[0];
    _subName[page] = name;
    list.forEach(function (t) {
      var el = document.getElementById("sub-" + t);
      if (el) el.classList.toggle("hidden", t !== name);
    });
    document.querySelectorAll('.subtabs[data-page="' + page + '"] button').forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-sub") === name);
    });
    var main = document.querySelector("main");
    if (main) main.scrollTop = 0;
    if (page === "archive") subLoadArchive(name);
    else if (page === "project") subLoadProject(name);
    else if (page === "scenecards") subLoadScene(name);
  }

  function subLoadArchive(name) {
    if (name === "timeline") loadTimeline();
    else if (name === "fore") loadFore();
    else if (name === "note") loadNote();
    else if (name === "knowledge") loadKnowledge();
    else if (name === "log") loadLog();
    else if (name === "branch") loadBranches();
    else if (name === "stats") loadStats();
  }

  function subLoadProject(name) {
    if (name === "p-story" || name === "p-style") loadProjectForm();
    else if (name === "p-proof") loadProofreadForm();
    else if (name === "p-lore") loadLore();
    else if (name === "p-book") { loadBreakStyleOptions(); loadBookSceneList(); bookAutoToggle(); }
  }

  function subLoadScene(name) {
    if (name === "sc-lib" || name === "sc-card" || name === "sc-io") loadSceneCards();
    else if (name === "sc-prompt") loadScenePrompt();
    else if (name === "sc-proj") loadProjectSceneCards();
  }

  // 兼容旧调用（档案页原 switchSub('timeline') 语义）
  function switchSub(name) { subTab("archive", name); }

  // ================= 档案 =================

  // v0.20 写作统计仪表盘（总字数/各卷分布/进度）
  function loadStats() {
    api("stats").then(function (r) {
      var el = document.getElementById("stats-card");
      if (!r.ok || !r.stats) {
        el.innerHTML = '<div class="dim">还没有统计（先载入项目并写作）。</div>';
        return;
      }
      var s = r.stats;
      var h = '<div class="row"><b>写作统计</b></div>' +
        "<div style='font-size:30px;color:#e8c87a;font-weight:700'>" + (s.total_chars || 0).toLocaleString() + " 字</div>" +
        "<div class='dim'>共 " + (s.chapters || 0) + " 章" +
        (s.target ? " · 当前卷目标 " + s.target + " 章" : "") + "</div>";
      if (s.progress != null) {
        h += '<div class="bar"><div style="width:' + Math.round(s.progress) + '%"></div></div>' +
          '<div class="dim">当前卷进度 ' + s.progress.toFixed(1) + "%</div>";
      }
      if (s.volume_chars && s.volume_chars.length) {
        h += "<div class='dim' style='margin-top:8px'>各卷分布</div>";
        s.volume_chars.forEach(function (v) {
          h += '<div class="volrow"><span>第 ' + v.vol + " 卷</span><span>" + v.count +
            " 章</span><span>" + v.chars.toLocaleString() + " 字</span></div>";
        });
      }
      el.innerHTML = h;
    });
  }

  // v0.20 全文搜索（标题/梗概/正文），结果点击打开章节
  function searchChapters(kw) {
    if (kw === "") {
      document.getElementById("search-result").classList.add("hidden");
      document.getElementById("search-result").innerHTML = "";
      loadTimeline();
      return;
    }
    kw = typeof kw === "string" && kw !== "" ? kw : document.getElementById("ch-search-full").value;
    if (!kw || !kw.trim()) { alert("请输入关键词。"); return; }
    api("search", { kw: kw.trim() }, "GET").then(function (r) {
      if (err(r)) return;
      var el = document.getElementById("search-result");
      el.classList.remove("hidden");
      var res = r.results || [];
      if (!res.length) {
        el.innerHTML = '<div class="dim">未找到包含「' + esc(kw.trim()) + "」的章节。</div>";
        return;
      }
      var h = '<div class="dim">找到 ' + res.length + " 条结果（点结果阅读章节）</div>";
      res.forEach(function (x) {
        h += '<div class="chi" onclick="openChapter(' + x.seq + ')"><b>第 ' + x.seq + " 章 · " +
          esc(x.title) + "</b><div class='dim'>" + esc(x.snippet || "") + "</div></div>";
      });
      el.innerHTML = h;
      el.scrollIntoView({ block: "start" });
    });
  }

  // v0.20 交换两章内容（排序调整；旧版自动备份草稿箱）
  function swapChapter() {
    if (!_curChSeq) return;
    var target = prompt("把「第 " + _curChSeq + " 章」与哪一章交换？（交换=两章标题/正文/出场角色/卷互换，章号不变；旧版备份草稿箱）", "");
    if (target === null) return;
    var b = parseInt(target, 10);
    if (!b || b < 1 || b === _curChSeq) { alert("章号需为正整数且与当前章不同。"); return; }
    if (!confirm("确定交换第 " + _curChSeq + " 章与第 " + b + " 章的内容吗？")) return;
    api("swap", { a: _curChSeq, b: b }, "POST").then(function (r) {
      if (err(r)) return;
      alert("已交换（旧版备份在草稿箱）。");
      _curChSeq = null;
      loadTimeline();
    });
  }

  // v0.20 重写此章：回滚世界状态到该章前，删除该章及之后章节（与 PC 端一致）
  function rewriteChapter() {
    if (!_curChSeq) return;
    var seq = _curChSeq;
    if (!confirm("【重写此章】将回滚世界状态（角色卡/信息库/伏笔/管理笔记）到第 " + seq +
      " 章开始前，删除第 " + seq + " 章及之后全部章节，进度回退到该章。\n\n" +
      "被删章节会自动备份到草稿箱（可找回）。确定继续吗？")) return;
    api("rewrite", { seq: seq }, "POST").then(function (r) {
      if (err(r)) return;
      alert("已回滚世界状态并删除第 " + seq + " 章及之后章节，可从第 " + seq + " 章重新生成。");
      _curChSeq = null;
      loadTimeline();
      refreshState();
    });
  }

  // v0.20 分卷管理：卷分布一览 + 整卷合并
  function openVolManage() {
    api("timeline").then(function (r) {
      var groups = {};
      (r.timeline || []).forEach(function (c) {
        var v = c.vol || 1;
        groups[v] = (groups[v] || 0) + 1;
      });
      var rows = Object.keys(groups).map(Number).sort(function (a, b) { return a - b; });
      var h = '<div class="row"><b>分卷管理</b></div><div class="dim">' +
        Object.keys(groups).length + " 卷 · 点击「整卷合并」把某卷全部章节并入另一卷（删除空卷）</div>";
      rows.forEach(function (v) {
        h += '<div class="volrow"><span>第 ' + v + " 卷</span><span>" + groups[v] + " 章</span></div>";
      });
      h += '<label>把第</label><input id="m-vol-old" type="number" min="1" value="1" style="width:70px">' +
        '<label>卷并入第</label><input id="m-vol-new" type="number" min="1" value="1" style="width:70px">' +
        '<label>卷</label>' +
        '<div class="btnrow"><button class="primary" onclick="saveVolMerge()">整卷合并</button>' +
        '<button onclick="closeModal()">关闭</button></div>';
      modal(h);
    });
  }
  function saveVolMerge() {
    var oldVol = parseInt(document.getElementById("m-vol-old").value, 10);
    var newVol = parseInt(document.getElementById("m-vol-new").value, 10);
    if (!oldVol || !newVol || oldVol === newVol) { alert("卷号非法（需为正整数且不同）。"); return; }
    if (!confirm("把第 " + oldVol + " 卷的全部章节并入第 " + newVol + " 卷吗？")) return;
    api("volume_merge", { old_vol: oldVol, new_vol: newVol }, "POST").then(function (r) {
      if (err(r)) return;
      alert("已把第 " + oldVol + " 卷 " + r.moved + " 章并入第 " + newVol + " 卷。");
      closeModal();
      _curChSeq = null;
      loadTimeline();
    });
  }

  // v0.20 AI 段落工具：选中文本 → 润色/扩写/缩写/去AI味 → 替换
  var _polishSrcEl = null;
  function polishInput() {
    var el = document.activeElement;
    if (!el || (el.tagName !== "TEXTAREA" && el.tagName !== "INPUT")) {
      el = document.getElementById("out-content");
    }
    var text = window.getSelection().toString();
    if (!text || !text.trim()) {
      text = (el.value || "").substring(el.selectionStart || 0, el.selectionEnd || 0).trim();
    }
    if (!text) {
      alert("请先在文本框中选中要处理的一段文字（光标所在输入框）。");
      return;
    }
    if (text.length > 6000) { alert("选中文本过长（最多 6000 字），请分段处理。"); return; }
    _polishSrcEl = el;
    modal(
      '<div class="row"><b>AI 段落工具</b><span class="dim">' + text.length + " 字</span></div>" +
      '<label>处理方式</label><select id="m-polish-mode">' +
      '<option value="polish">文笔润色</option><option value="expand">扩写补足</option>' +
      '<option value="shorten">精简浓缩</option><option value="deai">去AI味</option></select>' +
      '<label>原文</label><textarea id="m-polish-orig" rows="5" readonly>' + esc(text) + "</textarea>" +
      '<label>处理结果</label><textarea id="m-polish-res" rows="8" placeholder="点「开始处理」后显示…"></textarea>' +
      '<div class="btnrow"><button class="primary" id="m-polish-run" onclick="runPolish(\'' +
      esc(text).replace(/'/g, "\\'") + '\')"><span class="ic ic-magic"></span>开始处理</button>' +
      '<button onclick="replacePolish()">替换选中文本</button>' +
      '<button onclick="closeModal()">关闭</button></div>');
  }
  function runPolish(text) {
    var mode = document.getElementById("m-polish-mode").value;
    var btn = document.getElementById("m-polish-run");
    btn.disabled = true;
    btn.textContent = "处理中…";
    api("polish", { text: text, mode: mode }, "POST").then(function (r) {
      btn.disabled = false;
      btn.innerHTML = '<span class="ic ic-magic"></span>开始处理';
      if (err(r)) return;
      document.getElementById("m-polish-res").value = r.text || "";
    }).catch(function (e) { btn.disabled = false; alert("请求失败：" + e); });
  }
  function replacePolish() {
    var res = document.getElementById("m-polish-res").value.trim();
    if (!res) { alert("没有可替换的处理结果。"); return; }
    var el = _polishSrcEl || document.getElementById("out-content");
    var start = el.selectionStart != null ? el.selectionStart : el.value.length;
    var end = el.selectionEnd != null ? el.selectionEnd : start;
    closeModal();
    el.value = el.value.slice(0, start) + res + el.value.slice(end);
    try { el.selectionStart = el.selectionEnd = start + res.length; } catch (e2) {}
    el.focus();
    alert("已替换（" + res.length + " 字）。");
  }

  function loadKnowledge() {
    api("knowledge").then(function (r) {
      document.getElementById("kb-text").textContent = r.knowledge || "（知识库为空——主AI会把联网搜索灵感、重要设定确认、关键伏笔落定等值得长期记住的内容记在这里。）";
    });
  }

  function loadLog() {
    api("logs").then(function (r) {
      document.getElementById("log-text").textContent = r.logs || "（还没有生成日志。）";
    });
  }

  // ================= 分支存档（v1.56 复刻 PC 故事档案·分支存档） =================
  function loadBranches() {
    api("branch_list", {}, "GET").then(function (r) {
      var el = document.getElementById("branch-list");
      if (!el) return;
      var list = (r && r.branches) || [];
      var msg = document.getElementById("br-msg");
      if (msg) msg.textContent = list.length ? "共 " + list.length + " 个存档点。" : "";
      el.innerHTML = "";
      if (!list.length) {
        el.innerHTML = '<div class="dim">还没有分支存档。写出几章后，想试不同剧情走向时先存一个。</div>';
        return;
      }
      list.forEach(function (b) {
        var row = document.createElement("div");
        row.className = "char-item";
        row.innerHTML = "<div><b>" + esc(b.name) + "</b>" +
          "<div class='dim'>" + esc(b.saved_at || "") + " · 进度 " + (b.chapters || 0) +
          " 章</div></div>" +
          '<div><button class="mini" onclick="loadBranch(\'' + esc(b.name) + '\')">载入</button>' +
          '<button class="mini" style="color:var(--red)" onclick="delBranch(\'' +
          esc(b.name) + '\')">删</button></div>';
        el.appendChild(row);
      });
    }).catch(function (e) {
      var msg = document.getElementById("br-msg");
      if (msg) msg.textContent = "✖ " + e;
    });
  }

  function saveBranch() {
    var el = document.getElementById("br-name");
    var name = (el.value || "").trim();
    if (!name) { alert("请先填存档名（如：主角拜师前）。"); return; }
    var msg = document.getElementById("br-msg");
    if (msg) msg.textContent = "存档中…";
    api("branch_save", { name: name }, "POST").then(function (r) {
      if (err(r)) { if (msg) msg.textContent = ""; return; }
      if (msg) msg.textContent = "✓ 已存为分支《" + name + "》。";
      el.value = "";
      loadBranches();
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  }

  function loadBranch(name) {
    if (!confirm("载入分支《" + name + "》？\n当前项目会被整体替换回那个存档点"
        + "（设定/进度/角色/章节/伏笔全部回退）。")) return;
    var msg = document.getElementById("br-msg");
    mask(true, "载入分支中…");
    api("branch_load", { name: name }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      if (msg) msg.textContent = "✓ 已载入《" + name + "》。";
      refreshState(); loadTimeline(); loadDrafts(); loadChapters(); loadProjectForm();
    }).catch(function (e) { mask(false); if (msg) msg.textContent = "✖ " + e; });
  }

  function delBranch(name) {
    if (!confirm("删除分支《" + name + "》？只删这个存档点，不影响当前项目。")) return;
    api("branch_delete", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      loadBranches();
    });
  }

  // v0.19 编辑已归档章节（原版自动备份到草稿箱）
  function editChapter() {
    if (!_curChSeq) return;
    api("chapter", { seq: _curChSeq }, "GET").then(function (r) {
      if (err(r)) return;
      modal(
        '<div class="row"><b>编辑已归档章节 · 第 ' + _curChSeq + ' 章</b></div>' +
        '<label>章节标题</label><input id="m-edit-title" value="' + esc(r.title || "") + '">' +
        '<label>正文（原版会自动备份到草稿箱）</label>' +
        '<textarea id="m-edit-content" rows="12">' + esc(r.content || "") + '</textarea>' +
        '<div class="btnrow"><button class="primary" onclick="saveChapterEdit()"><span class="ic ic-check"></span>保存修改</button>' +
        '<button onclick="closeModal()">取消</button></div>');
    });
  }
  function saveChapterEdit() {
    var title = document.getElementById("m-edit-title").value;
    var content = document.getElementById("m-edit-content").value;
    api("chapter_edit", { seq: _curChSeq, title: title, content: content }, "POST").then(function (r) {
      if (err(r)) return;
      closeModal();
      loadTimeline();
      openChapter(_curChSeq);
      alert("已保存（原版备份到草稿箱）。");
    });
  }

  function loadTimeline() {
    api("timeline").then(function (r) {
      var el = document.getElementById("timeline-list");
      el.innerHTML = "";
      if (!r.ok || !r.timeline.length) {
        el.innerHTML = '<div class="empty"><span class="e-ic ic-archive"></span>还没有已写章节。<br>去「写作」页生成第一章吧。</div>';
        return;
      }
      // v0.17 分卷：按卷分组显示（卷降序=最新卷在前，卷内章节倒序=最新在前）
      var groups = {};
      r.timeline.forEach(function (c) {
        var v = c.vol || 1;
        (groups[v] = groups[v] || []).push(c);
      });
      var vols = Object.keys(groups).map(Number).sort(function (a, b) { return b - a; });
      vols.forEach(function (v) {
        var head = document.createElement("div");
        head.className = "vol-head";
        head.textContent = "第 " + v + " 卷 · " + groups[v].length + " 章";
        el.appendChild(head);
        groups[v].slice().reverse().forEach(function (c) {
          var d = document.createElement("div");
          d.className = "chi";
          var marks = "";
          (c.foreshadows || []).forEach(function (f) {
            var t = typeof f === "string" ? f : (f && f.text || "");
            var done = typeof f === "object" && f && f.f_type === "payoff";
            if (t) {
              marks += '<span class="tag ' + (done ? "done" : "open") + '">' + esc(t) + "</span>";
            }
          });
          var st = c.status === "approved" ? "已定稿" : "草稿";
          d.innerHTML = "<div><b>第 " + c.seq + " 章 · " + esc(c.title || "") + "</b>" +
            "<div class='dim'>" + marks + "</div>" +
            '<div class="dim">' + esc(c.brief || "") + "</div></div>" +
            '<div class="dim">第' + (c.vol || 1) + "卷 · " + st + " · " + c.chars + "字</div>";
          d.onclick = function () { openChapter(c.seq); };
          el.appendChild(d);
        });
      });
    });
  }

  var _curChSeq = null;
  function openChapter(seq) {
    _curChSeq = seq;
    api("chapter", { seq: seq }, "GET").then(function (r) {
      if (err(r)) return;
      var d = document.getElementById("ch-detail");
      d.classList.remove("hidden");
      document.getElementById("chd-title").textContent = "第 " + seq + " 章 · " + r.title;
      document.getElementById("chd-vol").textContent = "第 " + (r.volume || 1) + " 卷";
      document.getElementById("chd-vol-in").value = r.volume || 1;
      document.getElementById("chd-meta").innerHTML =
        metaHtml(r.review, r.beats, r.intent, r.deai) + (r.foreshadows && r.foreshadows.length ?
          "<br>本章伏笔：" + r.foreshadows.map(esc).join("；") : "");
      document.getElementById("chd-content").textContent = r.content || "";
      document.getElementById("chd-content").scrollTop = 0;
    });
  }

  // v0.17 分卷：本章归入新卷
  function setChapterVol() {
    if (!_curChSeq) return;
    var v = parseInt(document.getElementById("chd-vol-in").value, 10);
    if (!v || v < 1) { alert("卷号需为正整数"); return; }
    api("volume_set", { seq: _curChSeq, vol: v }, "POST").then(function (r) {
      if (err(r)) return;
      document.getElementById("chd-vol").textContent = "第 " + v + " 卷";
      loadTimeline();
    });
  }

  function loadFore() {
    api("foreshadows").then(function (r) {
      if (!r.ok) return;
      var s = r.stats || {};
      document.getElementById("fore-stats").textContent =
        "伏笔统计：待回收 " + s.open + " · 已回收 " + s.resolved + " · ⚠逾期 " + s.overdue +
        "（阈值 " + r.threshold + " 章）　" + "回收率 " +
        (s.open + s.resolved ? Math.round(s.resolved * 100 / (s.open + s.resolved)) : 0) + "%";
      var el = document.getElementById("fore-list");
      el.innerHTML = "";
      if (!r.foreshadows.length) {
        el.innerHTML = '<div class="dim">还没有伏笔。生成章节时主AI会自动埋设/回收。</div>';
        return;
      }
      var sel = [];
      r.foreshadows.forEach(function (f) {
        var tag = f.overdue ? "over" : (f.status === "resolved" ? "done" : "open");
        var tname = f.overdue ? "⚠逾期" : (f.status === "resolved" ? "已回收" : "待回收");
        var row = document.createElement("div");
        row.className = "fore-item";
        row.innerHTML = '<label class="chk"><input type="checkbox" class="fore-cb" value="' + f.id + '">' +
          '<span><span class="tag ' + tag + '">' + tname + "</span>" + esc(f.text) +
          "<br><span class='dim'>埋设于第 " + f.planted_chapter + " 章" +
          (f.resolved_chapter ? " · 回收于第 " + f.resolved_chapter + " 章" : "") +
          " · 类型 " + esc(f.f_type) + "</span></span></label>";
        el.appendChild(row);
        sel.push(f);
      });
      var bar = document.createElement("div");
      bar.className = "btnrow";
      bar.innerHTML = '<button class="primary" onclick="foreMark(\'resolved\')">标记回收选中</button>' +
        '<button onclick="foreMark(\'open\')">恢复待回收</button>';
      el.appendChild(bar);
    });
  }

  function foreMark(status) {
    var ids = Array.prototype.map.call(document.querySelectorAll(".fore-cb:checked"),
      function (b) { return b.value; });
    if (!ids.length) { alert("请先勾选伏笔。"); return; }
    api("fore_mark", { ids: ids, status: status }, "POST").then(function (r) {
      if (err(r)) return;
      loadFore();
    });
  }

  function loadNote() {
    api("note_get").then(function (r) {
      document.getElementById("note-text").textContent =
        r.ok && r.note ? r.note : "（暂无管理笔记。主AI每若干章自动压缩剧情形成，可在生成日志中查看。）";
    });
  }

  // v0.12 沉浸阅读：字号 A-/A+
  var _readFont = 17;
  function readFont(delta) {
    _readFont = Math.max(15, Math.min(25, _readFont + delta));
    document.getElementById("chd-content").style.fontSize = _readFont + "px";
    document.getElementById("read-size").textContent = _readFont + "px";
  }

  // ================= 项目 =================
  function loadProjectForm() {
    api("state").then(function (s) {
      if (!s.ok || !s.project) return;
      var p = s.project;
      document.getElementById("p-name").value = p.title;
      document.getElementById("p-brief").value = p.brief;
      document.getElementById("p-world").value = p.world_view;
      document.getElementById("p-rules").value = p.special_rules;
      document.getElementById("p-style").value = p.style;
      document.getElementById("p-style-ref").value = p.style_ref;
      document.getElementById("p-style-note").value = p.style_note;
      document.getElementById("p-writer-prompt").value = p.writer_prompt;
      document.getElementById("p-main-prompt").value = p.main_prompt;
      document.getElementById("p-title-rules").value = p.title_rules || DEFAULT_TITLE_RULES;
      document.getElementById("rt-title-rules").value = p.title_rules || DEFAULT_TITLE_RULES;
    });
  }

  function saveProject() {
    mask(true, "保存中…");
    var payload = {
      name: document.getElementById("p-name").value,
      brief: document.getElementById("p-brief").value,
      world_view: document.getElementById("p-world").value,
      special_rules: document.getElementById("p-rules").value,
      style: document.getElementById("p-style").value,
      style_ref: document.getElementById("p-style-ref").value,
      style_note: document.getElementById("p-style-note").value,
      writer_prompt: document.getElementById("p-writer-prompt").value,
      main_prompt: document.getElementById("p-main-prompt").value,
      title_rules: document.getElementById("p-title-rules").value
    };
    // v0.16 多项目：有当前项目=更新（project_save），无当前项目=新建（project_create）
    api("projects").then(function (pr) {
      var cur = (pr.projects || []).filter(function (p) { return p.current; })[0];
      var path = cur ? "project_save" : "project_create";
      return api(path, payload, "POST");
    }).then(function (r) {
      mask(false);
      var ok = r.ok ? "✓ 已保存：" + (r.name || payload.name) : "✖ " + r.error;
      // 故事设定页与文风参考页各有一个保存按钮：两个页签的提示都写，避免看不到反馈
      var m1 = document.getElementById("p-save-msg");
      if (m1) m1.textContent = ok;
      var m2 = document.getElementById("p-style-msg");
      if (m2) m2.textContent = ok;
      refreshState(); renderProjects();
    }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  // project_save 是「全量覆盖」语义（后端把没带的字段写成空串）：改局部字段时先把
  // 当前项目全部设定读回来做底，只覆盖 patch 里的键——否则会误清空别的设定。
  function saveProjectFields(patch) {
    return api("state").then(function (s) {
      var p = (s && s.project) || {};
      var d = {
        name: p.title || "", brief: p.brief || "", world_view: p.world_view || "",
        special_rules: p.special_rules || "", style: p.style || "",
        style_note: p.style_note || "", style_ref: p.style_ref || "",
        tech_source: p.tech_source || "", techniques: p.techniques || "",
        writer_prompt: p.writer_prompt || "", main_prompt: p.main_prompt || "",
        break_style: p.break_style || ""
      };
      Object.keys(patch || {}).forEach(function (k) { d[k] = patch[k]; });
      return api("project_save", d, "POST");
    });
  }

  // AI 辅助起草故事设定（PC 项目页「AI 生成所选」）
  function planStoryAI() {
    var idea = (document.getElementById("ps-idea").value || "").trim();
    if (!idea) { alert("请先描述你想写什么小说。"); return; }
    var targets = [];
    if (document.getElementById("ps-story").checked) targets.push("story");
    if (document.getElementById("ps-world").checked) targets.push("world");
    if (document.getElementById("ps-rules").checked) targets.push("rules");
    if (!targets.length) { alert("请至少勾选一栏要生成的内容。"); return; }
    var notes = "【故事简介】\n" + document.getElementById("p-brief").value +
      "\n\n【世界观】\n" + document.getElementById("p-world").value +
      "\n\n【特殊规则】\n" + document.getElementById("p-rules").value;
    var msg = document.getElementById("ps-msg");
    msg.textContent = "AI 起草中…（已填内容作为续写基础）";
    document.getElementById("ps-ai-btn").disabled = true;
    api("plan_story", {
      idea: idea,
      notes: notes,
      constraint: document.getElementById("ps-constraint").value,
      targets: targets
    }, "POST").then(function (r) {
      mask(false);
      document.getElementById("ps-ai-btn").disabled = false;
      if (err(r)) { msg.textContent = ""; return; }
      if (targets.indexOf("story") >= 0 && r.story) document.getElementById("p-brief").value = r.story;
      if (targets.indexOf("world") >= 0 && r.world) document.getElementById("p-world").value = r.world;
      if (targets.indexOf("rules") >= 0 && r.rules) document.getElementById("p-rules").value = r.rules;
      msg.textContent = "✓ 已起草并填入上面三栏——确认无误后点「保存故事设定」。";
    }).catch(function (e) {
      document.getElementById("ps-ai-btn").disabled = false;
      msg.textContent = "✖ " + e;
    });
  }

  // 新建项目（直接创建 / AI 生成并创建）
  function newProjectDirect() {
    var name = (document.getElementById("np-name").value || "").trim();
    if (!name) { alert("请先填书名。"); return; }
    var msg = document.getElementById("np-msg");
    mask(true, "创建项目中…");
    api("project_create", {
      name: name, brief: document.getElementById("np-brief").value
    }, "POST").then(function (r) {
      mask(false);
      if (err(r)) { msg.textContent = ""; return; }
      msg.textContent = "✓ 已创建《" + name + "》，现在是当前项目（书架可见）。";
      document.getElementById("np-name").value = "";
      document.getElementById("np-brief").value = "";
      refreshState(); renderProjects(); loadProjectForm();
    }).catch(function (e) { mask(false); msg.textContent = "✖ " + e; });
  }

  function newProjectAI() {
    var idea = (document.getElementById("np-idea").value || "").trim();
    if (!idea) { alert("请先描述你想写什么小说。"); return; }
    var msg = document.getElementById("np-ai-msg");
    mask(true, "AI 起名并起草故事设定中…");
    api("plan_story", {
      idea: idea,
      constraint: document.getElementById("np-constraint").value,
      targets: ["story", "world", "rules"]
    }, "POST").then(function (r) {
      if (err(r)) { mask(false); msg.textContent = ""; return; }
      // 书名直接用「想法首句」：这里不做 AI 起名（那是「一键成书」立项环节的活儿），
      // 建好后书名可在「故事设定」里改。
      var guess = idea.split(/[。！？\n，,]/)[0].slice(0, 14) || "我的故事";
      return api("project_create", {
        name: guess, brief: r.story || "", world_view: r.world || "",
        special_rules: r.rules || ""
      }, "POST").then(function (r2) {
        mask(false);
        if (err(r2)) { msg.textContent = ""; return; }
        msg.textContent = "✓ 已创建《" + guess + "》并填入 AI 起草的剧情/世界观/规则（书名可到「故事设定」改）。";
        document.getElementById("np-idea").value = "";
        document.getElementById("np-constraint").value = "";
        refreshState(); renderProjects(); loadProjectForm();
      });
    }).catch(function (e) {
      mask(false);
      msg.textContent = "✖ " + e;
    });
  }

  // 写后校对（PC 项目页「写后校对」页签：开关 + 规则；与设置页同一份配置）
  function loadProofreadForm() {
    api("settings_get", {}, "GET").then(function (r) {
      if (!r.ok) return;
      var a = document.getElementById("p-proofread");
      if (a) a.checked = r.proofread_enabled !== false;
      var b = document.getElementById("p-proofread-rules");
      if (b) b.value = r.proofread_rules || "";
    }).catch(function () {});
  }

  function saveProofread() {
    var on = document.getElementById("p-proofread").checked;
    var rules = document.getElementById("p-proofread-rules").value;
    var msg = document.getElementById("p-proof-msg");
    api("settings_save", { proofread_enabled: on, proofread_rules: rules }, "POST")
      .then(function (r) {
        if (err(r)) { msg.textContent = ""; return; }
        var s = document.getElementById("s-proofread");
        if (s) s.checked = on;
        var sr = document.getElementById("s-proofread-rules");
        if (sr) sr.value = rules;
        msg.textContent = "✓ 已保存：写后校对" + (on ? "已启用" : "已关闭") +
          "，规则 " + rules.length + " 字" + (rules ? "" : "（留空 = 内置默认）") + "。";
      }).catch(function (e) { msg.textContent = "✖ " + e; });
  }

  // 主AI按本文风适配本项目的情景卡（任务化，可停止）
  var _scAdaptTid = null;
  function adaptSceneCards() {
    if (_scAdaptTid) { alert("适配进行中，请先停止或等待完成。"); return; }
    if (!confirm("让主AI把「本项目库」的情景卡写法调整到契合本文风？\n（只改本项目库，不动总库；卡的情景内核/卡名/分类不变）")) return;
    var msg = document.getElementById("p-sc-msg");
    msg.textContent = "主AI适配中…";
    document.getElementById("p-sc-adapt").disabled = true;
    api("scene_cards_adapt", {}, "POST").then(function (r) {
      if (err(r)) {
        document.getElementById("p-sc-adapt").disabled = false;
        msg.textContent = "";
        return;
      }
      _scAdaptTid = r.task_id;
      scAdaptPoll();
    }).catch(function (e) {
      document.getElementById("p-sc-adapt").disabled = false;
      msg.textContent = "✖ " + e;
    });
  }

  function scAdaptPoll() {
    if (!_scAdaptTid) return;
    api("task_status", { task_id: _scAdaptTid, since: 0 }, "GET").then(function (r) {
      var msg = document.getElementById("p-sc-msg");
      if (r.error) {
        _scAdaptTid = null;
        document.getElementById("p-sc-adapt").disabled = false;
        msg.textContent = "✖ " + r.error;
        return;
      }
      if (r.logs && r.logs.length) msg.textContent = r.logs[r.logs.length - 1].msg || "";
      if (r.done) {
        _scAdaptTid = null;
        document.getElementById("p-sc-adapt").disabled = false;
        if (r.error) { msg.textContent = "✖ " + r.error; return; }
        var res = r.result || {};
        msg.textContent = "✓ 适配完成" + (res.count != null ? "：本项目库 " + res.count + " 张卡" : "") + "。";
        return;
      }
      setTimeout(scAdaptPoll, 1100);
    }).catch(function (e) {
      _scAdaptTid = null;
      document.getElementById("p-sc-adapt").disabled = false;
      document.getElementById("p-sc-msg").textContent = "✖ " + e;
    });
  }

  // ================= 书架（v0.16 多项目） =================
  function renderProjects() {
    api("projects").then(function (r) {
      if (!r.ok) return;
      var el = document.getElementById("proj-list");
      var list = r.projects || [];
      if (!list.length) {
        el.innerHTML = '<div class="empty"><span class="e-ic ic-project"></span>还没有项目，点「＋ 新建项目」开始</div>';
        return;
      }
      el.innerHTML = list.map(function (p) {
        return '<div class="char-item' + (p.current ? ' on' : '') + '" style="cursor:pointer" ' +
          'onclick="switchProject(\'' + esc(p.dir) + '\')">' +
          '<div><b>' + esc(p.title) + '</b>' +
          '<div class="dim">第 ' + p.next_chapter + ' 章待写 · 已写 ' + p.chapters +
          ' 章 · 角色 ' + p.characters + (p.brief ? ' · ' + esc(p.brief) : '') + '</div></div>' +
          (p.current ? '' : '<div class="acts"><button class="mini" onclick="delProject(\'' +
            esc(p.dir) + '\')">删</button></div>') +
          '</div>';
      }).join("");
    });
  }
  function switchProject(dir) {
    mask(true, "切换项目中…");
    api("project_switch", { dir: dir }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      refreshState(); loadChapters(); loadProjectForm(); renderProjects();
      document.getElementById("p-save-msg").textContent = "";
    }).catch(function (e) { mask(false); alert(e); });
  }
  function delProject(dir) {
    if (!confirm("删除这个项目？项目文件将被移除，不可恢复。")) return;
    api("project_delete", { dir: dir }, "POST").then(function (r) {
      if (err(r)) return;
      renderProjects(); refreshState();
    });
  }
  function newProject() {
    if (!confirm("新建项目？当前表单将清空，填好后点保存即创建新项目。")) return;
    api("project_new", {}, "POST").then(function (r) {
      if (err(r)) return;
      ["p-name", "p-brief", "p-world", "p-rules", "p-style", "p-style-ref",
       "p-style-note",
       "p-writer-prompt", "p-main-prompt", "p-title-rules", "rt-title-rules"].forEach(function (id) {
        document.getElementById(id).value = "";
      });
      document.getElementById("p-save-msg").textContent = "新项目：填写设定后点「保存全部项目设定」即创建";
      refreshState(); renderProjects();
    }).catch(function (e) { alert(e); });
  }

  function extractStyle() {
    mask(true, "AI 提炼风格要点中…（基于文风样本与最近章节）");
    api("style_extract", {}, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      var pts = (r.points || []).join("\n");
      if (pts) {
        document.getElementById("p-style-note").value = pts;
        alert("已提炼 " + r.points.length + " 条风格要点，可修改后随「保存全部」入库。");
      } else alert("提炼结果为空，请确认已填写文风样本并至少写了几章。");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function loadLore() {
    api("lore_list").then(function (r) {
      var el = document.getElementById("lore-list");
      el.innerHTML = "";
      if (!r.ok) return;
      (r.entries || []).forEach(function (e, i) {
        var row = document.createElement("div");
        row.className = "lore-item";
        row.innerHTML = "<div><b>" + esc(e.title) + (e.always ? "（常驻）" : "") + "</b>" +
          "<div class='dim'>" + esc(e.keys.join("、")) + "　" + esc((e.content || "").slice(0, 60)) +
          "</div></div>" +
          '<div><button class="mini" onclick="editLore(' + i + ')">编辑</button>' +
          '<button class="mini" onclick="delLore(' + i + ')">删</button></div>';
        el.appendChild(row);
      });
      if (!(r.entries || []).length) {
        el.innerHTML = '<div class="dim">还没有设定锚点。点「＋新增」添加。</div>';
      }
      window._lore = r.entries || [];
    });
  }

  function addLore() { editLore(-1); }

  function editLore(i) {
    var e = i >= 0 && window._lore && window._lore[i] ? window._lore[i] : {};
    modal(
      '<div class="row"><b>' + (i >= 0 ? "编辑锚点" : "新增锚点") + '</b></div>' +
      field("title", "标题", e.title) +
      field("keys", "关键词（逗号分隔，命中剧情文本时注入）", (e.keys || []).join("、")) +
      field("content", "内容", e.content) +
      '<label class="chk"><input type="checkbox" id="m-always"' + (e.always ? " checked" : "") +
      '> 常驻（始终注入，不依赖关键词）</label>' +
      '<div class="btnrow"><button class="primary" onclick="saveLore(' + i + ')">保存</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function saveLore(i) {
    var entries = (window._lore || []).slice();
    var entry = {
      id: (i >= 0 && entries[i] ? entries[i].id : ""),
      title: gv("title"), content: gv("content"),
      keys: gv("keys").split(/[,，]/).map(function (s) { return s.trim(); }).filter(Boolean),
      always: document.getElementById("m-always").checked
    };
    if (i >= 0) entries[i] = entry; else entries.push(entry);
    api("lore_save", { entries: entries }, "POST").then(function (r) {
      if (err(r)) return;
      closeModal(); loadLore();
    });
  }

  function delLore(i) {
    var entries = (window._lore || []).slice();
    entries.splice(i, 1);
    api("lore_save", { entries: entries }, "POST").then(function (r) {
      if (err(r)) return;
      loadLore();
    });
  }

  function loadPlans() {
    api("state").then(function (s) {
      var el = document.getElementById("plan-list");
      el.innerHTML = "";
      if (!s.ok || !s.project) return;
      var plans = []; window._plans = plans;
      // 计划走 state（project）提供，无 plan_list 接口
      loadPlansDetail();
    });
  }

  function loadPlansDetail() {
    api("plan_get", {}, "GET").then(function (r) {
      var el = document.getElementById("plan-list");
      el.innerHTML = "";
      if (!r.ok) return;
      window._plans = r.plans || [];
      if (!window._plans.length) {
        el.innerHTML = '<div class="dim">还没有计划。点「＋新增」添加。</div>';
        return;
      }
      window._plans.forEach(function (p, i) {
        var row = document.createElement("div");
        row.className = "plan-item";
        row.innerHTML = "<div><b>第 " + p.start + "~" + p.end + " 章</b> <span class='dim'>" +
          esc((p.note || "").slice(0, 40)) + "</span></div>" +
          '<button class="mini" onclick="delPlan(' + i + ')">删</button>';
        el.appendChild(row);
      });
    });
  }

  function addPlan() {
    modal(
      '<div class="row"><b>新增章节写作计划</b></div>' +
      '<label>起始章</label><input id="m-ps" type="number" value="1">' +
      '<label>结束章</label><input id="m-pe" type="number" value="3">' +
      '<label>写作指示</label><textarea id="m-pn" rows="3" placeholder="这段时间要推进的剧情/写法要求…"></textarea>' +
      '<div class="btnrow"><button class="primary" onclick="doAddPlan()">添加</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function doAddPlan() {
    api("plan_add", { start: document.getElementById("m-ps").value,
      end: document.getElementById("m-pe").value,
      note: document.getElementById("m-pn").value }, "POST").then(function (r) {
      if (err(r)) return;
      closeModal(); loadPlansDetail();
    });
  }

  function delPlan(i) {
    api("plan_del", { index: i }, "POST").then(function (r) {
      if (err(r)) return;
      loadPlansDetail();
    });
  }

  // ================= 项目对接（v0.13 与 PC 端互导） =================
  function exportProject() {
    mask(true, "打包项目中…");
    api("project_export", {}, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      document.getElementById("transfer-msg").textContent =
        "已导出：" + r.path + (r.shared ? "（已弹出系统分享，选发送方式即可）"
          : "（请在文件管理器 export 目录中拷贝）");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function importProject() {
    api("pick_import", {}, "POST").then(function (r) {
      if (err(r)) return;
      document.getElementById("transfer-msg").textContent = "请在系统文件选择器中挑选 PC 端导出的项目 zip…";
    }).catch(function (e) { alert(e); });
  }

  window.__importReady = function (fname) {
    mask(true, "导入项目中…");
    api("project_import", { fname: fname }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      document.getElementById("transfer-msg").textContent = "已导入《" + r.title + "》，现在是当前项目。";
      refreshState(); loadChapters(); loadProjectForm();
    }).catch(function (e) { mask(false); alert(e); });
  };

  // ================= 情景提示词页（v1.56 复刻 PC gui_scene_cards） =================
  var _scLib = [];        // 总库卡缓存
  var _scCur = null;      // 当前编辑的卡名（null=新卡）

  function loadSceneCards() {
    api("scene_cards_list", {}, "GET").then(function (r) {
      if (err(r)) return;
      _scLib = r.cards || [];
      // 分类下拉（保留用户当前的筛选）
      var sel = document.getElementById("sc-cat-filter");
      if (sel) {
        var cats = [];
        _scLib.forEach(function (c) {
          var g = c.category || "未分类";
          if (cats.indexOf(g) < 0) cats.push(g);
        });
        var keep = sel.value;
        sel.innerHTML = '<option value="">全部分类</option>' + cats.map(function (g) {
          return '<option value="' + esc(g) + '">' + esc(g) + "</option>";
        }).join("");
        sel.value = keep;
      }
      renderSceneLib();
      var msg = document.getElementById("sc-msg");
      if (msg && !msg.textContent) msg.textContent = "共 " + _scLib.length + " 张卡。";
    }).catch(function (e) {
      var msg = document.getElementById("sc-msg");
      if (msg) msg.textContent = "✖ " + e;
    });
  }

  function renderSceneLib() {
    var el = document.getElementById("sc-lib-list");
    if (!el) return;
    var sel = document.getElementById("sc-cat-filter");
    var cat = sel ? sel.value : "";
    var list = _scLib.filter(function (c) {
      return !cat || (c.category || "未分类") === cat;
    });
    el.innerHTML = "";
    if (!list.length) {
      el.innerHTML = '<div class="dim">这个分类下还没有卡。点「＋ 新增」手写，' +
        '或用「✨ AI 一键生成」「📄 从文本提取」快速做一张。</div>';
      return;
    }
    list.forEach(function (c) {
      var row = document.createElement("div");
      row.className = "chi";
      row.innerHTML = "<div><b>" + esc(c.name) + "</b> <span class='dim'>" +
        esc(c.category || "未分类") + "</span><div class='dim'>" +
        esc((c.content || "").slice(0, 60)) + "</div></div>";
      row.onclick = function () { scOpenCard(c.name); };
      el.appendChild(row);
    });
  }

  function scOpenCard(name) {
    var hit = null;
    _scLib.forEach(function (c) { if (c.name === name) hit = c; });
    _scCur = name;
    if (hit) {
      document.getElementById("sc-name").value = hit.name || "";
      document.getElementById("sc-cat").value = hit.category || "";
      document.getElementById("sc-content").value = hit.content || "";
    }
    subTab("scenecards", "sc-card");
    var msg = document.getElementById("sc-msg");
    if (msg) msg.textContent = "正在编辑《" + name + "》（改名后保存=另存为新的卡名）。";
  }

  function newSceneCard() {
    _scCur = null;
    document.getElementById("sc-name").value = "";
    document.getElementById("sc-cat").value = "";
    document.getElementById("sc-content").value = "";
    subTab("scenecards", "sc-card");
    var msg = document.getElementById("sc-msg");
    if (msg) msg.textContent = "新卡：填类型名 + 分类 + 规则内容，然后点「💾 保存当前卡」。";
  }

  function saveSceneCard() {
    var name = (document.getElementById("sc-name").value || "").trim();
    var content = document.getElementById("sc-content").value || "";
    var category = (document.getElementById("sc-cat").value || "").trim();
    var msg = document.getElementById("sc-msg");
    if (!name) { alert("请填类型名（如：秘境夺宝）。"); return; }
    if (!content.trim()) { alert("规则内容不能为空。"); return; }
    api("scene_cards_save", {
      name: name, content: content, category: category,
      old_name: _scCur || ""
    }, "POST").then(function (r) {
      if (err(r)) { if (msg) msg.textContent = ""; return; }
      _scCur = r.name || name;
      if (msg) msg.textContent = "✓ 已保存《" + _scCur + "》（总库共 " + (r.count || 0) + " 张）。";
      loadSceneCards();
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  }

  function delSceneCard() {
    var name = _scCur || (document.getElementById("sc-name").value || "").trim();
    if (!name) { alert("请先从卡库列表选中一张卡。"); return; }
    if (!confirm("删除总库卡《" + name + "》？（本项目库里已复制的副本不受影响）")) return;
    var msg = document.getElementById("sc-msg");
    api("scene_cards_delete", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      _scCur = null;
      document.getElementById("sc-name").value = "";
      document.getElementById("sc-cat").value = "";
      document.getElementById("sc-content").value = "";
      if (msg) msg.textContent = "✓ 已删除《" + name + "》（总库剩 " + (r.count || 0) + " 张）。";
      loadSceneCards();
    });
  }

  // ✨ AI 一键生成：给类型名 + 可补充需求 → AI 出一份规则草稿（回填到「当前卡」，确认后再保存）
  function genSceneCard() {
    modal('<div class="row"><b>✨ AI 一键生成情景卡</b></div>' +
      '<label>类型名（这类场景叫什么）</label>' +
      '<input id="m-sc-type" placeholder="例：秘境夺宝">' +
      '<label>补充需求（可选：想要什么套路/忌讳）</label>' +
      '<textarea id="m-sc-detail" rows="3" placeholder="例：要两次反转、先易后难、结尾留更大的钩子"></textarea>' +
      '<div class="btnrow"><button class="primary" onclick="runGenSceneCard()">生成</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function runGenSceneCard() {
    var t = (document.getElementById("m-sc-type").value || "").trim();
    if (!t) { alert("请填类型名。"); return; }
    mask(true, "AI 生成情景卡中…（按本项目文风与人物）");
    api("scene_cards_generate", {
      type_name: t, detail: document.getElementById("m-sc-detail").value
    }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      closeModal();
      _scCur = null;
      document.getElementById("sc-name").value = t;
      document.getElementById("sc-cat").value = "";
      document.getElementById("sc-content").value = r.content || "";
      subTab("scenecards", "sc-card");
      var msg = document.getElementById("sc-msg");
      if (msg) msg.textContent = "✓ 已生成草稿——可改后点「💾 保存当前卡」入库，或补分类后保存。";
    }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  // 📄 从文本提取：给类型名 + 参考文本 → 按提取提示词出规则草稿
  function extractSceneCard() {
    modal('<div class="row"><b>📄 从文本提取情景卡</b></div>' +
      '<label>类型名（这张卡叫什么）</label>' +
      '<input id="m-sc-etype" placeholder="例：酒馆打探消息">' +
      '<label>参考文本（一段包含这种场景的小说文字）</label>' +
      '<textarea id="m-sc-etext" rows="8" placeholder="粘贴一段参考文本…"></textarea>' +
      '<div class="dim">用的是「提取提示词」页签里那套提示词，可到那里改写。</div>' +
      '<div class="btnrow"><button class="primary" onclick="runExtractSceneCard()">提取</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function runExtractSceneCard() {
    var t = (document.getElementById("m-sc-etype").value || "").trim();
    var text = document.getElementById("m-sc-etext").value || "";
    if (!t) { alert("请填类型名。"); return; }
    if (!text.trim()) { alert("请粘贴参考文本。"); return; }
    mask(true, "从文本提取情景卡中…");
    api("scene_cards_extract", { type_name: t, text: text }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      closeModal();
      _scCur = null;
      document.getElementById("sc-name").value = t;
      document.getElementById("sc-cat").value = "";
      document.getElementById("sc-content").value = r.content || "";
      subTab("scenecards", "sc-card");
      var msg = document.getElementById("sc-msg");
      if (msg) msg.textContent = "✓ 已提取草稿——可改后点「💾 保存当前卡」入库。";
    }).catch(function (e) { mask(false); alert("请求失败：" + e); });
  }

  function loadScenePrompt() {
    api("scene_cards_prompt_get", {}, "GET").then(function (r) {
      var el = document.getElementById("sc-extract-prompt");
      if (el) el.value = r.prompt || "";
      var msg = document.getElementById("sc-prompt-msg");
      if (msg && !(r.prompt || "").trim()) {
        msg.textContent = "（当前为空 = 用内置初始提示词；点「💾 保存提取提示词」可改成自己的。）";
      }
    }).catch(function () {});
  }

  function saveScenePrompt() {
    var msg = document.getElementById("sc-prompt-msg");
    api("scene_cards_prompt_save", {
      prompt: document.getElementById("sc-extract-prompt").value
    }, "POST").then(function (r) {
      if (err(r)) return;
      if (msg) msg.textContent = "✓ 已保存提取提示词" +
        ((r.prompt || "").trim() ? "（" + r.prompt.length + " 字）" : "（留空 = 用内置初始）") + "。";
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  }

  function resetScenePrompt() {
    if (!confirm("恢复内置初始的提取提示词？（你的自定义会被清掉）")) return;
    api("scene_cards_prompt_reset", {}, "POST").then(function (r) {
      if (err(r)) return;
      var el = document.getElementById("sc-extract-prompt");
      if (el) el.value = r.prompt || "";
      var msg = document.getElementById("sc-prompt-msg");
      if (msg) msg.textContent = "✓ 已恢复内置初始提示词。";
    });
  }

  function importSceneCardTxt() {
    var text = document.getElementById("sc-import-text").value || "";
    if (!text.trim()) { alert("请先粘贴卡片文本（或点「选 txt 文件批量导入」）。"); return; }
    var msg = document.getElementById("sc-io-msg");
    api("scene_cards_import_txt", {
      text: text, fallback_name: (document.getElementById("sc-import-name").value || "").trim()
    }, "POST").then(function (r) {
      if (err(r)) { if (msg) msg.textContent = ""; return; }
      if (msg) msg.textContent = "✓ 已导入/覆盖 " + (r.added || 0) + " 张（总库共 " +
        (r.count || 0) + " 张）。";
      document.getElementById("sc-import-text").value = "";
      loadSceneCards();
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  }

  // 选 txt 文件批量导入：走系统文件选择器（imprts/picked.txt），落地后回调批量导入
  function pickSceneCardTxt() {
    window.__sceneTxtWant = true;
    var msg = document.getElementById("sc-io-msg");
    if (msg) msg.textContent = "请在弹出的文件选择器中选一份 txt（每张卡一段/用【卡名】分隔）…";
    api("pick_txt", {}, "POST").then(function (r) {
      if (err(r)) { window.__sceneTxtWant = false; return; }
    }).catch(function (e) {
      window.__sceneTxtWant = false;
      if (msg) msg.textContent = "✖ " + e;
    });
  }

  window.__sceneTxtReady = function (fname) {
    var msg = document.getElementById("sc-io-msg");
    api("scene_cards_import_txt", {
      fname: fname || "picked.txt",
      fallback_name: (document.getElementById("sc-import-name").value || "").trim()
    }, "POST").then(function (r) {
      if (err(r)) { if (msg) msg.textContent = ""; return; }
      if (msg) msg.textContent = "✓ 已从 txt 批量导入/覆盖 " + (r.added || 0) +
        " 张（总库共 " + (r.count || 0) + " 张）。";
      loadSceneCards();
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  };

  function exportSceneCard() {
    var name = _scCur || (document.getElementById("sc-name").value || "").trim();
    if (!name) { alert("请先从卡库列表选中一张卡。"); return; }
    var msg = document.getElementById("sc-export-msg");
    api("scene_cards_export", { name: name }, "POST").then(function (r) {
      if (err(r)) { if (msg) msg.textContent = "✖ " + r.error; return; }
      if (msg) msg.textContent = "✓ 已导出《" + name + "》：" + r.path +
        (r.shared ? "（已弹出系统分享，选发送方式即可）" : "（可在文件管理器 export 目录中拷贝）");
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  }

  function exportAllSceneCards() {
    var msg = document.getElementById("sc-export-msg");
    api("scene_cards_export_all", {}, "POST").then(function (r) {
      if (err(r)) { if (msg) msg.textContent = "✖ " + r.error; return; }
      if (msg) msg.textContent = "✓ 已批量导出 " + (r.cards || 0) + " 张：" + r.path +
        (r.shared ? "（已弹出系统分享）" : "（可在 export 目录中拷贝）");
    }).catch(function (e) { if (msg) msg.textContent = "✖ " + e; });
  }

  // 本项目可用卡（主AI每章从中挑卡注入）
  function loadProjectSceneCards() {
    api("scene_cards_project_list", {}, "GET").then(function (r) {
      var el = document.getElementById("sc-proj-list");
      if (!el) return;
      var cards = (r && r.cards) || [];
      el.innerHTML = "";
      if (!cards.length) {
        el.innerHTML = '<div class="dim">本项目库还是空的：点「＋ 从总库加入」勾选要带的卡。' +
          '（主AI也可在写作时自做一张只进本项目库的卡）</div>';
        return;
      }
      cards.forEach(function (c) {
        var row = document.createElement("div");
        row.className = "char-item";
        row.innerHTML = "<div><b>" + esc(c.name) + "</b> <span class='dim'>" +
          esc(c.category || "未分类") + "</span><div class='dim'>" +
          esc((c.content || "").slice(0, 60)) + "</div></div>" +
          '<div><button class="mini" onclick="projCardToLibrary(\'' + esc(c.name) +
          '\')">放入总库</button>' +
          '<button class="mini" style="color:var(--red)" onclick="removeProjectSceneCard(\'' +
          esc(c.name) + '\')">移出</button></div>';
        el.appendChild(row);
      });
    }).catch(function () {});
  }

  function pickProjectSceneCards() {
    api("scene_cards_list", {}, "GET").then(function (r) {
      if (err(r)) return;
      var all = (r.cards || []).map(function (c) { return c.name; }).filter(Boolean);
      if (!all.length) {
        alert("总库还没有情景卡——点「＋ 新增」「✨ AI 一键生成」或到「导入 / 导出」页签导入。");
        return;
      }
      api("scene_cards_project_list", {}, "GET").then(function (pr) {
        var have = {};
        ((pr && pr.cards) || []).forEach(function (c) { have[c.name] = true; });
        modal(
          '<div class="row"><b>从总库加入本项目</b></div>' +
          '<div class="dim">只有加进来的卡会被本项目主AI选用（已加入的显示为灰色）。</div>' +
          all.map(function (nm) {
            return '<label class="chk"><input type="checkbox" class="m-pc-cb" value="' +
              esc(nm) + '"' + (have[nm] ? " checked disabled" : "") + "> " + esc(nm) +
              (have[nm] ? "（已在项目库）" : "") + "</label>";
          }).join("") +
          '<div class="btnrow"><button class="primary" onclick="applyProjectSceneCards()">加入</button>' +
          '<button onclick="closeModal()">取消</button></div>');
      });
    });
  }

  function applyProjectSceneCards() {
    var names = Array.prototype.slice
      .call(document.querySelectorAll("#modal-box .m-pc-cb"))
      .filter(function (b) { return b.checked && !b.disabled; })
      .map(function (b) { return b.value; });
    if (!names.length) { alert("请至少勾选一张卡。"); return; }
    api("scene_cards_project_add", { names: names }, "POST").then(function (r) {
      if (err(r)) return;
      closeModal();
      alert("✓ 已加入 " + (r.added || 0) + " 张（本项目库现有 " + (r.count || 0) + " 张）。");
      loadProjectSceneCards();
      loadBookSceneList();
    });
  }

  function removeProjectSceneCard(name) {
    if (!confirm("把《" + name + "》移出本项目库？（不影响总库）")) return;
    api("scene_cards_project_remove", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      loadProjectSceneCards();
      loadBookSceneList();
    });
  }

  function projCardToLibrary(name) {
    api("scene_cards_project_to_library", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      if (r.skipped) alert("总库已有同名卡《" + name + "》，未覆盖（总库共 " + r.count + " 张）。");
      else alert("✓ 已把《" + name + "》放入总库（所有项目可用）。");
      loadSceneCards();
    });
  }

  // ================= 设置 =================
  function loadSettingsForm() {
    api("settings_get").then(function (r) {
      if (!r.ok) return;
      document.getElementById("s-url").value = r.base_url || "";
      document.getElementById("s-key").value = r.api_key || "";
      document.getElementById("s-model").value = r.model || "";
      document.getElementById("s-prof").value = r.current_profile || "默认配置";
      document.getElementById("s-temperature").value = r.temperature == null ? 1.0 : r.temperature;
      document.getElementById("s-chars").value = r.chapter_target_chars == null ? 2500 : r.chapter_target_chars;
      document.getElementById("s-workers").value = r.max_workers == null ? 5 : r.max_workers;
      document.getElementById("s-timeout").value = r.request_timeout == null ? 300 : r.request_timeout;
      document.getElementById("s-retry").value = r.retry_times == null ? 3 : r.retry_times;
      document.getElementById("s-retry-int").value = r.retry_interval == null ? 3 : r.retry_interval;
      document.getElementById("s-rate").value = r.rate_limit_min_wait == null ? 5 : r.rate_limit_min_wait;
      document.getElementById("s-compress").value = r.compress_interval == null ? 5 : r.compress_interval;
      document.getElementById("s-recent").value = r.writer_recent_chapters == null ? 3 : r.writer_recent_chapters;
      document.getElementById("s-overdue").value = r.foreshadow_overdue_chapters == null ? 15 : r.foreshadow_overdue_chapters;
      document.getElementById("s-search").checked = !!r.web_search_enabled;
      document.getElementById("s-rewrite").checked = r.auto_rewrite !== false;
      document.getElementById("s-proofread").checked = r.proofread_enabled !== false;
      document.getElementById("s-proofread-rules").value = r.proofread_rules || "";
      // v0.81 撤销「自定义禁词」设置栏（正文编辑区波浪线仍用 config 已有值）
      // v0.29 拆书工坊 / 小说导入成项目 API 配置下拉（选项 = 已保存配置名）
      var bsel = document.getElementById("s-break-profile");
      if (bsel) {
        bsel.innerHTML = '<option value="">跟随全局（按用途分工）</option>' +
          (r.profiles || []).map(function (p) {
            return '<option value="' + esc(p.name) + '">' + esc(p.name) + '</option>';
          }).join("");
        bsel.value = r.break_profile || "";
      }
      var isel = document.getElementById("s-import-profile");
      if (isel) {
        isel.innerHTML = '<option value="">跟随拆书工坊</option>' +
          (r.profiles || []).map(function (p) {
            return '<option value="' + esc(p.name) + '">' + esc(p.name) + '</option>';
          }).join("");
        isel.value = r.import_profile || "";
      }
      // v0.37 文风校对四节点 API 配置下拉（style_profiles dict，每节点留空跟随全局）
      var styleKeys = ["s-style-a", "s-style-b", "s-style-c", "s-style-d"];
      var styleNodes = ["node_a", "node_b", "node_c", "node_d"];
      var sprofs = r.style_profiles || {};
      for (var si = 0; si < styleKeys.length; si++) {
        var ss2 = document.getElementById(styleKeys[si]);
        if (!ss2) continue;
        ss2.innerHTML = '<option value="">跟随全局（按用途分工）</option>' +
          (r.profiles || []).map(function (p) {
            return '<option value="' + esc(p.name) + '">' + esc(p.name) + '</option>';
          }).join("");
        ss2.value = sprofs[styleNodes[si]] || "";
      }
      // v1.47 AI 对话 API 配置下拉
      var csel = document.getElementById("s-chat-profile");
      if (csel) {
        csel.innerHTML = '<option value="">跟随全局</option>' +
          (r.profiles || []).map(function (p) {
            return '<option value="' + esc(p.name) + '">' + esc(p.name) + '</option>';
          }).join("");
        csel.value = r.chat_profile || "";
      }
      // v0.31 拆书参数不再混在设置页：模式/token/重叠/并行/提示词/L3 全在「拆书工坊」页与
      // 「小说导入成项目」卡里设置；设置页只保留两个 API 选择下拉
      var effort = r.reasoning_effort || "";
      var sel = document.getElementById("s-effort");
      for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === effort) { sel.selectedIndex = i; break; }
      }
      var pl = document.getElementById("prof-list");
      pl.innerHTML = (r.profiles || []).map(function (p) {
        return '<div class="plan-item"><b>' + esc(p.name) + '</b> <span class="dim">' +
          esc(p.model || "") + '</span><button class="mini" onclick="delProfile(\'' + esc(p.name) +
          '\')">删</button></div>';
      }).join("");
      // 屏幕方向 seg 高亮
      var om = getOrient();
      document.querySelectorAll("#orient-seg button").forEach(function (b) {
        b.classList.toggle("on", b.dataset.o === om);
      });
      refreshOrientBtn();
      // 生成前确认剧情点开关
      document.getElementById("s-confirm-beats").checked = getConfirmBeats();
      // v1.56 正文长度上下限 / 单次输出上限 / 角色推理方式 / 码字上下文开关 / 情景卡 API
      setVal("s-min-chars", r.chapter_min_chars == null ? "" : r.chapter_min_chars);
      setVal("s-max-chars", r.chapter_max_chars == null ? "" : r.chapter_max_chars);
      setVal("s-max-tokens", r.max_tokens == null ? "" : r.max_tokens);
      setVal("s-main-recent", r.main_recent_chapters == null ? "" : r.main_recent_chapters);
      setReasonMode(r.reasoning_mode === "parallel" ? "parallel" : "sequential");
      setChk("s-ctx-style", r.tool_ctx_style !== false);
      setChk("s-ctx-notes", r.tool_ctx_notes !== false);
      setChk("s-ctx-rp", r.tool_ctx_rp !== false);
      // 用途分工 14 行（各环节选 API 配置 + 独立思考强度；情景提示词制作也在这一表里）
      renderRoleRows(r.profiles || [], r.role_profiles || {}, r.role_thinking || {});
      // v0.19 自动拉取模型：已填 API 地址/Key 时静默填充 datalist 下拉（不打扰）
      if ((r.base_url || "").trim() && (r.api_key || "").trim()) {
        api("fetch_models", {}, "POST").then(function (mr) {
          if (mr.error || !mr.models) return;
          var list = (mr.models || []).map(function (m) {
            return typeof m === "string" ? m : (m.id || m.name || "");
          }).filter(Boolean);
          if (list.length) {
            document.getElementById("model-list").innerHTML =
              list.map(function (m) { return '<option value="' + esc(m) + '">'; }).join("");
            document.getElementById("model-hint").textContent =
              "已自动拉取 " + list.length + " 个模型，点模型输入框可从下拉选。";
          }
        });
      }
    });
  }

  function saveSettings() {
    mask(true, "保存中…");
    api("settings_save", {
      base_url: document.getElementById("s-url").value,
      api_key: document.getElementById("s-key").value,
      model: document.getElementById("s-model").value,
      temperature: parseFloat(document.getElementById("s-temperature").value) || 1.0,
      chapter_target_chars: parseInt(document.getElementById("s-chars").value, 10) || 2500,
      chapter_min_chars: numOrZero("s-min-chars"),
      chapter_max_chars: numOrZero("s-max-chars"),
      max_tokens: numOrZero("s-max-tokens"),
      main_recent_chapters: numOrZero("s-main-recent"),
      reasoning_mode: getReasonMode(),
      tool_ctx_style: document.getElementById("s-ctx-style").checked,
      tool_ctx_notes: document.getElementById("s-ctx-notes").checked,
      tool_ctx_rp: document.getElementById("s-ctx-rp").checked,
      max_workers: parseInt(document.getElementById("s-workers").value, 10) || 5,
      request_timeout: parseInt(document.getElementById("s-timeout").value, 10) || 300,
      retry_times: parseInt(document.getElementById("s-retry").value, 10) || 3,
      retry_interval: parseInt(document.getElementById("s-retry-int").value, 10) || 3,
      rate_limit_min_wait: parseInt(document.getElementById("s-rate").value, 10) || 5,
      compress_interval: parseInt(document.getElementById("s-compress").value, 10) || 5,
      writer_recent_chapters: parseInt(document.getElementById("s-recent").value, 10) || 3,
      foreshadow_overdue_chapters: parseInt(document.getElementById("s-overdue").value, 10) || 15,
      web_search_enabled: document.getElementById("s-search").checked,
      auto_rewrite: document.getElementById("s-rewrite").checked,
      proofread_enabled: document.getElementById("s-proofread").checked,
      proofread_rules: document.getElementById("s-proofread-rules").value,
      reasoning_effort: document.getElementById("s-effort").value,
      break_profile: document.getElementById("s-break-profile").value.trim(),
      import_profile: document.getElementById("s-import-profile").value.trim(),
      style_profiles: {
        node_a: document.getElementById("s-style-a").value.trim(),
        node_b: document.getElementById("s-style-b").value.trim(),
        node_c: document.getElementById("s-style-c").value.trim(),
        node_d: document.getElementById("s-style-d").value.trim()
      },
      chat_profile: document.getElementById("s-chat-profile") ?
        document.getElementById("s-chat-profile").value.trim() : ""
    }, "POST").then(function (r) {
      mask(false);
      document.getElementById("s-msg").textContent = r.ok ? "已保存。" : r.error;
    }).catch(function (e) { mask(false); alert(e); });
  }

  function setVal(id, v) {
    var el = document.getElementById(id);
    if (el) el.value = v;
  }

  function setChk(id, on) {
    var el = document.getElementById(id);
    if (el) el.checked = !!on;
  }

  function numOrZero(id) {
    var el = document.getElementById(id);
    if (!el) return 0;
    var v = parseInt(el.value, 10);
    return (isNaN(v) || v <= 0) ? 0 : v;
  }

  // ---------- v1.56 用途分工（14 个环节各选 API 配置 + 独立思考强度） ----------
  var ROLE_ROWS = [
    ["decide", "主AI决断与校验"],
    ["write", "正文写作"],
    ["reason", "角色推理"],
    ["deai", "去AI味润色"],
    ["review", "审查AI"],
    ["write_tool", "码字AI（续写/段落工具）"],
    ["break", "拆书工坊"],
    ["import", "小说导入成项目"],
    ["scene_card", "情景提示词制作"],
    ["style_a", "文风校对·节点A"],
    ["style_b", "文风校对·节点B"],
    ["style_c", "文风校对·节点C"],
    ["style_d", "文风校对·节点D"],
    ["chat", "AI对话"]
  ];
  var THINK_LEVELS = [["", "跟随全局"], ["off", "关闭思考（最快）"], ["low", "低"],
    ["medium", "中"], ["high", "高"], ["max", "最大"]];

  function renderRoleRows(profiles, roleProfiles, roleThinking) {
    var box = document.getElementById("role-rows");
    if (!box) return;
    var po = '<option value="">（不指定）</option>' + (profiles || []).map(function (p) {
      return '<option value="' + esc(p.name) + '">' + esc(p.name) + "</option>";
    }).join("");
    var to = THINK_LEVELS.map(function (t) {
      return '<option value="' + t[0] + '">' + t[1] + "</option>";
    }).join("");
    box.innerHTML = ROLE_ROWS.map(function (row) {
      var k = row[0];
      return '<div class="row role-row"><span class="role-lab">' + row[1] + "</span>" +
        '<select id="r-prof-' + k + '" onchange="saveRoleRow(\'' + k + '\')">' + po +
        '</select><select id="r-think-' + k + '" onchange="saveRoleRow(\'' + k + '\')">' + to +
        "</select></div>";
    }).join("");
    ROLE_ROWS.forEach(function (row) {
      var k = row[0];
      var ps = document.getElementById("r-prof-" + k);
      var ts = document.getElementById("r-think-" + k);
      if (ps) ps.value = (roleProfiles || {})[k] || "";
      if (ts) ts.value = (roleThinking || {})[k] || "";
    });
  }

  function saveRoleRow() {
    var rp = {};
    var rt = {};
    ROLE_ROWS.forEach(function (row) {
      var k = row[0];
      var p = document.getElementById("r-prof-" + k);
      var t = document.getElementById("r-think-" + k);
      if (p && p.value.trim()) rp[k] = p.value.trim();
      if (t && t.value) rt[k] = t.value;
    });
    api("settings_save", { role_profiles: rp, role_thinking: rt }, "POST").then(function (r) {
      var m = document.getElementById("s-msg");
      if (m) m.textContent = r.ok ? "用途分工已保存。" : (r.error || "");
    });
  }

  function getReasonMode() {
    var seg = document.getElementById("s-reason-seg");
    if (!seg) return "sequential";
    var on = seg.querySelector("button.on");
    return (on && on.dataset.rm === "parallel") ? "parallel" : "sequential";
  }

  function setReasonMode(m) {
    var seg = document.getElementById("s-reason-seg");
    if (!seg) return;
    Array.prototype.forEach.call(seg.querySelectorAll("button"), function (b) {
      b.classList.toggle("on", b.dataset.rm === m);
    });
  }

  function saveProfile() {
    api("profiles_save", {
      name: document.getElementById("s-prof").value,
      base_url: document.getElementById("s-url").value,
      api_key: document.getElementById("s-key").value,
      model: document.getElementById("s-model").value
    }, "POST").then(function (r) {
      if (err(r)) return;
      loadSettingsForm();
      alert("配置已保存。");
    });
  }

  function delProfile(name) {
    if (!confirm("删除配置「" + name + "」？")) return;
    api("profiles_delete", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      loadSettingsForm();
    });
  }

  function fetchModels() {
    mask(true, "拉取模型列表中…");
    // v1.13 传当前输入框的地址/Key（此前传空对象，后端拿不到未保存的配置 → 报"未填写"）
    api("fetch_models", {
      base_url: document.getElementById("s-url").value,
      api_key: document.getElementById("s-key").value
    }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      var list = (r.models || []).map(function (m) {
        return typeof m === "string" ? m : (m.id || m.name || "");
      }).filter(Boolean);
      if (list.length) {
        var cur = document.getElementById("s-model").value;
        modal('<div class="row"><b>可用模型（点选填入）</b></div>' +
          list.map(function (m) {
            return '<div class="char-item" onclick="pickModel(\'' + esc(m) + '\')"><b>' +
              esc(m) + "</b></div>";
          }).join("") + '<button onclick="closeModal()">关闭</button>');
      } else alert("没有可用模型。");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function pickModel(m) {
    document.getElementById("s-model").value = m;
    closeModal();
  }

  function exportTxt() {
    mask(true, "导出中…");
    api("export_txt", {}, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      document.getElementById("export-msg").textContent =
        "已导出 " + r.chapters + " 章：\n" + (r.files || []).join("\n") +
        (r.shared ? "\n（已弹出系统分享面板）" : "\n（文件在 App 私有目录，连接电脑可拷出）");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function exportEpub() {
    mask(true, "EPUB 导出中…");
    api("export_epub", {}, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      document.getElementById("epub-msg").textContent =
        "已导出 EPUB：" + r.path +
        (r.shared ? "（已弹出系统分享面板）" : "（文件在 App 私有目录，连接电脑可拷出）");
    }).catch(function (e) { mask(false); alert(e); });
  }

  // ================= 去AI味 / 编辑审稿 =================
  var _deaiSeq = null;   // 无当前草稿时选中的已归档章节（v0.14 横屏 PC 入口）
  function openDeai() {
    var seq = document.getElementById("result").dataset.seq;
    if (seq) { _deaiSeq = seq; showDeaiModal(seq); return; }
    api("chapters").then(function (r) {
      if (!r.ok || !(r.chapters || []).length) {
        alert("暂无可治理章节：请先生成草稿，或已有已归档章节。");
        return;
      }
      modal(
        '<div class="row"><b>选择要治理的章节</b></div>' +
        r.chapters.map(function (c) {
          return '<div class="char-item" onclick="pickDeaiChapter(' + c.seq + ')"><b>第 ' +
            c.seq + ' 章 · ' + esc(c.title || "") + '</b></div>';
        }).join("") + '<button onclick="closeModal()">取消</button>');
    });
  }
  function pickDeaiChapter(seq) {
    _deaiSeq = seq;
    closeModal();
    showDeaiModal(seq);
  }
  function showDeaiModal(seq) {
    modal(
      '<div class="row"><b>去 AI 味治理 · 第 ' + seq + ' 章</b></div>' +
      '<label>治理模式</label><select id="m-deai-mode">' +
      '<option value="clean">按规则清洗（推荐）</option>' +
      '<option value="replace">句式词形替换</option>' +
      '<option value="rewrite">整章/局部重写</option></select>' +
      '<div class="btnrow"><button class="primary" onclick="deaiRun()">开始治理</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function deaiRun() {
    var seq = _deaiSeq || document.getElementById("result").dataset.seq;
    mask(true, "AI 治理中…（只改文本，不改剧情）");
    api("deai_run", { seq: seq, mode: document.getElementById("m-deai-mode").value }, "POST")
      .then(function (r) {
        mask(false);
        if (err(r)) return;
        modal(
          '<div class="row"><b>治理结果 · 第 ' + seq + ' 章</b></div>' +
          '<details><summary>查看治理后全文</summary>' +
          '<textarea id="m-polished" rows="12">' + esc(r.polished) + '</textarea></details>' +
          '<div class="btnrow"><button class="primary" onclick="deaiApply()">采用并合并（自动备份）</button>' +
          '<button onclick="closeModal()">放弃</button></div>');
        window._polished = r.polished;
      }).catch(function (e) { mask(false); alert(e); });
  }

  function deaiApply() {
    var seq = _deaiSeq || document.getElementById("result").dataset.seq;
    mask(true, "合并中…");
    api("deai_apply", { seq: seq, polished: window._polished }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      closeModal();
      if (document.getElementById("result").dataset.seq == seq) {
        document.getElementById("out-content").value = window._polished;
        document.getElementById("out-meta").textContent = "";
      }
      loadDrafts();
      alert("已合并治理结果（原正文已备份到草稿箱）。");
    }).catch(function (e) { mask(false); alert(e); });
  }

  function openEditorReview(seq) {
    if (!seq) seq = document.getElementById("result").dataset.seq;
    if (!seq) { alert("请先生成本章。"); return; }
    mask(true, "AI 编辑审稿中…");
    api("editor_review", { seq: seq }, "POST").then(function (r) {
      mask(false);
      if (err(r)) return;
      var d = r.data || {};
      modal(
        '<div class="row"><b>编辑审稿 · 第 ' + seq + ' 章</b></div>' +
        '<div class="meta">' + esc(JSON.stringify(d).slice(0, 1500)) + '</div>' +
        '<button onclick="closeModal()">关闭</button>');
    }).catch(function (e) { mask(false); alert(e); });
  }

  // ================= 草稿箱 =================
  function restoreDraft(fname) {
    if (!confirm("把草稿恢复为正式章节（覆盖同章号现有内容）？")) return;
    api("draft_restore", { fname: fname }, "POST").then(function (r) {
      if (err(r)) return;
      loadDrafts(); refreshState(); loadChapters();
      alert("已恢复第 " + r.seq + " 章。");
    });
  }

  function delDraft(fname) {
    if (!confirm("删除这份备份？")) return;
    api("draft_delete", { fname: fname }, "POST").then(function (r) {
      if (err(r)) return;
      loadDrafts();
    });
  }

  // ================= 章节列表（码字页目录 + 生成页「已写章节」共用） =================
  function loadChapters() {
    loadGenChapters();
    loadWorkList();
  }

  // ================= 屏幕方向（v1.52：默认横屏，可切竖屏并记忆） =================
  // 界面本身只有一套壳（左侧导航 + 右侧工作区，见 style.css），方向只影响可用宽度。
  var ORIENT_KEY = "xinghuo_orient_v1";
  var _orientMem = null;
  function getOrient() {
    if (_orientMem !== null) return _orientMem;
    // 未记过选择时默认横屏启动（PC 版布局的宽屏形态）；用户切过之后按记忆走
    try { _orientMem = localStorage.getItem(ORIENT_KEY) || "landscape"; }
    catch (e) { _orientMem = "landscape"; }
    return _orientMem;
  }
  function setOrient(m) {
    _orientMem = m;
    try { localStorage.setItem(ORIENT_KEY, m); } catch (e) { /* file:// 下存储不可用时降级为内存记忆 */ }
    document.querySelectorAll("#orient-seg button").forEach(function (b) {
      b.classList.toggle("on", b.dataset.o === m);
    });
    refreshOrientBtn();
    api("orientation", { mode: m }, "POST").then(function (r) {
      if (r && r.error) alert(r.error);
    });
  }
  function isLandscapeNow() {
    if (window.matchMedia) {
      return window.matchMedia("(orientation: landscape)").matches;
    }
    return window.orientation === 90 || window.orientation === -90;
  }
  // 顶栏/侧边按钮：按【当前实际方向】切到相反方向——无论处于哪种模式点一下都有反应
  function toggleOrientation() {
    setOrient(isLandscapeNow() ? "portrait" : "landscape");
  }
  function refreshOrientBtn() {
    var txt = getOrient() === "landscape" ? "⇄ 竖屏" : "⇄ 横屏";
    document.querySelectorAll(".orient-btn").forEach(function (el) {
      el.textContent = txt;
    });
  }

  // ================= 界面缩放（v1.53：对应 PC 版「界面缩放 50%~160%」） =================
  // PC 端 Ctrl+滚轮重设整套 QSS 等比缩放；安卓端没有滚轮，改成导航底部 −/＋ 与设置页按钮，
  // 改整页 zoom（等比缩放，含字体/间距/圆角），点百分比恢复 100%；另外 WebView 侧允许双指
  // 捏合自由缩放页面（原生缩放，见 MainActivity）。
  var ZOOM_KEY = "xinghuo_zoom_v1";
  var ZOOM_MIN = 50, ZOOM_MAX = 160, ZOOM_STEP = 10;
  function getUiZoom() {
    try {
      var v = parseInt(localStorage.getItem(ZOOM_KEY), 10);
      if (v >= ZOOM_MIN && v <= ZOOM_MAX) return v;
    } catch (e) { /* file:// 下存储不可用时降级为默认 100% */ }
    return 100;
  }
  function applyUiZoom(pct) {
    // 100% 时不写 zoom，保持 WebView 默认观感（也避开个别旧版根元素 zoom 的差异）
    document.documentElement.style.zoom = pct === 100 ? "" : String(pct / 100);
    document.querySelectorAll(".zoom-pct").forEach(function (el) {
      el.textContent = pct + "%";
    });
  }
  function setUiZoom(pct) {
    pct = Math.round(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, pct)) / ZOOM_STEP) * ZOOM_STEP;
    try { localStorage.setItem(ZOOM_KEY, String(pct)); } catch (e) { /* 忽略 */ }
    applyUiZoom(pct);
  }
  function uiZoomStep(dir) { setUiZoom(getUiZoom() + dir * ZOOM_STEP); }
  function uiZoomReset() { setUiZoom(100); }

  // ================= 界面风格（v1.46 三套配色 + v1.78 静谧石墨：只换皮肤，不改功能） =================
  var THEME_KEY = "xinghuo_theme_v1";
  var THEMES = ["sakura", "mint", "night", "graphite"];
  var _themeMem = null;
  function getUiTheme() {
    if (_themeMem !== null) return _themeMem;
    try {
      var t = localStorage.getItem(THEME_KEY);
      _themeMem = THEMES.indexOf(t) >= 0 ? t : "sakura";
    } catch (e) { _themeMem = "sakura"; }
    return _themeMem;
  }
  function applyUiTheme(t) {
    document.documentElement.dataset.theme = t;
    document.querySelectorAll("#theme-seg button").forEach(function (b) {
      b.classList.toggle("on", b.dataset.t === t);
    });
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.setAttribute("content", getComputedStyle(document.documentElement)
      .getPropertyValue("--bg1").trim() || "#fff8fb");
  }
  function setUiTheme(t) {          // 设置页「界面风格」点击
    if (THEMES.indexOf(t) < 0) return;
    _themeMem = t;
    try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* 存储不可用时仅内存记忆 */ }
    applyUiTheme(t);
  }
  function initUiTheme() { applyUiTheme(getUiTheme()); }

  // ================= 生成前剧情点确认关卡开关（v0.15，默认开启） =================
  var CONFIRM_KEY = "xinghuo_confirm_beats_v1";
  var _confirmMem = null;
  function getConfirmBeats() {
    if (_confirmMem !== null) return _confirmMem;
    try { _confirmMem = localStorage.getItem(CONFIRM_KEY) !== "off"; }
    catch (e) { _confirmMem = true; }
    return _confirmMem;
  }
  function setConfirmBeatsCb() {
    var on = document.getElementById("s-confirm-beats").checked;
    _confirmMem = on;
    try { localStorage.setItem(CONFIRM_KEY, on ? "on" : "off"); } catch (e) {}
  }

  // ================= 语音码字（v0.16，系统语音识别面板） =================
  function voiceInput() {
    mask(true, "系统语音识别面板已弹出，说出要输入的内容…");
    api("voice_input", {}, "POST").then(function (r) {
      if (err(r)) { mask(false); return; }
      // 结果经 Java onActivityResult 回调 window.__voiceReady(text) 插入
    }).catch(function (e) { mask(false); alert(e); });
  }
  function insertAtCursor(el, text) {
    if (!el) return;
    var s = el.selectionStart != null ? el.selectionStart : el.value.length;
    var e = el.selectionEnd != null ? el.selectionEnd : s;
    el.value = el.value.slice(0, s) + text + el.value.slice(e);
    try { el.selectionStart = el.selectionEnd = s + text.length; } catch (err) {}
    el.focus();
  }
  // v0.20 听写历史：识别文本存 localStorage（最近 10 条），可点击回填
  var VOICE_KEY = "xinghuo_voice_hist_v1";
  function voiceHist() {
    try { return JSON.parse(localStorage.getItem(VOICE_KEY) || "[]"); }
    catch (e) { return []; }
  }
  function saveVoiceHist(text) {
    var h = voiceHist();
    h.unshift({ t: text, at: new Date().toLocaleTimeString("zh-CN") });
    h = h.slice(0, 10);
    try { localStorage.setItem(VOICE_KEY, JSON.stringify(h)); } catch (e) {}
    renderVoiceHist();
  }
  function renderVoiceHist() {
    var h = voiceHist();
    var el = document.getElementById("voice-hist");
    if (!el) return;
    if (!h.length) { el.classList.add("hidden"); return; }
    el.classList.remove("hidden");
    var list = document.getElementById("voice-hist-list");
    list.innerHTML = "";
    h.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "chi";
      row.innerHTML = '<b>' + esc(item.at) + "</b><div class='dim'>" + esc(item.t.slice(0, 60)) +
        (item.t.length > 60 ? "…" : "") + "</div>";
      row.onclick = function () {
        var cur = document.activeElement;
        if (cur && (cur.tagName === "TEXTAREA" || cur.tagName === "INPUT")) {
          insertAtCursor(cur, item.t);
        } else {
          insertAtCursor(document.getElementById("out-content"), item.t);
        }
      };
      list.appendChild(row);
    });
  }
  function clearVoiceHist() {
    try { localStorage.removeItem(VOICE_KEY); } catch (e) {}
    renderVoiceHist();
  }
  // Java 桥回调：识别文本插入当前聚焦的输入框（无聚焦则插到正文编辑区）+ 记入听写历史
  window.__voiceReady = function (text) {
    mask(false);
    if (!text) return;
    var el = document.activeElement;
    if (el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT")) {
      insertAtCursor(el, text);
    } else {
      insertAtCursor(document.getElementById("out-content"), text);
    }
    if (text.trim()) saveVoiceHist(text.trim());
  };

  // ================= tab =================
  // v1.52：补上 tutorial，否则点「教程」会隐藏所有页面却不显示教程页（空白工作区）
  // v1.56：补上 generate（小说生成独立页）与 scenecards（情景提示词页），与电脑端 12 个大页对齐
  var tabs = ["write", "generate", "characters", "archive", "style", "break", "chat",
              "project", "scenecards", "settings", "tutorial"];
  // ================= 拆书工坊（v0.55） =================
  var _breakTid = null;
  var _breakLast = 0;
  var _breakTimer = null;
  var _breakCur = null;    // 当前拆书结果 {doc, learning, stats}
  var _breakFname = null;
  // ================= 文风校对（v0.36） =================
  var _styleTid = null;
  var _styleLast = 0;
  var _styleTimer = null;
  var _styleFname = null;
  function setBreakMode(mode) {
    var seg = document.getElementById("break-mode-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.dataset.mode === mode);
    });
    // 简单模式只留基本参数；智能模式显示档位+上下文（自动换算 token）；高级模式全开
    var adv = mode === "advanced";
    var smt = mode === "smart" || adv;
    var smart = mode === "smart";
    document.querySelectorAll("#tab-break .adv-only").forEach(function (el) {
      el.style.display = adv ? "" : "none";
    });
    document.querySelectorAll("#tab-break .smart-only").forEach(function (el) {
      el.style.display = smart ? "" : "none";
    });
    var parn = document.getElementById("break-parn");
    if (parn) parn.style.display = smt ? "" : "none";
    var prompt = document.getElementById("break-prompt");
    if (prompt) prompt.style.display = smt ? "" : "none";
    var token = document.getElementById("break-token");
    if (token) token.style.display = smart ? "none" : "";
  }
  function setBreakSmart(sub) {
    var seg = document.getElementById("break-smart-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.dataset.sub === sub);
    });
  }
  function setBreakPar(v) {
    document.querySelectorAll("#break-par-seg button").forEach(function (b) {
      b.classList.toggle("on", b.dataset.bp === v);
    });
  }
  function initBreakTab() {
    loadBreaks();
    // 回填拆书参数（config 为准：模式/档位/上下文/token/重叠/并行/提示词/L3）
    api("settings_get", {}, "GET").then(function (r) {
      if (!r.ok) return;
      var mode = r.break_mode || "smart";
      setBreakMode(mode);
      setBreakSmart(r.break_smart_sub || "balanced");
      document.getElementById("break-ctx").value =
        r.model_context_window == null ? 0 : r.model_context_window;
      document.getElementById("break-prompt").value = r.break_prompt || "";
      document.getElementById("break-token").value =
        r.break_token_per_part == null ? 8000 : r.break_token_per_part;
      var ov = document.getElementById("break-overlap");
      if (ov) ov.value = r.break_overlap_token == null ? 0 : r.break_overlap_token;
      var l3 = document.getElementById("break-l3");
      if (l3) l3.value = r.break_l3_batch == null ? 0 : r.break_l3_batch;
      var pn = document.getElementById("break-parn");
      if (pn) pn.value = r.break_parallel_n == null ? 2 : r.break_parallel_n;
      setBreakPar(r.break_parallel ? "1" : "0");
    });
    refreshState().then(function () {
      var b = document.getElementById("break-cur");
      if (b) {
        var st = window.__lastProject;
        b.textContent = st && st.break_style
          ? "当前项目已应用拆书风格：" + st.break_style
          : "当前项目未应用拆书风格（拆书后保存风格，再点「应用到当前项目」）";
      }
    });
  }
  function saveBreakSettings() {
    var mbtn = document.querySelector("#break-mode-seg button.on");
    var mode = mbtn ? mbtn.dataset.mode : "smart";
    var sbtn = document.querySelector("#break-smart-seg button.on");
    var sub = sbtn ? sbtn.dataset.sub : "balanced";
    var ov = parseInt(document.getElementById("break-overlap").value, 10) || 0;
    var l3 = parseInt(document.getElementById("break-l3").value, 10) || 0;
    var parn = parseInt(document.getElementById("break-parn").value, 10) || 2;
    var ctx = parseInt(document.getElementById("break-ctx").value, 10) || 0;
    api("settings_save", {
      break_mode: mode,
      break_smart_sub: sub,
      model_context_window: Math.max(0, Math.min(10000000, ctx)),
      break_prompt: document.getElementById("break-prompt").value.trim(),
      break_token_per_part: parseInt(document.getElementById("break-token").value, 10) || 8000,
      break_overlap_token: Math.max(0, ov),
      break_l3_batch: Math.max(0, Math.min(60, l3)),
      break_parallel: document.querySelector("#break-par-seg button.on").dataset.bp === "1",
      break_parallel_n: Math.max(1, Math.min(8, parn))
    }, "POST").then(function (r) {
      var tok = mode === "smart"
        ? "按上下文×" + (sub === "conservative" ? "30%" : sub === "aggressive" ? "70%" : "50%") + " 自动定档"
        : "每部分 " + (parseInt(document.getElementById("break-token").value, 10) || 8000) + " token";
      document.getElementById("break-msg").textContent =
        r.ok ? "拆书设置已保存（模式：" + (mode === "advanced" ? "高级" : mode === "simple" ? "简单" : "智能") +
          (mode === "smart" ? "·" + (sub === "conservative" ? "保守" : sub === "aggressive" ? "激进" : "正常") : "") +
          "，" + tok + (ov ? "，重叠 " + ov + " token" : "") + (l3 ? "，L3 分批 " + l3 : "") + "）。" : r.error;
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function breakImportDoc() {
    // 复用系统文件选择器选拆书文档（txt/md/json），导入为一个拆书风格
    api("pick_txt", {}, "POST").then(function (r) {
      if (err(r)) return;
      document.getElementById("break-msg").textContent =
        "请在弹出的文件选择器中选拆书文档（txt/md/json）…";
    }).catch(function (e) { alert("请求失败：" + e); });
    // 等待 Java 回调后手动触发一次解析（拆书文档内容走 break_import_doc）
    window.__breakDocReady = function (fname) {
      mask(false);
      var name = prompt("保存为拆书风格名称：", "");
      if (name === null) return;
      if (!name.trim()) { alert("名称不能为空。"); return; }
      api("break_import_doc", { name: name.trim(), fname: fname }, "POST").then(function (r) {
        if (err(r)) return;
        alert("已导入为拆书风格「" + r.name + "」。可在风格库「应用到当前项目」让主AI学习。");
        loadBreaks();
      }).catch(function (e) { alert("请求失败：" + e); });
    };
  }
  function pickBreakTxt() {
    api("pick_txt", {}, "POST").then(function (r) {
      if (err(r)) return;
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  // Java 桥回调：txt 已保存到 imports/picked.txt（拆书工坊与小说导入成项目共用）
  window.__breakTxtReady = function (fname) {
    mask(false);
    // v1.56 情景提示词页「选 txt 文件批量导入」也走同一个 Java 回调
    if (window.__sceneTxtWant) {
      window.__sceneTxtWant = false;
      window.__sceneTxtReady(fname);
      return;
    }
    _breakFname = fname || "picked.txt";
    _styleFname = _breakFname;
    _importFname = _breakFname;
    api("break_parse", { fname: _breakFname }, "GET").then(function (r) {
      if (err(r)) return;
      var vols = (r.volumes || []).slice(0, 20).map(function (v) {
        return "第" + v.no + "卷" + (v.title ? "《" + v.title + "》" : "") + "·" + v.chapters + "章";
      }).join("\n");
      var base = "已导入：共 " + r.vol_count + " 卷 / " + r.chapter_count + " 章 / " +
        (r.chars / 10000).toFixed(1) + " 万字";
      document.getElementById("break-parse-info").innerHTML =
        base + "（按卷分批 AI 拆解，始终维系全书整体性）。<br>" +
        (vols ? "<pre>" + esc(vols) + "</pre>" : "");
      document.getElementById("break-start-btn").disabled = false;
      document.getElementById("break-restart-btn").disabled = false;
      var ip = document.getElementById("import-parse-info");
      if (ip) ip.innerHTML = base + "，可开始导入成项目（会先自动拆书再还原设定/角色/章节）。";
      var ir = document.getElementById("m-import-run");
      var irr = document.getElementById("m-import-restart");
      if (irr) irr.disabled = false;
      if (ir) ir.disabled = false;
    });
  };
  function breakRestart() {
    // v0.39 重新开始拆书：清空进度全部重来（不再续传）
    if (!_breakFname) { alert("请先导入 txt。"); return; }
    if (_breakTid) { alert("拆书进行中，请先停止或等待完成。"); return; }
    if (!confirm("将清除本次小说的拆书进度，从头重新拆书（不再续传）。确定吗？")) return;
    breakStart(true);
  }
  function breakStart(restart) {
    if (!_breakFname) { alert("请先导入 txt。"); return; }
    if (_breakTid) { alert("拆书进行中，请先停止或等待完成。"); return; }
    api("break_start", { fname: _breakFname, title: "拆书分析", restart: !!restart }, "POST").then(function (r) {
      if (err(r)) return;
      _breakTid = r.task_id;
      _breakLast = 0;
      _breakCur = null;
      document.getElementById("break-doc").textContent = "";
      document.getElementById("break-logs").innerHTML = "";
      document.getElementById("break-prog").classList.remove("hidden");
      document.getElementById("break-start-btn").disabled = true;
      document.getElementById("break-restart-btn").disabled = true;
      document.getElementById("break-stop-btn").disabled = false;
      document.getElementById("break-msg").textContent = "正在拆书（L1 标题概览 → 全书骨架 → 逐卷细纲 → 汇总）…";
      breakPoll();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function breakStop() {
    if (!_breakTid) return;
    api("break_stop", { task_id: _breakTid }, "POST").then(function (r) {
      var b = document.getElementById("break-stop-btn");
      if (b) { b.disabled = true; b.textContent = "正在停止…"; }
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function breakPoll() {
    if (!_breakTid) return;
    api("task_status", { task_id: _breakTid, since: _breakLast }, "GET").then(function (r) {
      if (r.error) { alert(r.error); _breakTid = null; resetBreakBtns(); return; }
      if (r.logs && r.logs.length) {
        _breakLast = r.count;
        var box = document.getElementById("break-logs");
        r.logs.forEach(function (l) {
          var d = document.createElement("div");
          if (l.kind === "warn") d.className = "warn";
          if (l.kind === "error") d.className = "warn";
          d.textContent = l.msg;
          box.appendChild(d);
          box.scrollTop = box.scrollHeight;
        });
      }
      if (r.done) {
        _breakTid = null;
        var res = r.result || {};
        if (r.error) { alert(r.error); resetBreakBtns(); return; }
        if (res.ok && res.doc) {
          _breakCur = res;
          document.getElementById("break-doc").textContent = res.doc;
          document.getElementById("break-save-btn").disabled = false;
          document.getElementById("break-export-btn").disabled = false;
          document.getElementById("break-msg").textContent =
            "拆书完成：文档 " + res.doc.length + " 字（≤5 万）。可「保存为拆书风格」→ 应用到当前项目，让主AI学习其剧情设计技法。";
        } else {
          document.getElementById("break-msg").textContent = "拆书未完成：" + (res.error || "");
        }
        resetBreakBtns();
        return;
      }
      var p = r.progress;
      if (p && p.total) {
        var stage = { title: "L1 标题概览", skeleton: "L1 骨架", volume: "L2 卷细纲", merge: "L3 汇总" }[p.stage] || p.stage;
        document.getElementById("break-prog").querySelector("div").style.width =
          Math.round(p.done * 100 / p.total) + "%";
        document.getElementById("break-msg").textContent = stage + " " + p.done + "/" + p.total;
      }
      _breakTimer = setTimeout(breakPoll, 1100);
    }).catch(function (e) { alert("请求失败：" + e); _breakTid = null; });
  }
  function resetBreakBtns() {
    document.getElementById("break-start-btn").disabled = false;
    document.getElementById("break-restart-btn").disabled = false;
    var b = document.getElementById("break-stop-btn");
    b.disabled = true;
    b.textContent = "停止";
  }
  function breakSave() {
    if (!_breakCur || !_breakCur.doc) { alert("还没有拆书结果。"); return; }
    var name = prompt("拆书风格名称（如：番茄爽文流 / 悬疑日常伏笔流）：", "");
    if (name === null) return;
    name = name.trim();
    if (!name) { alert("名称不能为空。"); return; }
    api("break_save", { name: name, doc: _breakCur.doc, learning: _breakCur.learning || "" }, "POST")
      .then(function (r) {
        if (err(r)) return;
        alert("已保存为拆书风格「" + name + "」。回到风格库点「应用到当前项目」即可让主AI学习其设计技法。");
        loadBreaks();
      }).catch(function (e) { alert("请求失败：" + e); });
  }
  function loadBreaks() {
    api("breaks_list", {}, "GET").then(function (r) {
      if (!r.ok) return;
      var sel = document.getElementById("break-style-sel");
      var prev = sel.value;
      sel.innerHTML = "";
      (r.breaks || []).forEach(function (b) {
        var o = document.createElement("option");
        o.value = b.name;
        o.textContent = b.name + "（" + (b.doc_chars || 0) + "字）";
        sel.appendChild(o);
      });
      if (prev && Array.prototype.some.call(sel.options, function (o) { return o.value === prev; })) {
        sel.value = prev;
      }
    });
  }
  function breakShowStyle() {
    var name = document.getElementById("break-style-sel").value;
    if (!name) return;
    api("break_load", { name: name }, "GET").then(function (r) {
      if (err(r)) return;
      document.getElementById("break-doc").textContent = ((r.break || {}).doc) || "";
      document.getElementById("break-export-btn").disabled = false;
    });
  }
  function breakApply() {
    var name = document.getElementById("break-style-sel").value;
    if (!name) { alert("风格库为空，请先拆书并保存风格。"); return; }
    if (!confirm("把拆书风格「" + name + "」应用到当前项目？主AI会在剧情决断/校验/审查时"
      + "参考其提炼的设计技法（学剧情推动/伏笔设计，不照抄情节）。")) return;
    api("break_apply", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      alert("已应用。主AI将学习「" + name + "」的剧情设计技法。");
      initBreakTab();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function breakExport() {
    var name = document.getElementById("break-style-sel").value;
    if (!name) { alert("请先选一个拆书风格。"); return; }
    api("break_export", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      alert(r.shared ? "已弹出系统分享面板。" : "已导出：" + r.path);
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function breakExportCur() {
    if (_breakCur && _breakCur.doc) {
      var name = prompt("导出为哪个风格名？", "");
      if (name === null) return;
      api("break_save", { name: name.trim() || "拆书", doc: _breakCur.doc, learning: _breakCur.learning || "" }, "POST")
        .then(function (r) {
          if (err(r)) return;
          api("break_export", { name: r.name }, "POST").then(function (r2) {
            if (err(r2)) return;
            alert(r2.shared ? "已弹出系统分享面板。" : "已导出：" + r2.path);
          });
        });
      return;
    }
    breakShowStyle();
    breakExport();
  }
  function breakDelete() {
    var name = document.getElementById("break-style-sel").value;
    if (!name) { alert("风格库为空。"); return; }
    if (!confirm("删除拆书风格「" + name + "」？")) return;
    api("break_delete", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      loadBreaks();
      alert("已删除。");
    }).catch(function (e) { alert("请求失败：" + e); });
  }

  // ================= 文风校对（v0.36：A提取→B生成→C评分→D优化 多轮迭代，任务化可停止） =================
  function initStyleTab() {
    api("stylecheck_prompts", {}, "GET").then(function (r) {
      if (!r.ok) return;
      if (r.prompts) {
        document.getElementById("se-p-a").value = r.prompts.node_a || "";
        document.getElementById("se-p-b").value = r.prompts.node_b || "";
        document.getElementById("se-p-c").value = r.prompts.node_c || "";
        document.getElementById("se-p-d").value = r.prompts.node_d || "";
      }
      var sel = document.getElementById("se-preset-sel");
      var names = Object.keys(r.presets || {});
      sel.innerHTML = names.map(function (n) {
        return '<option value="' + esc(n) + '">' + esc(n) + '</option>';
      }).join("");
      var m = document.getElementById("se-msg");
      if (_styleFname && m) m.textContent = "已导入 txt：" + _styleFname + "（可直接开始校对，也可粘贴原文覆盖）。";
    });
  }
  function pickStyleTxt() {
    api("pick_txt", {}, "POST").then(function (r) {
      if (err(r)) return;
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function styleStart() {
    if (_styleTid) { alert("校对进行中，请先停止或等待完成。"); return; }
    var content = document.getElementById("se-text").value.trim();
    if (!content && !_styleFname) { alert("请先粘贴原文或导入 txt。"); return; }
    var rounds = parseInt(document.getElementById("se-rounds").value, 10) || 5;
    var threshold = parseFloat(document.getElementById("se-threshold").value) || 80;
    api("stylecheck_start", {
      content: content,
      fname: _styleFname,
      max_rounds: rounds,
      threshold: threshold
    }, "POST").then(function (r) {
      if (err(r)) return;
      _styleTid = r.task_id;
      _styleLast = 0;
      document.getElementById("se-logs").innerHTML = "";
      document.getElementById("se-top").textContent = "";
      document.getElementById("se-start-btn").disabled = true;
      document.getElementById("se-stop-btn").disabled = false;
      document.getElementById("se-export-btn").disabled = true;
      document.getElementById("se-msg").textContent = "正在校对（节点A 提取文风 → 多轮 B 生成 / C 评分 / D 优化）…";
      stylePoll();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function styleStop() {
    if (!_styleTid) return;
    api("stylecheck_stop", { task_id: _styleTid }, "POST").then(function (r) {
      var b = document.getElementById("se-stop-btn");
      if (b) { b.disabled = true; b.textContent = "正在停止…"; }
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function stylePoll() {
    if (!_styleTid) return;
    api("task_status", { task_id: _styleTid, since: _styleLast }, "GET").then(function (r) {
      if (r.error) { alert(r.error); _styleTid = null; styleResetBtns(); return; }
      if (r.logs && r.logs.length) {
        _styleLast = r.count;
        var box = document.getElementById("se-logs");
        r.logs.forEach(function (l) {
          var d = document.createElement("div");
          if (l.kind === "warn") d.className = "warn";
          d.textContent = l.msg;
          box.appendChild(d);
          box.scrollTop = box.scrollHeight;
        });
      }
      if (r.done) {
        _styleTid = null;
        var res = r.result || {};
        if (r.error) { alert(r.error); styleResetBtns(); return; }
        if (res.ok && res.top && res.top.length) {
          var lines = res.top.map(function (t, i) {
            return "Top" + (i + 1) + "（" + t.score + " 分）：\n" + t.prompt;
          }).join("\n\n");
          document.getElementById("se-top").textContent = lines;
          document.getElementById("se-export-btn").disabled = false;
          document.getElementById("se-msg").textContent =
            "校对完成：最佳 " + res.best_score + " 分" + (res.reached_threshold ? "（已达阈值）" : "") +
            "，共 " + (res.rounds || []).length + " 轮。可导出 Top3 提示词。";
        } else {
          document.getElementById("se-msg").textContent = "校对未完成：" + (r.error || "无结果");
        }
        styleResetBtns();
        return;
      }
      _styleTimer = setTimeout(stylePoll, 1100);
    }).catch(function (e) { alert("请求失败：" + e); _styleTid = null; styleResetBtns(); });
  }
  function styleResetBtns() {
    document.getElementById("se-start-btn").disabled = false;
    var b = document.getElementById("se-stop-btn");
    if (b) { b.disabled = true; b.textContent = "停止"; }
  }
  function stylePromptsSave() {
    api("stylecheck_prompts_save", {
      prompts: {
        node_a: document.getElementById("se-p-a").value,
        node_b: document.getElementById("se-p-b").value,
        node_c: document.getElementById("se-p-c").value,
        node_d: document.getElementById("se-p-d").value
      }
    }, "POST").then(function (r) {
      if (err(r)) return;
      alert("提示词已保存。");
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function stylePresetSave() {
    var name = prompt("存为预设名（留空=取消）：", "");
    if (!name) return;
    api("stylecheck_presets_save", {
      name: name.trim(),
      prompts: {
        node_a: document.getElementById("se-p-a").value,
        node_b: document.getElementById("se-p-b").value,
        node_c: document.getElementById("se-p-c").value,
        node_d: document.getElementById("se-p-d").value
      }
    }, "POST").then(function (r) {
      if (err(r)) return;
      alert("预设已保存。");
      initStyleTab();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function stylePresetLoad() {
    var name = document.getElementById("se-preset-sel").value;
    if (!name) { alert("请先选一个预设。"); return; }
    api("stylecheck_presets_apply", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      if (r.prompts) {
        document.getElementById("se-p-a").value = r.prompts.node_a || "";
        document.getElementById("se-p-b").value = r.prompts.node_b || "";
        document.getElementById("se-p-c").value = r.prompts.node_c || "";
        document.getElementById("se-p-d").value = r.prompts.node_d || "";
      }
      alert("已加载预设「" + name + "」。");
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function stylePresetDelete() {
    var name = document.getElementById("se-preset-sel").value;
    if (!name || name === "default") { alert("default 不可删除。"); return; }
    if (!confirm("删除预设「" + name + "」？")) return;
    api("stylecheck_presets_delete", { name: name }, "POST").then(function (r) {
      if (err(r)) return;
      alert("已删除。");
      initStyleTab();
    }).catch(function (e) { alert("请求失败：" + e); });
  }
  function styleExport() {
    var text = document.getElementById("se-top").textContent;
    if (!text) { alert("还没有可导出的结果。"); return; }
    api("stylecheck_export", { text: text }, "POST").then(function (r) {
      if (err(r)) return;
      alert(r.shared ? "已弹出系统分享面板。" : "已导出：" + r.path);
    }).catch(function (e) { alert("请求失败：" + e); });
  }

  function switchTab(name) {
    tabs.forEach(function (t) {
      document.getElementById("tab-" + t).classList.toggle("hidden", t !== name);
    });
    document.querySelectorAll(".navbtn").forEach(function (b) {
      b.classList.toggle("on", b.dataset.tab === name);
    });
    if (name === "write") initWriteTab();
    if (name === "generate") initGenerateTab();
    if (name === "characters") renderCharacters();
    if (name === "archive") subTab("archive", _subName.archive || "timeline");
    if (name === "style") initStyleTab();
    if (name === "break") initBreakTab();
    if (name === "chat") initChatTab();
    if (name === "project") {
      renderProjects();
      subTab("project", _subName.project || "p-story");
    }
    if (name === "scenecards") subTab("scenecards", _subName.scenecards || "sc-lib");
    if (name === "settings") loadSettingsForm();
  }

  document.querySelectorAll(".navbtn[data-tab]").forEach(function (b) {
    b.onclick = function () { switchTab(b.dataset.tab); };
  });

  // ================= AI 对话（v1.47 与桌面 gui_chat 语义对齐） =================
  var _chatTid = null;          // 当前打开话题 id
  var _chatTitle = "";          // 当前话题名（重命名弹窗回填）
  var _chatMsgs = [];           // 当前话题消息缓存
  var _chatTask = null;         // 运行中任务 task_id
  var _chatLast = 0;            // 任务日志 since 游标
  var _chatTimer = null;        // 轮询定时器
  var _chatStreamNode = null;   // 流式中的 AI 气泡节点
  var _chatStream = null;       // {think, body} 流式累积

  function chatBubble(role, content, think) {
    var h = '<div class="chat-msg ' + (role === "user" ? "chat-user" : "chat-ai") + '">';
    if (think) {
      h += '<details class="chat-think"><summary>🧠 思考过程</summary><div>' +
        esc(think).replace(/\n/g, "<br>") + '</div></details>';
    }
    h += '<div class="chat-body">' + esc(content || "").replace(/\n/g, "<br>") + '</div></div>';
    return h;
  }

  function renderChatMsgs() {
    return _chatMsgs.map(function (m) {
      return chatBubble(m.role === "user" ? "user" : "ai", m.content, m.think || null);
    }).join("");
  }

  function setChatStatus(s) {
    document.getElementById("chat-status").textContent = s || "";
  }

  function scrollChatBottom() {
    var box = document.getElementById("chat-msgs");
    if (box) box.scrollTop = box.scrollHeight;
  }

  function setChatRunning(running) {
    var send = document.getElementById("btn-chat-send");
    if (send) send.disabled = running;
    var stop = document.getElementById("btn-chat-stop");
    if (stop) stop.style.display = running ? "" : "none";
    document.querySelectorAll(".chat-ops button.mini").forEach(function (b) {
      if (b.id !== "btn-chat-stop") b.disabled = running;
    });
  }

  function renderChatTopics() {
    var kw = (document.getElementById("chat-search").value || "").trim().toLowerCase();
    api("chat_topics", {}, "GET").then(function (r) {
      if (!r.ok) return;
      var el = document.getElementById("chat-topics");
      var topics = (r.topics || []).filter(function (t) {
        return !kw || (t.title || "").toLowerCase().indexOf(kw) >= 0;
      });
      if (!topics.length) {
        el.innerHTML = '<div class="dim" style="padding:10px 2px">还没有话题：点「＋ 新话题」创建，' +
          '或直接输入问题发送（自动创建）。</div>';
        return;
      }
      el.innerHTML = topics.map(function (t) {
        return '<div class="chat-topic' + (t.id === _chatTid ? " on" : "") +
          '" onclick="openChatTopic(\'' + t.id + '\')"><span class="tt">' +
          esc(t.title || "未命名") + '</span><span class="dim">' + t.msg_count + ' 条</span></div>';
      }).join("");
    });
  }

  function initChatTab() {
    renderChatTopics();
  }

  function openChatTopic(tid) {
    api("chat_open", { tid: tid }, "GET").then(function (r) {
      if (!r.ok) { alert(r.error); return; }
      _chatTid = tid;
      _chatTitle = r.title || "未命名";
      _chatMsgs = r.messages || [];
      document.getElementById("chat-title").textContent = _chatTitle;
      document.getElementById("chat-session").classList.remove("hidden");
      document.getElementById("chat-msgs").innerHTML = _chatMsgs.length ?
        renderChatMsgs() :
        '<div class="dim" style="text-align:center;padding:14px 4px">还没有消息，问点什么吧。</div>';
      setChatStatus("就绪。");
      renderChatTopics();
      scrollChatBottom();
    });
  }

  function startChatPoll(taskId) {
    _chatTask = taskId;
    _chatLast = 0;
    _chatStream = { think: "", body: "" };
    setChatRunning(true);
    setChatStatus("⏳ 正在请求…（可点「⏹ 停止」立即中断）");
    var box = document.getElementById("chat-msgs");
    _chatStreamNode = document.createElement("div");
    _chatStreamNode.className = "chat-msg chat-ai";
    _chatStreamNode.innerHTML =
      '<details class="chat-think" style="display:none"><summary>🧠 思考过程</summary><div></div></details>' +
      '<div class="chat-body"></div>';
    box.appendChild(_chatStreamNode);
    scrollChatBottom();
    chatPollOnce();
  }

  function chatPollOnce() {
    api("task_status", { task_id: _chatTask, since: _chatLast }, "GET").then(function (r) {
      if (r.error) { chatFinishRun(null, r.error); return; }
      if (r.logs && r.logs.length) {
        r.logs.forEach(function (l) {
          if (l.kind === "think") {
            _chatStream.think += l.msg;
            var dt = _chatStreamNode.querySelector("details");
            if (dt) { dt.style.display = ""; dt.querySelector("div").textContent = _chatStream.think; }
          } else if (l.kind === "chunk") {
            _chatStream.body += l.msg;
            var bd = _chatStreamNode.querySelector(".chat-body");
            if (bd) bd.innerHTML = esc(_chatStream.body).replace(/\n/g, "<br>");
          }
        });
        _chatLast = r.count;
        scrollChatBottom();
      }
      if (!r.done) {
        _chatTimer = setTimeout(chatPollOnce, 400);
        return;
      }
      chatFinishRun(r.result);
    }).catch(function (e) { chatFinishRun(null, "请求失败：" + e); });
  }

  function chatFinishRun(result, fallbackErr) {
    _chatTask = null;
    if (_chatTimer) { clearTimeout(_chatTimer); _chatTimer = null; }
    _chatStreamNode = null;
    _chatStream = null;
    setChatRunning(false);
    if (result && result.ok) {
      setChatStatus("✅ 完成 · 配置：" + (result.profile || "?") + "（" + (result.model || "?") +
        "）· 耗时 " + (result.elapsed || 0).toFixed(1) + "s · " + (result.text || "").length + " 字。");
    } else if (result && result.stopped) {
      setChatStatus("⏹ 已停止 · 配置：AI对话 · 耗时 " + (result.elapsed || 0).toFixed(1) + "s。已发送消息保留。");
    } else if (result && result.error) {
      setChatStatus("❌ 失败：" + result.error);
    } else {
      setChatStatus("❌ " + (fallbackErr || "任务失败。"));
    }
    // 服务端已把消息落库：整话题重载为权威状态（成功含 think、停止/失败保留已发送的用户消息）
    if (_chatTid) openChatTopic(_chatTid);
    renderChatTopics();
  }

  function chatSend() {
    if (_chatTask) { setChatStatus("正在生成中，可点「⏹ 停止」。"); return; }
    var input = document.getElementById("chat-input");
    var text = (input.value || "").trim();
    if (!text) return;
    input.value = "";
    if (!_chatTid) setChatStatus("⏳ 正在创建话题…");
    api("chat_send", {
      tid: _chatTid || "",
      text: text,
      use_project: document.getElementById("chat-use-project").checked,
      use_web: document.getElementById("chat-use-web").checked
    }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      _chatTid = r.tid;
      openChatTopic(r.tid);
      startChatPoll(r.task_id);
    }).catch(function (e) { setChatStatus("❌ 请求失败：" + e); });
  }

  function chatStop() {
    if (!_chatTask) return;
    api("chat_stop", { task_id: _chatTask }, "POST").then(function (r) {
      if (r.error) return;
      setChatStatus("⏹ 正在停止…（请求已断开）");
    });
  }

  function chatEditLast() {
    if (_chatTask) { setChatStatus("生成中，请先停止再操作。"); return; }
    if (!_chatTid || !_chatMsgs.length) { setChatStatus("没有可编辑的消息。"); return; }
    var last = _chatMsgs[_chatMsgs.length - 1];
    modal(
      '<div class="row"><b>编辑最后一条消息</b>' +
      (last.role === "user" ? '<div class="dim">用户消息，保存后自动重新生成。</div>'
                            : '<div class="dim">AI 回复文本，保存后如需重写点「🔄 重生成」。</div>') +
      '</div>' +
      '<textarea id="m-chat-edit" rows="8">' + esc(last.content || "") + '</textarea>' +
      '<div class="btnrow">' +
      '<button class="primary" onclick="chatEditSave()">保存</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function chatEditSave() {
    var content = document.getElementById("m-chat-edit").value;
    closeModal();
    api("chat_edit_last", { tid: _chatTid, content: content }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      openChatTopic(_chatTid);
      setChatStatus("已编辑。");
      if (r.role === "user") chatRegen();   // 桌面语义：编辑用户消息后自动重新生成
    });
  }

  function chatRegen() {
    if (_chatTask) return;
    if (!_chatTid || !_chatMsgs.length) { setChatStatus("没有可重新生成的消息。"); return; }
    api("chat_regen", {
      tid: _chatTid,
      use_project: document.getElementById("chat-use-project").checked,
      use_web: document.getElementById("chat-use-web").checked
    }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      startChatPoll(r.task_id);
    }).catch(function (e) { setChatStatus("❌ 请求失败：" + e); });
  }

  function chatContinue() {
    if (_chatTask) return;
    if (!_chatTid || !_chatMsgs.length) { setChatStatus("没有可续写的消息。"); return; }
    api("chat_continue", {
      tid: _chatTid,
      use_project: document.getElementById("chat-use-project").checked,
      use_web: document.getElementById("chat-use-web").checked
    }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      startChatPoll(r.task_id);
    }).catch(function (e) { setChatStatus("❌ 请求失败：" + e); });
  }

  function chatDeleteLast() {
    if (_chatTask) return;
    if (!_chatTid || !_chatMsgs.length) { setChatStatus("没有消息可删除。"); return; }
    api("chat_delete_last", { tid: _chatTid }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      openChatTopic(_chatTid);
      setChatStatus("已删除最后一条消息。");
    });
  }

  function newChatTopic() {
    modal(
      '<div class="row"><b>新话题</b></div>' +
      '<input id="m-chat-name" value="新话题" placeholder="话题名称（可稍后改名）">' +
      '<div class="btnrow">' +
      '<button class="primary" onclick="createChatTopic()">创建</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function createChatTopic() {
    var name = document.getElementById("m-chat-name").value.trim() || "新话题";
    closeModal();
    api("chat_create", { title: name }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      renderChatTopics();
      openChatTopic(r.tid);
    });
  }

  function renameChatTopic() {
    if (!_chatTid) return;
    modal(
      '<div class="row"><b>重命名话题</b></div>' +
      '<input id="m-chat-name" value="' + esc(_chatTitle || "新话题") + '">' +
      '<div class="btnrow">' +
      '<button class="primary" onclick="saveChatRename()">保存</button>' +
      '<button onclick="closeModal()">取消</button></div>');
  }

  function saveChatRename() {
    var name = document.getElementById("m-chat-name").value.trim();
    closeModal();
    if (!name) return;
    api("chat_rename", { tid: _chatTid, title: name }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      openChatTopic(_chatTid);
    });
  }

  function delChatTopic() {
    if (!_chatTid) return;
    if (!confirm("删除话题「" + _chatTitle + "」？该话题的所有消息将一并删除。")) return;
    api("chat_delete", { tid: _chatTid }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      _chatTid = null; _chatTitle = ""; _chatMsgs = [];
      document.getElementById("chat-session").classList.add("hidden");
      setChatStatus("话题已删除。");
      renderChatTopics();
    });
  }

  function closeChatSession() {
    if (_chatTask) { setChatStatus("正在生成中，请先停止。"); return; }
    _chatTid = null; _chatTitle = ""; _chatMsgs = [];
    document.getElementById("chat-session").classList.add("hidden");
    renderChatTopics();
  }

  function chatExport() {
    if (!_chatTid) { setChatStatus("请先打开一个话题再导出。"); return; }
    api("chat_export", { tid: _chatTid }, "POST").then(function (r) {
      if (r.error) { setChatStatus("❌ " + r.error); return; }
      setChatStatus(r.shared ? "已导出并弹出系统分享面板。" : "已导出：" + r.path);
    }).catch(function (e) { setChatStatus("❌ 请求失败：" + e); });
  }

  function chatClearInput() {
    document.getElementById("chat-input").value = "";
  }

  var chatInputEl = document.getElementById("chat-input");
  if (chatInputEl) {
    chatInputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); chatSend(); }
    });
  }

  // 导出全局（供 onclick 内联调用）
  window.renderChatTopics = renderChatTopics;
  window.openChatTopic = openChatTopic;
  window.newChatTopic = newChatTopic;
  window.createChatTopic = createChatTopic;
  window.renameChatTopic = renameChatTopic;
  window.saveChatRename = saveChatRename;
  window.delChatTopic = delChatTopic;
  window.closeChatSession = closeChatSession;
  window.chatSend = chatSend;
  window.chatStop = chatStop;
  window.chatEditLast = chatEditLast;
  window.chatEditSave = chatEditSave;
  window.chatRegen = chatRegen;
  window.chatContinue = chatContinue;
  window.chatDeleteLast = chatDeleteLast;
  window.chatExport = chatExport;
  window.chatClearInput = chatClearInput;
  window.setMode = setMode;
  window.doGenerate = doGenerate;
  window.doFinalize = doFinalize;
  window.doRegenerate = doRegenerate;
  window.toggleLogs = toggleLogs;
  window.restoreDraft = restoreDraft;
  window.delDraft = delDraft;
  window.newCharacter = newCharacter;
  window.openChar = openChar;
  window.saveChar = saveChar;
  window.delChar = delChar;
  window.setCharView = setCharView;
  window.restoreChar = restoreChar;
  window.aiCharacter = aiCharacter;
  window.aiCharacterBatch = aiCharacterBatch;
  window.aiClassify = aiClassify;
  window.openImportDialog = openImportDialog;
  window.doImportChar = doImportChar;
  window.batchStatus = batchStatus;
  window.doBatchStatus = doBatchStatus;
  window.switchSub = switchSub;
  // 中页签/大页切换由 HTML 内联 onclick 调用，必须挂到全局（否则点击静默失效）
  window.subTab = subTab;
  window.switchTab = switchTab;
  window.loadDrafts = loadDrafts;
  window.openChapter = openChapter;
  window.readFont = readFont;
  window.foreMark = foreMark;
  window.saveProject = saveProject;
  window.renderProjects = renderProjects;
  window.switchProject = switchProject;
  window.delProject = delProject;
  window.newProject = newProject;
  window.voiceInput = voiceInput;
  window.extractStyle = extractStyle;
  window.addLore = addLore;
  window.editLore = editLore;
  window.saveLore = saveLore;
  window.delLore = delLore;
  window.addPlan = addPlan;
  window.doAddPlan = doAddPlan;
  window.delPlan = delPlan;
  window.saveSettings = saveSettings;
  window.saveProfile = saveProfile;
  window.delProfile = delProfile;
  window.fetchModels = fetchModels;
  window.pickModel = pickModel;
  window.exportTxt = exportTxt;
  window.exportEpub = exportEpub;
  window.exportProject = exportProject;
  window.importProject = importProject;
  window.openDeai = openDeai;
  window.pickDeaiChapter = pickDeaiChapter;
  window.deaiRun = deaiRun;
  window.deaiApply = deaiApply;
  window.openEditorReview = openEditorReview;
  window.closeModal = closeModal;
  window.renderCharacters = renderCharacters;
  window.setOrient = setOrient;
  window.toggleOrientation = toggleOrientation;
  window.setConfirmBeatsCb = setConfirmBeatsCb;
  window.confirmBeatsSubmit = confirmBeatsSubmit;
  window.confirmBeatsSkip = confirmBeatsSkip;
  window.setChapterVol = setChapterVol;
  window.editChapter = editChapter;
  window.saveChapterEdit = saveChapterEdit;
  window.loadKnowledge = loadKnowledge;
  window.loadLog = loadLog;
  window.searchChapters = searchChapters;
  window.swapChapter = swapChapter;
  window.rewriteChapter = rewriteChapter;
  window.openVolManage = openVolManage;
  window.saveVolMerge = saveVolMerge;
  window.bookStart = bookStart;
  window.bookSubmit = bookSubmit;
  window.bookStop = bookStop;
  window.bookContinue = bookContinue;
  window.breakImportDoc = breakImportDoc;
  window.polishInput = polishInput;
  window.runPolish = runPolish;
  window.replacePolish = replacePolish;
  window.clearVoiceHist = clearVoiceHist;
  window.pickBreakTxt = pickBreakTxt;
  window.breakStart = breakStart;
  window.breakRestart = breakRestart;
  window.breakStop = breakStop;
  window.importRestart = importRestart;
  window.breakSave = breakSave;
  window.breakShowStyle = breakShowStyle;
  window.breakApply = breakApply;
  window.breakExport = breakExport;
  window.breakExportCur = breakExportCur;
  window.breakDelete = breakDelete;
  window.initStyleTab = initStyleTab;
  window.pickStyleTxt = pickStyleTxt;
  window.styleStart = styleStart;
  window.styleStop = styleStop;
  window.stylePromptsSave = stylePromptsSave;
  window.stylePresetSave = stylePresetSave;
  window.stylePresetLoad = stylePresetLoad;
  window.stylePresetDelete = stylePresetDelete;
  window.styleExport = styleExport;
  window.setBreakPar = setBreakPar;
  window.setBreakMode = setBreakMode;
  window.setBreakSmart = setBreakSmart;
  window.saveBreakSettings = saveBreakSettings;
  window.importToggle = importToggle;
  window.importSubmit = importSubmit;
  window.importStop = importStop;
  window.saveImportSettings = saveImportSettings;
  window.setImportPar = setImportPar;
  window.setImportMode = setImportMode;
  window.setImportSmart = setImportSmart;
  window.initImportTab = initImportTab;
  window.setUiTheme = setUiTheme;
  window.getUiZoom = getUiZoom;
  window.setUiZoom = setUiZoom;
  window.uiZoomStep = uiZoomStep;
  window.uiZoomReset = uiZoomReset;
  window.tutShow = tutShow;

  // v1.56 UI 布局 + 功能逻辑复刻 PC：新增页面/函数的全局绑定
  window.stopGenerate = stopGenerate;
  window.initGenerateTab = initGenerateTab;
  window.loadMainPrompt = loadMainPrompt;
  window.saveMainPrompt = saveMainPrompt;
  window.loadGenChapters = loadGenChapters;
  window.genOpenChapter = genOpenChapter;
  window.genEditChapter = genEditChapter;
  window.genReviewChapter = genReviewChapter;
  window.genDeleteChapter = genDeleteChapter;
  window.openSearchBox = openSearchBox;
  window.doSearchBox = doSearchBox;
  window.doRetitle = doRetitle;
  window.updateWorkCount = updateWorkCount;
  window.loadWorkList = loadWorkList;
  window.workOpenChapter = workOpenChapter;
  window.workNewChapter = workNewChapter;
  window.workSave = workSave;
  window.toggleWorkAutosave = toggleWorkAutosave;
  window.workContinue = workContinue;
  window.workStop = workStop;
  window.polishWork = polishWork;
  window.runPolishWork = runPolishWork;
  window.applyPolishWork = applyPolishWork;
  window.saveWorkCtx = saveWorkCtx;
  window.initWriteTab = initWriteTab;
  window.saveProjectFields = saveProjectFields;
  window.planStoryAI = planStoryAI;
  window.newProjectDirect = newProjectDirect;
  window.newProjectAI = newProjectAI;
  window.loadProofreadForm = loadProofreadForm;
  window.saveProofread = saveProofread;
  window.adaptSceneCards = adaptSceneCards;
  window.bookAutoToggle = bookAutoToggle;
  window.applyBookSettings = applyBookSettings;
  window.pickBookSceneCards = pickBookSceneCards;
  window.applyBookSceneCards = applyBookSceneCards;
  window.loadBranches = loadBranches;
  window.saveBranch = saveBranch;
  window.loadBranch = loadBranch;
  window.delBranch = delBranch;
  window.loadSceneCards = loadSceneCards;
  window.renderSceneLib = renderSceneLib;
  window.scOpenCard = scOpenCard;
  window.newSceneCard = newSceneCard;
  window.saveSceneCard = saveSceneCard;
  window.delSceneCard = delSceneCard;
  window.genSceneCard = genSceneCard;
  window.runGenSceneCard = runGenSceneCard;
  window.extractSceneCard = extractSceneCard;
  window.runExtractSceneCard = runExtractSceneCard;
  window.loadScenePrompt = loadScenePrompt;
  window.saveScenePrompt = saveScenePrompt;
  window.resetScenePrompt = resetScenePrompt;
  window.importSceneCardTxt = importSceneCardTxt;
  window.pickSceneCardTxt = pickSceneCardTxt;
  window.exportSceneCard = exportSceneCard;
  window.exportAllSceneCards = exportAllSceneCards;
  window.loadProjectSceneCards = loadProjectSceneCards;
  window.pickProjectSceneCards = pickProjectSceneCards;
  window.applyProjectSceneCards = applyProjectSceneCards;
  window.removeProjectSceneCard = removeProjectSceneCard;
  window.projCardToLibrary = projCardToLibrary;
  window.renderRoleRows = renderRoleRows;
  window.saveRoleRow = saveRoleRow;
  window.setReasonMode = setReasonMode;

  // 启动：应用记住的屏幕方向（未记过 = 横屏），并刷新方向按钮文案
  initUiTheme();
  refreshOrientBtn();
  // v1.53：应用记住的界面缩放（未记过 = 100%）
  applyUiZoom(getUiZoom());
  renderVoiceHist();
  // v0.28 一键成书/小说导入成项目为项目页内常驻卡片（顶部入口按钮已移除，默认展开，
  // 卡片内「收起」可折叠；顶部不再放重复按钮）
  initImportTab();
  // v1.52：始终把记住的方向交给原生侧（含 sensor=跟随系统），避免原生默认值与前端记忆不一致
  api("orientation", { mode: getOrient() }, "POST");
  switchTab("write");
})();
