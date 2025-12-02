# analyzer.py (整個檔案，請直接覆蓋)
import json
import re
import datetime
import time
from urllib.parse import urlparse

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

from tools import (
    check_url_safety,
    analyze_domain_age,
    check_url_patterns,
    extract_contact_info,
    detect_language_anomaly,
)
# Optional: 如果你有 SimplePhishingAnalysis，可以保留；本版本 LLM 直接回 JSON，我們以 dict 處理
# from models import SimplePhishingAnalysis

# ------------------ TOOL REGISTRY & CONFIG ------------------
TOOL_REGISTRY = {
    "check_url_safety": check_url_safety,
    "analyze_domain_age": analyze_domain_age,
    "check_url_patterns": check_url_patterns,
    "extract_contact_info": extract_contact_info,
    "detect_language_anomaly": detect_language_anomaly,
}

SAFE_DOMAINS = {"google.com", "google.com.tw", "microsoft.com", "facebook.com", "github.com", "gov.tw", "edu.tw"}
SUSPICIOUS_TLDS = {".xyz", ".top", ".loan", ".vip", ".click", ".buzz", ".shop", ".loan", ".info", ".ru", ".tk"}
LOG_PATH = "planner_tool_log.jsonl"
MODEL_NAME = "qwen3:8b"

# ------------------ PROMPT (few-shot, JSON, escaped braces) ------------------
plan_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         """
你是工具路由規劃器 (Tool Planner)。你的任務：讀取 visible_text 與 urls，**只決定要呼叫哪些工具**，不要猜測工具輸出內容。
回覆格式（僅要 JSON，一行或多行皆可）：
{{"calls":[{{"tool":"<name>","args":{{...}}}}, ...]}}
工具清單：check_url_safety, analyze_domain_age, check_url_patterns, extract_contact_info, detect_language_anomaly
args 可為空 dict（程式會補足），最多 3 個呼叫，無需工具時回傳 {{"calls":[]}}
"""),
        ("human", "visible_text:\n{visible}\n\nurls:\n{urls}\n"),
    ],
)

planner_llm = ChatOllama(model=MODEL_NAME, temperature=0)

# ------------------ HELPERS ------------------
def log_decision(record: dict):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

def extract_visible_text(html: str) -> str:
    html = re.sub(r"<(script|style|meta|link|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL)
    blocks = re.findall(r">(.*?)<", html)
    return "\n".join(x.strip() for x in blocks if x.strip())

def find_urls(text: str) -> list:
    return [m.group(1).rstrip('.,;') for m in re.finditer(r"(?i)\b((?:https?://|www\.)\S+)", text)]

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except:
        return ""

def is_suspicious_tld(domain: str) -> bool:
    return any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS)

def contains_brand_typo(domain: str) -> bool:
    # very simple heuristic: common brand substrings with minor typo patterns (1 char different)
    suspicious_patterns = ["paypa", "faceb00k", "chasebannk", "googl", "g00gle", "appleid", "banking-secure"]
    return any(p in domain for p in suspicious_patterns)

def is_safe_domain(domain: str) -> bool:
    return any(domain.endswith(sd) for sd in SAFE_DOMAINS)

# ------------------ PLANNER + TOOL INVOCATION ------------------
ALLOWED_TOOLS = set(TOOL_REGISTRY.keys())

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

