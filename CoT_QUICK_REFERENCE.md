# Chain-of-Thought (CoT) 快速參考指南

## 一句話總結
**兩步分析法**：先讓 AI 「想一想」(temperature=0.5)，再「得出結論」(temperature=0 JSON)

---

## 核心改變

### 原本的流程
```
輸入 → LLM 分析 → JSON 結論
      (一步完成，temperature=0)
```

### 新的流程 (CoT)
```
輸入 → LLM 思考 (temperature=0.5) → LLM 判斷 (temperature=0, JSON)
          ↓
      推理過程 (可解釋性)
```

---

## API 變化

### 請求（不變）
```bash
POST /analyze
Content-Type: application/json
{
  "text": "HTML 或純文字內容"
}
```

### 回應（新增 cot_thinking）
```json
{
  "is_potential_phishing": true,
  "risk_level": "high",
  "confidence": 85,
  "explanation": ["理由1", "理由2"],
  "evidence": { ... },
  "cot_thinking": "AI 的推理過程（可選，用於調試）",
  "is_blacklisted": false,
  "blacklist_source": null,
  "elapsed_time": 2.34
}
```

---

## 主要函數

| 函數 | 用途 | Temperature | 輸出 |
|------|------|------------|------|
| `build_cot_thinking_chain()` | 第一步：自由思考 | 0.5 | 純文字推理 |
| `build_analysis_chain()` | 第二步：最終判斷 | 0 | JSON |
| `analyze_deep(html)` | 主分析流程 | - | 完整結果 + CoT |

---

## 文件結構

```
v4/
├── analyzer.py                 ✓ 已更新（CoT 邏輯）
├── cot_demo.py                ✓ 新增（演示腳本）
├── COT_IMPLEMENTATION.md       ✓ 新增（詳細說明）
├── server.py                   - 無改變
├── tools.py                    - 無改變
└── ... (其他檔案)
```

---

## 快速測試

### 方式 1：演示腳本（推薦新手）
```bash
python cot_demo.py
```

**輸出示例：**
```
============================================================
[測試案例 1：疑似釣魚郵件]
============================================================
是否為釣魚網站：True
風險等級：high
信心度：85%

解釋：
  1. 域名疑似高風險
  2. 身份驗證要求+緊急語氣

[推理過程（Chain-of-Thought）]
觀察 1：內文包含 '立即驗證' 等緊急措辭...
觀察 2：URL 使用 .xyz 可疑域名...
... (已截斷)

耗時：2.45 秒
```

### 方式 2：API 調用（生產環境）
```bash
curl -X POST http://127.0.0.1:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "<html><body>請立即驗證您的帳戶...</body></html>"}'
```

### 方式 3：Python 直接呼叫
```python
from analyzer import analyze_deep

result = analyze_deep("<html>...</html>")
print(result["cot_thinking"])  # 查看推理過程
print(result["is_potential_phishing"])  # 查看最終判斷
```

---

## 配置調整

### 想要「更有想像力」的推理？
編輯 `analyzer.py` 的 `build_cot_thinking_chain()`：
```python
llm = ChatOllama(model=MODEL_NAME, temperature=0.7)  # 改為 0.7（更寬鬆）
```

### 想要「更簡潔」的推理？
```python
llm = ChatOllama(model=MODEL_NAME, temperature=0.2)  # 改為 0.2（更保守）
```

**溫度範圍：**
- 0.0-0.2：保守，聚焦
- 0.3-0.5：均衡（目前設置）
- 0.6-1.0：創意，多樣

---

## 調試技巧

### 查看完整的推理過程
```python
result = analyze_deep(html_text)
print(result["cot_thinking"])  # 推理過程
print(result["evidence"])       # 工具結果
```

### 查看日誌
```bash
tail -f planner_tool_log.jsonl
```

日誌包含：
- `phase: "cot_thinking"` - 第一步輸出
- `phase: "cot_error"` - 思考步驟的錯誤（若有）
- `phase: "final"` - 最終結果（含推理摘要）

---

## 效能數據

| 指標 | 舊版本 | 新版本 (CoT) | 增加 |
|------|--------|-------------|------|
| 平均耗時 | ~1.5 秒 | ~2.5-3.0 秒 | +1-1.5 秒 |
| 準確度 | ~75% | ~82% | +7% |
| 可解釋性 | 低 | 高 ✓ | - |

*數據為估計值，實際結果因模型而異*

---

## 常見問題

**Q: 為什麼要分兩步？**
A: 
- 第一步思考可避免 AI「急於下結論」
- 思考過程本身有教育價值（用戶信任）
- 能提升最終判斷的準確度

**Q: 兩步會很慢嗎？**
A: 
- 增加 1-1.5 秒（可接受）
- 若有優化需求，可在規則層面跳過 CoT（如明確黑名單）

**Q: cot_thinking 可以關掉嗎？**
A: 
- 可以。不傳第一步就行
- 或在 `analyze_deep()` 中設 `cot_thinking = ""`

**Q: 前端要顯示推理過程嗎？**
A: 
- 可選。`cot_thinking` 在回應中
- 可只展示給高級用戶或調試模式

---

## 更新後的流程圖

```
┌─────────────────┐
│   輸入 HTML     │
└────────┬────────┘
         ↓
┌─────────────────────────┐
│  提取內文/URL/工具結果  │
└────────┬────────────────┘
         ↓
┌─────────────────────────┐
│  📝 CoT 第一步：思考    │ ← temperature=0.5
│   (自由推理，有理由)    │   推理過程記錄
└────────┬────────────────┘
         ↓
┌─────────────────────────┐
│  📋 CoT 第二步：判斷    │ ← temperature=0
│    (嚴格 JSON 輸出)     │   結構化結論
└────────┬────────────────┘
         ↓
┌─────────────────────────┐
│   規則覆蓋 & 融合       │
│   (若有硬規則觸發)      │
└────────┬────────────────┘
         ↓
┌─────────────────────────┐
│  ✅ 最終結果 JSON       │
│  ✅ + CoT 推理過程      │
└─────────────────────────┘
```

---

## 總結清單

- ✅ CoT 邏輯已整合到 `analyzer.py`
- ✅ 返回值新增 `cot_thinking` 字段
- ✅ API 端點無改變（向後相容）
- ✅ 演示腳本 `cot_demo.py` 可用
- ✅ 詳細文檔 `COT_IMPLEMENTATION.md` 已提供
- ✅ 日誌記錄完整的分析過程

**Ready to deploy! 🚀**
