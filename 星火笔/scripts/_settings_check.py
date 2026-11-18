# -*- coding: utf-8 -*-
"""v2.45 审查AI独立用途 + 模型列表拉取的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] pick_profile("review")：未指定时跟随主AI决断配置 / 显式指定后独立 / 全不指定回退当前
  [2] fetch_models：本地 mock 网关（/models 与 /v1/models、404 回退、401、去重排序、空 id 过滤、缺参报错）
  [3] 离屏 GUI：设置页用途分工 5 个下拉、模型输入为可编辑下拉、拉取按钮存在
运行：env\\python.exe _settings_check.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import config
import llm

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_settings_")
config.CONFIG_PATH = os.path.join(TMP, "config.json")   # 绝不碰真实 data/config.json


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def save_cfg(profiles, current, role_profiles=None):
    cfg = dict(config.DEFAULT_CONFIG)
    cfg["api_profiles"] = profiles
    cfg["current_profile"] = current
    if role_profiles is not None:
        cfg["role_profiles"] = role_profiles
    config.save_config(cfg)
    config._cache = None


def prof(name, key="k1"):
    return {"name": name, "base_url": "https://x.test/v1", "api_key": key,
            "model": "m", "role": "all"}


def test_pick_review():
    # 1) review 未指定、decide 指定 → 审查跟随主AI决断配置
    save_cfg([prof("决策号"), prof("当前号")], "当前号",
             role_profiles={"decide": "决策号"})
    check("review-未指定跟随decide",
          config.pick_profile("review")["name"] == "决策号",
          config.pick_profile("review")["name"])
    # 2) review 显式指定 → 独立于 decide
    save_cfg([prof("决策号"), prof("审查号"), prof("当前号")], "当前号",
             role_profiles={"decide": "决策号", "review": "审查号"})
    check("review-显式指定独立",
          config.pick_profile("review")["name"] == "审查号",
          config.pick_profile("review")["name"])
    # 3) review 显式指定而 decide 未指定 → review 独立、主AI回退通用
    save_cfg([prof("通用号"), prof("审查号"), prof("当前号")], "当前号",
             role_profiles={"review": "审查号"})
    check("review-独立于未指定的decide",
          config.pick_profile("review")["name"] == "审查号"
          and config.pick_profile("decide")["name"] == "通用号",
          "review=%s decide=%s" % (config.pick_profile("review")["name"],
                                   config.pick_profile("decide")["name"]))
    # 4) 全部未指定 → 回退首个可用通用配置（与 deai 等新用途既有语义一致）
    save_cfg([prof("通用号"), prof("当前号")], "当前号", role_profiles={})
    check("review-全不指定回退通用",
          config.pick_profile("review")["name"] == "通用号",
          config.pick_profile("review")["name"])
    # 5) 既有环节不受影响
    save_cfg([prof("决策号"), prof("写作号"), prof("当前号")], "当前号",
             role_profiles={"decide": "决策号", "write": "写作号"})
    check("review-既有环节不受影响",
          config.pick_profile("write")["name"] == "写作号"
          and config.pick_profile("decide")["name"] == "决策号", "")


class _MockHandler:
    def __init__(self, only_v1=False, status=200):
        self.only_v1 = only_v1
        self.status = status

    def handle(self, path):
        if self.status != 200:
            return self.status, b"{}"
        if self.only_v1:
            if path == "/v1/models":
                return 200, self.body
            return 404, b"{}"
        if path.endswith("/models"):
            return 200, self.body
        return 404, b"{}"

    body = json.dumps({"data": [{"id": "deepseek-chat"}, {"id": "qwen-plus"},
                                {"id": "qwen-plus"}, {"id": ""}]}).encode()


def start_mock(handler):
    import http.server

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            st, body = handler.handle(self.path)
            self.send_response(st)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_fetch_models():
    # base 含 /v1：直连 /v1/models
    srv = start_mock(_MockHandler(only_v1=True))
    base = "http://127.0.0.1:%d/v1" % srv.server_address[1]
    models = llm.fetch_models(base, "sk-test", timeout=5)
    check("fetch-含v1直连", models == ["deepseek-chat", "qwen-plus"], str(models))
    srv.shutdown()
    # base 不含 /v1：/models 404 → 回退 /v1/models
    srv = start_mock(_MockHandler(only_v1=True))
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    models = llm.fetch_models(base, "sk-test", timeout=5)
    check("fetch-v1回退", models == ["deepseek-chat", "qwen-plus"], str(models))
    srv.shutdown()
    # 网关报错（401）
    srv = start_mock(_MockHandler(status=401))
    base = "http://127.0.0.1:%d/v1" % srv.server_address[1]
    try:
        llm.fetch_models(base, "sk-bad", timeout=5)
        check("fetch-401报错", False, "应抛 LLMError")
    except llm.LLMError as e:
        check("fetch-401报错", "401" in str(e), str(e))
    srv.shutdown()
    # 缺参数
    try:
        llm.fetch_models("", "sk")
        check("fetch-缺地址报错", False, "应抛 LLMError")
    except llm.LLMError as e:
        check("fetch-缺地址报错", "base_url" in str(e), str(e))
    try:
        llm.fetch_models("https://x.test/v1", "")
        check("fetch-缺Key报错", False, "应抛 LLMError")
    except llm.LLMError as e:
        check("fetch-缺Key报错", "API Key" in str(e), str(e))


def test_gui():
    from PySide6.QtWidgets import QApplication, QComboBox
    import gui_settings
    qapp = QApplication.instance() or QApplication([])
    page = gui_settings.SettingsPage(None)
    page._refresh_role_combos()
    keys = set(page.role_combos.keys())
    check("GUI-用途分工11下拉", keys == {"decide", "write", "reason", "deai", "review",
                                        "break", "import", "style_a", "style_b",
                                        "style_c", "style_d"},
          str(sorted(keys)))
    check("GUI-模型为可编辑下拉", isinstance(page.e_model, QComboBox)
          and page.e_model.isEditable(), type(page.e_model).__name__)
    check("GUI-拉取按钮存在", hasattr(page, "fetch_btn")
          and page.fetch_btn.text() == "拉取模型", "")
    # 表单载入/保存走下拉文本
    save_cfg([prof("A号"), prof("B号")], "A号")
    page.refresh_all()
    page.list.setCurrentRow(0)
    page._load_row_to_form(0)
    check("GUI-表单载入模型", page.e_model.currentText() == "m", page.e_model.currentText())
    page._on_models_fetched(("ok", ["deepseek-chat", "qwen-plus"], {}))
    check("GUI-拉取结果填入", page.e_model.count() == 2
          and "deepseek-chat" in [page.e_model.itemText(i) for i in range(page.e_model.count())],
          "count=%d" % page.e_model.count())
    page.close()
    qapp.processEvents()


def test_parse_shapes():
    """v0.67 回归：/models 多种返回形状都能拉全（嵌套 dict / 顶层列表 / 单模型 / 键即 id）。"""
    from llm import _parse_model_list
    shapes = [
        ({"data": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]}, ["m1", "m2", "m3"]),
        ({"data": {"list": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]}}, ["m1", "m2", "m3"]),
        ({"data": {"models": [{"id": "m1"}, {"id": "m2"}]}}, ["m1", "m2"]),
        ({"models": {"list": [{"id": "m1"}, {"id": "m2"}]}}, ["m1", "m2"]),
        ([{"id": "m1"}, {"id": "m2"}, {"id": "m3"}], ["m1", "m2", "m3"]),
        ({"data": {"m1": {}, "m2": {}, "m3": {}}}, ["m1", "m2", "m3"]),
        ({"data": {"id": "m1", "object": "model"}}, ["m1"]),
        ({"data": ["m1", "m2", "m3"]}, ["m1", "m2", "m3"]),
        ({"data": [{"model": "m1"}, {"model": "m2"}]}, ["m1", "m2"]),
    ]
    ok = True
    for shape, expect in shapes:
        ids, _ctx = _parse_model_list(shape)
        if ids != expect:
            ok = False
            print("  shape %r -> %r != %r" % (shape, ids, expect))
    check("parse-嵌套/顶层/单对象形状拉全", ok, "")


def test_stream_error():
    """v0.69 回归：流式响应里出现 {"error": ...} chunk 应立即抛 LLMError（不再静默吞掉返回空）。"""
    import http.server
    err_body = b'data: {"error": {"message": "Model is unloaded."}}\n\n'

    class EH(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            if n:
                self.rfile.read(n)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), EH)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/v1" % srv.server_address[1]
    cfg = dict(config.DEFAULT_CONFIG)
    cfg["api_profiles"] = [{"name": "流错号", "base_url": base,
                            "api_key": "k", "model": "m", "role": "all"}]
    cfg["current_profile"] = "流错号"
    config.save_config(cfg)
    config._cache = None
    try:
        llm.chat_text("s", "u", profile="流错号", timeout=10)
        check("stream-error-应报错", False, "应抛 LLMError")
    except llm.LLMError as e:
        check("stream-error-快速报错", "Model is unloaded" in str(e), str(e)[:100])
    except Exception as e:
        check("stream-error-应报错", False, "非 LLMError：%r" % e)
    srv.shutdown()


def main():
    try:
        test_pick_review()
        test_fetch_models()
        test_parse_shapes()
        test_stream_error()
        test_gui()
    finally:
        config._cache = None
        shutil.rmtree(TMP, ignore_errors=True)
    fails = [r for r in RESULTS if not r[1]]
    print("-" * 50)
    if fails:
        print("FAILED %d/%d:" % (len(fails), len(RESULTS)))
        for n, _, d in fails:
            print("  FAIL %s %s" % (n, d))
        sys.exit(1)
    print("ALL_OK (%d checks)" % len(RESULTS))


if __name__ == "__main__":
    main()