def collect_tool_evidence(urls: list, visible: str) -> dict:
    """
    Planner-driven tool invocation with fallback heuristics.
    Returns a dict of tool_name -> result
    """
    urls_for_plan = "\n".join(urls[:10]) if urls else ""
    planner = plan_prompt | planner_llm

    # decide calls
    calls = []
    try:
        plan_resp = planner.invoke({"visible": visible[:2000], "urls": urls_for_plan})
        content = plan_resp.content if hasattr(plan_resp, "content") else str(plan_resp)
        m = re.search(r"(\{[\s\S]*\})", content)
        json_text = m.group(1) if m else content
        raw = json.loads(json_text)
        calls = validate_plan(raw)
    except Exception:
        calls = []

    # fallback: if no calls and URL suspicious, at least check url patterns & domain age
    if not calls and urls and not is_safe_domain(domain_of(urls[0])):
        calls = [
            {"tool":"check_url_patterns","args":{"urls": urls}},
            {"tool":"analyze_domain_age","args":{"domain": domain_of(urls[0])}}
        ]

    log_decision({
        "time": datetime.datetime.utcnow().isoformat(),
        "phase": "planner",
        "visible_snippet": visible[:300],
        "urls": urls[:3],
        "planner_calls": calls
    })

    # execute calls and collect evidence
    evidence = {}
    for call in calls:
        tool_name = call["tool"]
        args = call.get("args", {}) or {}
        # autofill
        if tool_name == "check_url_safety" and not args.get("url") and urls:
            args["url"] = urls[0]
        if tool_name == "analyze_domain_age" and not args.get("domain") and urls:
            args["domain"] = domain_of(urls[0])
        if tool_name == "check_url_patterns" and not args.get("urls"):
            args["urls"] = urls or []
        if tool_name in ("extract_contact_info","detect_language_anomaly") and not args.get("text"):
            args["text"] = visible[:2000]

        func = TOOL_REGISTRY.get(tool_name)
        try:
            # 工具由 @tool 裝飾，需調用其 invoke 方法
            if hasattr(func, 'invoke'):
                res = func.invoke(args)
            else:
                res = func(**args)
        except Exception as e:
            res = {"error": str(e)}
        evidence[tool_name] = res

    log_decision({
        "time": datetime.datetime.utcnow().isoformat(),
        "phase": "evidence",
        "visible_snippet": visible[:300],
        "urls": urls[:3],
        "evidence": evidence
    })
    return evidence

# ------------------ RULE-BASED SCORING ------------------
def rule_score(visible: str, urls: list, evidence: dict) -> dict:
    """
    Compute rule-based risk score and reasons.
    Returns: {"score": int, "reasons": [...], "hard_flag": bool}
    """
    score = 0
    reasons = []
    hard_flag = False

    v = visible.lower()
    # keyword groups
    urgent = ["立即", "馬上", "盡快", "緊急", "限時", "逾期", "警告", "必須"]
    auth = ["驗證", "重新驗證", "帳號", "密碼", "登入", "解除限制", "確認身分", "身份驗證"]
    money = ["付款", "轉帳", "刷卡", "金額", "匯款", "銀行", "信用卡"]
    click = ["點擊", "點此", "連結", "href"]

    cnt_urgent = sum(1 for k in urgent if k in v)
    cnt_auth = sum(1 for k in auth if k in v)
    cnt_money = sum(1 for k in money if k in v)
    cnt_click = sum(1 for k in click if k in v)

    # weight and reasons
    if cnt_auth:
        score += cnt_auth * 3
        reasons.append(f"身份/驗證要求 x{cnt_auth}")
    if cnt_money:
        score += cnt_money * 3
        reasons.append(f"金錢/付款相關 x{cnt_money}")
    if cnt_urgent:
        score += cnt_urgent * 2
        reasons.append(f"緊急語氣 x{cnt_urgent}")
    if cnt_click:
        score += cnt_click * 1
        reasons.append(f"要求點擊 x{cnt_click}")

    # URL based checks
    for u in urls:
        d = domain_of(u)
        if not d:
            continue
        # 優先採用安全規則：如果是安全域名，跳過可疑檢查
        if is_safe_domain(d):
            reasons.append(f"安全域名：{d}")
            # 對安全域名減分（降低風險）
            score -= 1
        else:
            # 只在非安全域名時才檢查可疑特徵
            if is_suspicious_tld(d) or contains_brand_typo(d) or any(x in d for x in ["verify", "secure", "account", "login", "update", "reset"]):
                score += 4
                reasons.append(f"疑似可疑域名：{d}")
            # very high risk for credential phishing patterns
            if any(x in d for x in ["-secure-", "login-", "verify-", "account-"]):
                score += 5
                reasons.append(f"域名含 phishing pattern：{d}")

    # Evidence-based bumps (tools)
    for k, v in evidence.items():
        sv = str(v).lower()
        if "suspicious" in sv or "phish" in sv or "malicious" in sv or "blacklist" in sv:
            score += 4
            reasons.append(f"工具 {k} 標記可疑")
        # domain age returned as very new (example structure) -> bump
        if "created" in sv and "days" in sv:
            # best-effort parse small age -> bump if < 90 days
            m = re.search(r"(\d+)\s*day", sv)
            if m and int(m.group(1)) < 90:
                score += 3
                reasons.append(f"{k}：網域年齡小於90天")

    # Hard rules: if both auth + urgent present -> high risk regardless
    if cnt_auth >= 1 and cnt_urgent >= 1:
        hard_flag = True
        reasons.append("同時出現身份驗證要求與緊急語氣（強制標記）")

    # clamp and return
    return {"score": max(score, 0), "reasons": reasons, "hard_flag": hard_flag}

