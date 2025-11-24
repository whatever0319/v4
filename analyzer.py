import json
import re
import datetime
import time
from urllib.parse import urlparse

from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

from tools import (
    check_url_safety,
    analyze_domain_age,
    check_url_patterns,
    extract_contact_info,
    detect_language_anomaly,
)
from models import SimplePhishingAnalysis

# ------------------ 工具與白名單 ------------------
TOOL_REGISTRY = {
    "check_url_safety": check_url_safety,
    "analyze_domain_age": analyze_domain_age,
    "check_url_patterns": check_url_patterns,
    "extract_contact_info": extract_contact_info,
    "detect_language_anomaly": detect_language_anomaly,
}

SAFE_DOMAINS = {"google.com", "microsoft.com", "apple.com", "gov.tw", "edu.tw"}

# ------------------ Planner Prompt ------------------
plan_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
你是工具路由規劃器 (Tool Planner)。你的任務：讀取 visible_text 與 urls，**只決定要呼叫哪些工具**，不要猜測工具輸出內容。
回覆格式：
{"calls":[{"tool":"<name>","args":{...}}, ...]}
只使用以下工具：check_url_safety, analyze_domain_age, check_url_patterns, extract_contact_info, detect_language_anomaly
args 可為空 dict，後續程式會補
最多 3 個呼叫，無需工具時回傳 {"calls":[]}
"""
        ),
        ("human", "visible_text:\n{visible}\n\nurls:\n{urls}\n"),
    ],
    template_format="jinja2",
)

planner_llm = ChatOllama(model="qwen3:8b", temperature=0)

ALLOWED_TOOLS = set(TOOL_REGISTRY.keys())
LOG_PATH = "planner_tool_log.jsonl"

# ------------------ 輔助函式 ------------------
def validate_plan(raw_plan: dict) -> list:
    if not isinstance(raw_plan, dict):
        return []
    calls = raw_plan.get("calls")
    if not isinstance(calls, list):
        return []
    valid_calls = []
    for c in calls[:3]:
        if not isinstance(c, dict):
            continue
        tool = c.get("tool")
        args = c.get("args", {}) or {}
        if tool not in ALLOWED_TOOLS:
            continue
        if not isinstance(args, dict):
            continue
        valid_calls.append({"tool": tool, "args": args})
    return valid_calls

def is_safe_domain(url):
    try:
        domain = urlparse(url).netloc
        return any(domain.endswith(sd) for sd in SAFE_DOMAINS)
    except:
        return False

def log_decision(record: dict):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except:
        pass

def extract_visible_text(html: str) -> str:
    html = re.sub(r"<(script|style|meta|link|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL)
    blocks = re.findall(r">(.*?)<", html)
    return "\n".join(x.strip() for x in blocks if x.strip())

def find_urls(text: str) -> list:
    return [m.group(1) for m in re.finditer(r"(?i)\b((?:https?://|www\.)\S+)", text)]

# ------------------ 核心：工具執行 & 收集 Evidence ------------------
def collect_tool_evidence(urls: list, visible: str) -> dict:
    planner = plan_prompt | planner_llm
    urls_for_plan = "\n".join(urls[:10]) if urls else ""

    calls = []
    for attempt in range(2):
        try:
            plan_resp = planner.invoke({"visible": visible[:2000], "urls": urls_for_plan})
            content = plan_resp.content if hasattr(plan_resp, "content") else str(plan_resp)
            m = re.search(r"(\{[\s\S]*\})", content)
            json_text = m.group(1) if m else content
            raw = json.loads(json_text)
            calls = validate_plan(raw)
            if calls:
                break
        except:
            continue

    # fallback heuristics
    if not calls and urls and not is_safe_domain(urls[0]):
        calls = [
            {"tool":"check_url_patterns","args":{"urls": urls}},
            {"tool":"analyze_domain_age", "args":{"domain": urlparse(urls[0]).netloc}}
        ]

    log_decision({
        "time": datetime.datetime.utcnow().isoformat(),
        "visible_snippet": visible[:300],
        "urls": urls[:3],
        "planner_calls": calls
    })

    evidence = {}
    for call in calls:
        tool_name = call["tool"]
        args = call["args"]
        if tool_name == "check_url_safety" and not args.get("url") and urls:
            args["url"] = urls[0]
        if tool_name == "analyze_domain_age" and not args.get("domain") and urls:
            if is_safe_domain(urls[0]):
                continue
            args["domain"] = urlparse(urls[0]).netloc
        if tool_name == "check_url_patterns" and not args.get("urls"):
            args["urls"] = urls or []
        if tool_name in ("extract_contact_info","detect_language_anomaly") and not args.get("text"):
            args["text"] = visible[:2000]

        func = TOOL_REGISTRY[tool_name]
        try:
            res = func(**args)
        except Exception as e:
            res = {"error": str(e)}
        evidence[tool_name] = res

    log_decision({
        "time": datetime.datetime.utcnow().isoformat(),
        "visible_snippet": visible[:300],
        "urls": urls[:3],
        "planner_calls": calls,
        "evidence": evidence
    })

    return evidence

# ------------------ 分析 LLM Chain ------------------
def build_analysis_chain():
    llm = ChatOllama(model="qwen3:8b", temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """
你是一個資安分析 AI。
依據 Evidence 回傳 JSON：
{{
    "is_potential_phishing": true/false,
    "explanation": "最多三個短理由，用中文、每點 ≤12 字"
}}
僅使用 Evidence 中資訊，不得編造。
如果沒有可疑特徵，explanation="未發現可疑特徵"
"""),
        ("human", """
=== 可見文字 ===
{visible_text}

=== URL ===
{urls}

=== 工具檢測結果 (Evidence) ===
{evidence}

請依 Evidence 回傳 JSON。
""")
    ])
    return prompt | llm

# ------------------ 最終分析函式 ------------------
def analyze_deep(html_text: str) -> dict:
    start = time.time()

    visible = extract_visible_text(html_text)
    urls = find_urls(html_text)
    urls_str = "\n".join(urls[:10]) if urls else "（無網址）"

    evidence_dict = collect_tool_evidence(urls, visible)
    evidence_text = "\n".join(f"{k}: {v}" for k, v in evidence_dict.items()) if evidence_dict else "（所有工具檢測正常）"

    chain = build_analysis_chain()
    resp = chain.invoke({
        "visible_text": visible[:3000],
        "urls": urls_str,
        "evidence": evidence_text,
    })

    try:
        parsed = json.loads(resp.content if hasattr(resp, "content") else str(resp))
    except Exception:
        parsed = {"is_potential_phishing": False, "explanation": "未發現可疑特徵"}

    raw = parsed.get("explanation", "")
    parts = [p.strip("- 、,，") for p in re.split(r"[\n、,，]+", raw) if p.strip()]
    explanation_final = "、".join(parts[:3]) if parts else "未發現可疑特徵"

    end = time.time()

    return {
        "is_potential_phishing": parsed.get("is_potential_phishing", False),
        "explanation": explanation_final,
        "evidence": evidence_dict,
        "elapsed_time": end - start
    }