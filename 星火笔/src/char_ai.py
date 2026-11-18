# -*- coding: utf-8 -*-
"""角色推理：代入角色卡 + 信息库，推断行为。支持串行（照顾限速）与并行（追求速度）。"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import llm
import prompts


def reason_one(project, store, char_id, chapter_no, scene_focus, role_in_scene=""):
    card, lib = store.load_character(char_id)
    if card is None:
        return char_id, {"intent": "", "believes": [], "actions": [],
                         "speech_hints": [], "inner_conflict": "",
                         "_name": char_id, "_missing": True}
    sys, user = prompts.reason_character(card, lib, chapter_no, scene_focus,
                                         project, store, role_in_scene)
    data = llm.chat_json(sys, user, tag="char_reason_%s" % card.name, role="reason")
    if not isinstance(data, dict):
        data = {}
    data["_name"] = card.name
    return char_id, data


def run_inference(project, store, cast, chapter_no, scene_focus,
                  mode="sequential", max_workers=5, on_progress=None, stop_ev=None):
    """cast: [{"id":..,"role_in_scene":..,"notes":..}]

    v0.79.1 stop_ev：未传时继承调用线程的停止事件（llm.current_abort()）——
    ThreadPoolExecutor 子线程有自己的线程局部，主 worker 绑定的停止事件不会自动
    传给子线程；子线程推理（含 429 重试风暴）因此不响应点停止、主 worker 干等。
    这里统一在子线程内绑定/恢复，保证点停止能立即中断所有并行推理请求。
    """
    if stop_ev is None:
        stop_ev = llm.current_abort()
    inferences = {}
    if not cast:
        return inferences

    def done(cid):
        if on_progress:
            on_progress(cid)

    def _bound(c):
        """绑定停止事件后推理；恢复调用线程原有的绑定（串行模式在主 worker 线程调用，
        已有绑定则不重复设置/清理）。"""
        cur = llm.current_abort()
        if stop_ev is not None and cur is not stop_ev:
            llm.set_abort(stop_ev)
            try:
                return reason_one(project, store, c["id"], chapter_no,
                                  scene_focus, c.get("role_in_scene", ""))
            finally:
                llm.set_abort(cur)
        return reason_one(project, store, c["id"], chapter_no,
                          scene_focus, c.get("role_in_scene", ""))

    if mode == "parallel" and len(cast) > 1:
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(cast)))) as ex:
            futs = {}
            for c in cast:
                futs[ex.submit(_bound, c)] = c["id"]
            for f in as_completed(futs):
                cid = futs[f]
                try:
                    _, data = f.result()
                except Exception as e:
                    data = {"intent": "", "believes": [], "actions": [],
                            "speech_hints": [], "inner_conflict": "",
                            "_name": cid, "_error": str(e)}
                inferences[cid] = data
                done(cid)
    else:
        for c in cast:
            try:
                _, data = _bound(c)
            except Exception as e:
                data = {"intent": "", "believes": [], "actions": [],
                        "speech_hints": [], "inner_conflict": "",
                        "_name": c["id"], "_error": str(e)}
            inferences[c["id"]] = data
            done(c["id"])
    return inferences