# ------------------ LLM CHAIN (analysis with Chain-of-Thought) ------------------
def build_cot_thinking_chain():
    """第一步：讓 LLM 進行自由文字思考（較高 temperature）"""
    llm = ChatOllama(model=MODEL_NAME, temperature=0.5)  # Higher temperature for exploration
    prompt = ChatPromptTemplate.from_messages([
        ("system", """
你是一個資安分析 AI。請逐步分析以下信息，並詳細說明你的推理過程。
請自由地表達你的思考，不要限制於任何特定格式，就像在進行內部推理。

你需要考慮以下幾個方面：
1. 內文中的可疑特徵（緊急語氣、身份驗證要求、金錢相關等）
2. URL 的特徵（域名、TLD、可疑模式等）
3. 工具檢測結果中的警告標記
4. 整體綜合判斷

請逐點列出你的觀察和推理。
"""),
        ("human", """
=== 網頁內文 ===
{visible_text}

=== URL ===
{urls}

=== 工具檢測結果 ===
{evidence}

請詳細說明你的分析思路和推理過程，但請勿直接給出結論。
""")
    ])
    return prompt | llm


def build_analysis_chain():
    """第二步：基於 CoT 思考結果，給出嚴格 JSON 判斷"""
    llm = ChatOllama(model=MODEL_NAME, temperature=0)  # deterministic
    prompt = ChatPromptTemplate.from_messages([
        ("system", """
你是一個資安分析 AI，請基於前面的思考過程進行最終判斷。
請嚴格回傳 JSON（只輸出 JSON），格式如下（務必使用合法 JSON）：
{{
    "is_potential_phishing": true/false,
    "risk_level": "high"|"medium"|"low",
    "explanation": ["短理由一","短理由二"],
    "confidence": 0-100
}}
只根據提供的思考過程與原始內文進行判斷，不要加入外部未提供資訊。
若不確定，請給出中間值 confidence 並用 "medium"。
"""),
        ("human", """
=== 網頁內文 ===
{visible_text}

=== URL ===
{urls}

=== 工具檢測結果 ===
{evidence}

=== 先前的推理過程 ===
{cot_thinking}

基於以上思考過程，請給出最終的 JSON 判斷。
""")
    ])
    return prompt | llm

