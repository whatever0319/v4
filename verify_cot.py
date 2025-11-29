#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡化的 CoT 驗證腳本 - 檢查功能是否正常
"""

import json
import sys
import os

# 修正 Windows 編碼
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from analyzer import analyze_deep

# 簡單測試
test_html = """
<html>
<body>
    <h1>立即驗證帳戶</h1>
    <p>親愛的客戶，請立即點擊以下連結驗證您的帳號，否則將被凍結。</p>
    <a href="https://verify-account.xyz/login">驗證帳戶</a>
</body>
</html>
"""

print("=" * 60)
print("Chain-of-Thought 簡化驗證")
print("=" * 60)

try:
    result = analyze_deep(test_html)
    
    print("\n✅ 分析成功！")
    print(f"   釣魚判定：{result['is_potential_phishing']}")
    print(f"   風險等級：{result['risk_level']}")
    print(f"   信心度：{result['confidence']}%")
    print(f"   耗時：{result['elapsed_time']:.2f} 秒")
    
    if result.get('cot_thinking'):
        print(f"\n✅ CoT 推理過程記錄：{len(result['cot_thinking'])} 字")
    
    if result.get('evidence'):
        print(f"✅ 工具檢測結果記錄：{len(result['evidence'])} 個")
    
    print("\n🎉 CoT 實現驗證完成！")
    
except Exception as e:
    print(f"\n❌ 錯誤：{str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
