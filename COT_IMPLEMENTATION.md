# Chain-of-Thought (CoT) 實現說明

## 概述
已在 `analyzer.py` 中實現 **Chain-of-Thought** 模式，分兩個步驟進行分析：

1. **第一步（思考過程）**：讓 LLM 自由地進行推理和分析
   - Model: `qwen3:8b`
   - Temperature: `0.5`（較高，允許更多的探索和解釋性思考）
   - 輸出：純文字推理過程，不限制格式

2. **第二步（最終判斷）**：基於思考結果，給出結構化 JSON 結論
   - Model: `qwen3:8b`
   - Temperature: `0`（確定性，只輸出 JSON）
   - 輸出：嚴格的 JSON 格式

---

## 實現細節

### 1. 新增的函數

#### `build_cot_thinking_chain()`
```python
def build_cot_thinking_chain():
    """第一步：讓 LLM 進行自由文字思考（較高 temperature）"""
    llm = ChatOllama(model=MODEL_NAME, temperature=0.5)
    # ... prompt 用來讓 LLM 逐步分析
```

**特點：**
- Temperature 設為 0.5（相比 0 更加寬鬆）
- Prompt 要求模型「逐步說明推理」，不要直接給結論
- 考慮四個方面：
  1. 內文中的可疑特徵
  2. URL 的特徵
  3. 工具檢測結果
  4. 綜合判斷邏輯

#### `build_analysis_chain()`
```python
def build_analysis_chain():
    """第二步：基於 CoT 思考結果，給出嚴格 JSON 判斷"""
    llm = ChatOllama(model=MODEL_NAME, temperature=0)
    # ... prompt 要求嚴格 JSON 輸出
```

**特點：**
- Temperature 設為 0（確定性）
- Prompt 明確要求「只輸出 JSON」
- 接收前一步的推理過程作為輸入

### 2. 修改的流程

在 `analyze_deep()` 函數中：

```
[輸入] HTML 文本
  ↓
[步驟 1] 抽取內文、URL、工具檢測結果
  ↓
[步驟 2] LLM 思考過程 (CoT)
  - 調用 build_cot_thinking_chain()
  - 得到自由文字推理
  ↓
[步驟 3] LLM 最終判斷 (JSON)
  - 調用 build_analysis_chain()
  - 傳入 cot_thinking 作為額外上下文
  - 得到結構化 JSON
  ↓
[步驟 4] 規則覆蓋邏輯
  - 將 LLM 判斷與規則分數結合
  ↓
[輸出] 最終分析結果 + CoT 推理過程
```

### 3. 新的返回值

`analyze_deep()` 現在返回：

```json
{
  "is_potential_phishing": boolean,
  "risk_level": "high" | "medium" | "low",
  "confidence": 0-100,
  "explanation": ["理由1", "理由2", ...],
  "evidence": { ... },
  "cot_thinking": "推理過程摘要（前 800 字）",
  "elapsed_time": float
}
```

新增的 `cot_thinking` 字段包含 LLM 第一步的推理過程。

---

## 使用方式

### 1. API 調用（不變）

前端/客戶端調用 `/analyze` 端點，結果中會多出 `cot_thinking` 字段：

```bash
curl -X POST http://127.0.0.1:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "<html>...</html>"}'
```

返回示例：
```json
{
  "is_potential_phishing": true,
  "risk_level": "high",
  "confidence": 85,
  "explanation": ["域名疑似高風險", "身份驗證要求+緊急語氣"],
  "is_blacklisted": false,
  "blacklist_source": null,
  "cot_thinking": "觀察 1：內文包含 '立即驗證' 等緊急措辭...\n觀察 2：URL 使用 .xyz TLD...",
  "elapsed_time": 2.34
}
```

### 2. 演示腳本

執行 `cot_demo.py` 查看 CoT 效果：

```bash
python cot_demo.py
```

輸出包括：
- 推理過程（Chain-of-Thought）
- 最終判斷
- 完整 JSON 結果

---

## 優勢

### 可解釋性 (Interpretability)
- 用戶可以看到 LLM 的思考過程
- 了解 AI 是如何得出結論的
- 便於除錯和改進

### 準確度 (Accuracy)
- 兩步分析比單步更全面
- 第一步探索，第二步總結，降低「幻覺」風險
- 思考結果可提升最終判斷的品質

### 靈活性 (Flexibility)
- 第一步可調整 temperature，控制多樣性
- 第二步確保輸出格式嚴格
- 可選擇是否向用戶展示推理過程

---

## 日誌記錄

`planner_tool_log.jsonl` 現在記錄：

```json
{
  "time": "2024-...",
  "phase": "cot_thinking",
  "cot_output": "...推理過程的前 1000 字..."
}
```

和

```json
{
  "time": "2024-...",
  "phase": "final",
  "cot_thinking": "...推理過程的前 500 字...",
  "final": { ... }
}
```

便於後期分析和模型微調。

---

## 性能考量

### 額外延遲
- 多了一次 LLM 調用（思考步驟）
- 期望增加 1-3 秒的處理時間

### 優化建議
1. 若需加速，可在 Planner 層面就標記為「明確安全/危險」，跳過 CoT
2. 可以緩存常見模式的 CoT 結果
3. 非同步處理思考步驟，若超時則使用預設

---

## 自訂配置

在 `analyzer.py` 中修改以下參數：

```python
# CoT 第一步 (思考)
cot_chain = build_cot_thinking_chain()
# 若要改變 temperature，編輯 build_cot_thinking_chain()
llm = ChatOllama(model=MODEL_NAME, temperature=0.5)  # ← 改這裡 (0.2-0.7 推薦)

# 最終分析第二步 (JSON)
chain = build_analysis_chain()
# 一般保持 temperature=0 以確保格式一致
llm = ChatOllama(model=MODEL_NAME, temperature=0)  # ← 保持不變
```

---

## 總結

✅ **Chain-of-Thought 已實現**
- 兩步分析：思考 → 判斷
- 可解釋性 + 結構化輸出
- 融合了規則系統的優勢
- 記錄完整分析日誌供後續優化