# ------------------ ANALYZE (主流程) ------------------
def analyze_deep(html_text: str) -> dict:
    start = time.time()
    visible = extract_visible_text(html_text)
    urls = find_urls(html_text)
    urls_str = "\n".join(urls[:10]) if urls else "（無網址）"

    # Collect evidence
    evidence = collect_tool_evidence(urls, visible)

    # Compute rule score
    r = rule_score(visible, urls, evidence)
    score = r["score"]
    reasons = r["reasons"]
    hard_flag = r["hard_flag"]

    # Build evidence_text to LLM (structured but concise)
    def serialize_evidence(ev: dict) -> str:
        parts = []
        for k, v in ev.items():
            s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            parts.append(f"{k}: {s}")
        return "\n".join(parts) if parts else "（無工具結果）"

    evidence_text = serialize_evidence(evidence)

    # ========== STEP 1: Chain-of-Thought (Thinking) ==========
    cot_thinking = ""
    try:
        cot_chain = build_cot_thinking_chain()
        cot_resp = cot_chain.invoke({
            "visible_text": visible[:3000],
            "urls": urls_str,
            "evidence": evidence_text,
        })
        cot_thinking = cot_resp.content if hasattr(cot_resp, "content") else str(cot_resp)
        
        log_decision({
            "time": datetime.datetime.utcnow().isoformat(),
            "phase": "cot_thinking",
            "cot_output": cot_thinking[:1000]  # 記錄前 1000 字
        })
    except Exception as e:
        cot_thinking = f"推理過程出錯：{str(e)}"
        log_decision({"time": datetime.datetime.utcnow().isoformat(), "phase": "cot_error", "error": str(e)})

    # ========== STEP 2: Final Analysis (JSON) ==========
    content = ""
    try:
        chain = build_analysis_chain()
        resp = chain.invoke({
            "visible_text": visible[:3000],
            "urls": urls_str,
            "evidence": evidence_text,
            "cot_thinking": cot_thinking,
        })
        content = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        content = ""
        log_decision({"time": datetime.datetime.utcnow().isoformat(), "phase": "llm_error", "error": str(e)})

    # Try parse LLM JSON, fallback to minimal structure
    parsed = {}
    try:
        m = re.search(r"(\{[\s\S]*\})", content)
        jtext = m.group(1) if m else content
        parsed = json.loads(jtext)
    except Exception:
        parsed = {"is_potential_phishing": False, "risk_level": "low", "explanation": ["AI 判斷正常或回傳錯誤"], "confidence": 30}

    # RULE-OVERRIDE LOGIC (rule has priority)
    # If hard_flag -> force high risk
    final_decision = parsed.get("is_potential_phishing", False)
    final_level = parsed.get("risk_level", "low")
    final_conf = parsed.get("confidence", 30)
    final_explanations = parsed.get("explanation", [])
    if isinstance(final_explanations, str):
        final_explanations = re.split(r"[,、;，]", final_explanations)

    # If rule says hard_flag, override
    if hard_flag:
        final_decision = True
        final_level = "high"
        final_conf = max(final_conf, 85)
        final_explanations = ["規則判定：身份驗證+緊急語氣（強制）"] + final_explanations

    # If rule score high enough, override/boost
    if score >= 6 and not final_decision:
        final_decision = True
        final_level = "high"
        final_conf = max(final_conf, 80)
        final_explanations = ["規則分數高（{} 分）".format(score)] + final_explanations
    elif 4 <= score < 6:
        # medium
        if final_level == "low":
            final_level = "medium"
        final_conf = max(final_conf, 55)
        final_explanations = final_explanations or ["規則分數提示中度風險"]

    # If LLM says safe but evidence contains suspicious domain -> boost suspicion
    if not final_decision:
        for u in urls:
            d = domain_of(u)
            if is_suspicious_tld(d) or contains_brand_typo(d):
                final_decision = True
                final_level = "high"
                final_conf = max(final_conf, 75)
                final_explanations = [f"域名疑似高風險：{d}"] + final_explanations
                break

    # Normalize
    final_explanations = [e.strip() for e in final_explanations if str(e).strip()]
    if not final_explanations:
        final_explanations = ["未發現可疑特徵"]

    end = time.time()
    elapsed = end - start

    # Log full context for debugging / retraining
    log_decision({
        "time": datetime.datetime.utcnow().isoformat(),
        "phase": "final",
        "visible_snippet": visible[:500],
        "urls": urls[:5],
        "evidence": evidence,
        "rule": r,
        "cot_thinking": cot_thinking[:500],  # 記錄思考過程（前 500 字）
        "llm_raw": content,
        "final": {
            "is_potential_phishing": final_decision,
            "risk_level": final_level,
            "confidence": final_conf,
            "explanation": final_explanations
        },
        "elapsed": elapsed
    })

    return {
        "is_potential_phishing": final_decision,
        "risk_level": final_level,
        "confidence": final_conf,
        "explanation": final_explanations[:3],
        "evidence": evidence,
        "cot_thinking": cot_thinking,  # 完整思考過程直接回傳
        "elapsed_time": elapsed
    }
