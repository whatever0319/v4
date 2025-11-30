# server.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import datetime
import os

from html_utils import extract_relevant_html, extract_urls
from blacklist import (
    load_blacklist,
    is_blacklisted,
    check_blacklist_source,
    add_to_user_blacklist,
    delete_from_user_blacklist,
    get_user_blacklist,
    clear_user_blacklist
)
from analyzer import analyze_deep

app = Flask(__name__)
CORS(app)

# Background task support for async analysis
from concurrent.futures import ThreadPoolExecutor
import uuid
from threading import Lock

# Simple in-memory store: task_id -> {status: processing|done|error, result: dict or None}
TASKS = {}
TASKS_LOCK = Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=2)

if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    load_blacklist("phishtank.csv")

def log(title):
    print("\n==========", title, "==========")

@app.route("/user_blacklist", methods=["GET"])
def get_blacklist_route():
    return jsonify({"success": True, "list": get_user_blacklist()})

@app.route("/add_blacklist", methods=["POST"])
def add_blacklist_route():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"success": False, "message": "網址不可為空"})
    ok = add_to_user_blacklist(url)
    return jsonify({"success": ok, "message": "已成功加入" if ok else "加入失敗"})

@app.route("/delete_blacklist", methods=["POST"])
def delete_blacklist_route():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"success": False, "message": "網址不可為空"})
    ok = delete_from_user_blacklist(url)
    return jsonify({"success": ok, "message": "已刪除" if ok else "找不到此網址"})
@app.route('/clear_blacklist', methods=['POST'])
def handle_clear_blacklist():
    success = clear_user_blacklist()
    if success:
        return jsonify({"success": True, "message": "使用者黑名單已全部清空"})
    else:
        return jsonify({"success": False, "message": "清空失敗，請檢查伺服器日誌"})
@app.route("/analyze", methods=["POST"])
def analyze_route():
    t0 = time.time()
    data = request.json or {}
    text = data.get("text", "")
    # 前端可透過 include_cot 控制是否要完整的思考過程（預設 True）
    include_cot = bool(data.get("include_cot", True))

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("收到分析請求")
    print(f"時間：{now}")
    print(f"IP  ：{request.remote_addr}")
    print(f"長度：{len(text)}")

    urls = extract_urls(text)
    for u in urls:
        if is_blacklisted(u):
            source = check_blacklist_source(u)
            elapsed = round(time.time() - t0, 2)
            log("黑名單命中 → 直接返回")
            print(f"黑名單網址：{u}")
            print(f"來源：{source}")
            print(f"耗時：{elapsed} 秒")

            return jsonify({
                "is_potential_phishing": True,
                "is_blacklisted": True,
                "blacklist_source": source,   # ✅ official / user
                "explanation": f"偵測到黑名單惡意網址：{u}",
                "elapsed_time": elapsed
            })

    cleaned = extract_relevant_html(text) if "<html" in text.lower() else text
    result = analyze_deep(cleaned)

    # 非黑名單也要固定回這兩欄，讓前端好判斷
    result["is_blacklisted"] = False
    result["blacklist_source"] = None

    # 如果前端不需要完整 CoT，移除大型欄位以節省頻寬
    if not include_cot:
        # 保留摘要欄位，但刪除完整版（若存在）
        if "cot_thinking_full" in result:
            del result["cot_thinking_full"]

    elapsed = round(result["elapsed_time"], 2)
    log("分析完成（深度檢測）")
    print(f"耗時：{elapsed} 秒")
    print(f"分析結果：{result['is_potential_phishing']}")

    return jsonify(result)


@app.route("/analyze_async", methods=["POST"])
def analyze_async_route():
    """Start analysis in background and return a task_id immediately.

    Frontend can poll `/analyze_result/<task_id>` to get status/result.
    """
    data = request.json or {}
    text = data.get("text", "")
    include_cot = bool(data.get("include_cot", True))

    task_id = str(uuid.uuid4())
    with TASKS_LOCK:
        TASKS[task_id] = {"status": "processing", "result": None}

    def _run_and_store(tid, txt, icot):
        try:
            res = analyze_deep(txt)
            # remove full cot if frontend didn't request it
            if not icot and "cot_thinking_full" in res:
                del res["cot_thinking_full"]
            with TASKS_LOCK:
                TASKS[tid]["status"] = "done"
                TASKS[tid]["result"] = res
        except Exception as e:
            with TASKS_LOCK:
                TASKS[tid]["status"] = "error"
                TASKS[tid]["result"] = {"error": str(e)}

    EXECUTOR.submit(_run_and_store, task_id, text, include_cot)
    return jsonify({"task_id": task_id, "status": "processing"})


@app.route("/analyze_result/<task_id>", methods=["GET"])
def analyze_result_route(task_id):
    with TASKS_LOCK:
        info = TASKS.get(task_id)
    if not info:
        return jsonify({"error": "unknown task_id"}), 404
    return jsonify(info)

if __name__ == "__main__":
    print("Flask 後端啟動中（Debug Mode）...")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
