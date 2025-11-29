#!/usr/bin/env python3
"""
Chain-of-Thought 演示腳本

說明：
1. 第一步：LLM 進行自由文字思考（temperature=0.5，較高）
2. 第二步：LLM 基於思考結果給出嚴格 JSON 判斷（temperature=0，確定性）

這樣既能取得可解釋的推理過程，又能保留結構化輸出。
"""

import json
from analyzer import analyze_deep

# 測試案例 1：看起來像釣魚郵件的 HTML
test_html_1 = """
<html>
<body>
    <h1>緊急：您的帳戶已被限制</h1>
    <p>親愛的客戶，</p>
    <p>我們偵測到您的帳戶出現異常活動。為了保護您的帳號安全，我們需要您立即進行身份驗證。</p>
    <p><a href="https://verify-secure-banking.xyz/login">點擊此處立即驗證您的帳戶</a></p>
    <p>請勿延遲，逾期可能導致帳戶被永久凍結。</p>
    <p>感謝您的配合！</p>
    <p>銀行客服團隊</p>
</body>
</html>
"""

# 測試案例 2：正常網頁
test_html_2 = """
<html>
<body>
    <h1>歡迎來到 Google</h1>
    <p>Google 是全球最受信任的搜尋引擎。</p>
    <p><a href="https://www.google.com">瀏覽 Google</a></p>
    <p>©2024 Google Inc. 版權所有</p>
</body>
</html>
"""

def print_result(title: str, result: dict):
    print(f"\n{'='*60}")
    print(f"[{title}]")
    print(f"{'='*60}")
    print(f"是否為釣魚網站：{result['is_potential_phishing']}")
    print(f"風險等級：{result['risk_level']}")
    print(f"信心度：{result['confidence']}%")
    print(f"\n解釋：")
    for i, exp in enumerate(result.get('explanation', []), 1):
        print(f"  {i}. {exp}")
    
    if 'cot_thinking' in result and result['cot_thinking'].strip():
        print(f"\n[推理過程（Chain-of-Thought）]")
        print(result['cot_thinking'][:500])
        if len(result['cot_thinking']) > 500:
            print("... (已截斷)")
    
    print(f"\n耗時：{result['elapsed_time']:.2f} 秒")

if __name__ == "__main__":
    print("正在進行 Chain-of-Thought 分析...")
    print("(此演示會調用 Ollama 模型，確保模型已啟動)")
    
    # 測試案例 1：釣魚郵件
    print("\n[分析案例 1：疑似釣魚郵件]")
    result_1 = analyze_deep(test_html_1)
    print_result("測試案例 1", result_1)
    
    # 測試案例 2：正常網頁
    print("\n[分析案例 2：正常網頁]")
    result_2 = analyze_deep(test_html_2)
    print_result("測試案例 2", result_2)
    
    # 輸出為 JSON（便於程式使用）
    print("\n\n[完整 JSON 輸出]")
    print("=== 案例 1 ===")
    print(json.dumps(result_1, ensure_ascii=False, indent=2))
    print("\n=== 案例 2 ===")
    print(json.dumps(result_2, ensure_ascii=False, indent=2))
