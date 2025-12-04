# Chain-of-Thought (CoT) 流程圖

本文檔展示蝸牛檢測系統的 CoT 邏輯流程。

---

## 🎯 整體 CoT 分析流程（高層次）

```mermaid
graph TD
    Start([開始：收到 HTML 內容]) --> Extract["📄 步驟1：提取資訊<br/>- 抽取可見文字<br/>- 解析所有 URL<br/>- 空目前工具証據為空"]
    
    Extract --> Rule["⚖️ 步驟2：規則評分<br/>- 計算關鍵字分數<br/>- 檢查 URL/域名<br/>- 判定硬規則<br/>得分: 0-10"]
    
    Rule --> CoT["💭 步驟3：CoT思考<br/>LLM 自由文字推理<br/>- 分析可疑特徵<br/>- 推導風險因子<br/>溫度: 0.5"]
    
    CoT --> JSON["🔍 步驟4：結構化判斷<br/>LLM 輸出 JSON<br/>- is_potential_phishing<br/>- risk_level<br/>- confidence (0-100)<br/>溫度: 0"]
    
    JSON --> Merge["🔀 步驟5：規則-模型融合<br/>根據信心閾值(70%)決策"]
    
    Merge --> HighConf{模型信心<br/>≥ 70%?}
    
    HighConf -->|是：高信心| PriorityModel["✓ 模型判斷優先<br/>規則提供補充理由<br/>信心: +5%"]
    
    HighConf -->|否：低信心| PriorityRule["📋 規則可調整<br/>根據規則分數<br/>決定最終結論"]
    
    PriorityModel --> HardCheck{硬規則<br/>hard_flag<br/>存在?}
    PriorityRule --> HardCheck
    
    HardCheck -->|是| Override["🚨 強制覆蓋<br/>is_potential_phishing: true<br/>risk_level: high<br/>confidence: 85%"]
    
    HardCheck -->|否| FinalMerge["✅ 最終融合結果"]
    
    Override --> FinalMerge
    
    FinalMerge --> Output["📊 輸出結果<br/>- 最終判斷<br/>- 風險等級<br/>- 信心分數<br/>- 理由列表"]
    
    Output --> Log["📝 記錄到日誌<br/>planner_tool_log.jsonl"]
    
    Log --> End([結束])
    
    style Start fill:#e1f5ff
    style End fill:#e1f5ff
    style Extract fill:#fff3e0
    style Rule fill:#f3e5f5
    style CoT fill:#e8f5e9
    style JSON fill:#e8f5e9
    style Merge fill:#fce4ec
    style Override fill:#ffebee
    style FinalMerge fill:#f1f8e9
    style Output fill:#e0f2f1
    style Log fill:#ede7f6
```

---

## 📋 詳細流程：規則評分（步驟2）

```mermaid
graph TD
    RuleStart([規則評分開始]) --> KeywordCheck["🔑 關鍵字分析<br/>計算 4 類關鍵字出現次數:<br/>- 緊急語氣: ×2 分<br/>- 身份驗證: ×3 分<br/>- 金錢相關: ×3 分<br/>- 要求點擊: ×1 分"]
    
    KeywordCheck --> URLCheck["🌐 URL/域名檢查"]
    
    URLCheck --> SafeDomain{域名是否<br/>在安全列表?}
    
    SafeDomain -->|是| Deduct["✓ 安全域名<br/>評分 -1"]
    SafeDomain -->|否| SuspCheck["⚠️ 檢查可疑特徵:<br/>- 可疑 TLD<br/>- 品牌仿冒<br/>- Phishing Pattern<br/>評分 +4～+5"]
    
    Deduct --> JSCheck["🔍 JavaScript 檢測<br/>檢查代碼混淆:<br/>- eval(), atob()<br/>- innerHTML, document.write<br/>- 十六進位變數<br/>- String.fromCharCode<br/>評分: 1-5 分"]
    
    SuspCheck --> JSCheck
    
    JSCheck --> EvidenceScore["💾 工具證據評分<br/>檢查各工具標記:<br/>- suspicious/phishing<br/>- domain age<br/>評分: +3～+4"]
    
    EvidenceScore --> HardRule["⚡ 硬規則檢查<br/>if 身份驗證 ≥ 1<br/>AND 緊急語氣 ≥ 1<br/>then hard_flag = True"]
    
    HardRule --> RuleEnd([規則評分結束<br/>返回: score, reasons, hard_flag])
    
    style RuleStart fill:#fff3e0
    style KeywordCheck fill:#ffe0b2
    style URLCheck fill:#ffe0b2
    style SafeDomain fill:#ffcc80
    style Deduct fill:#a5d6a7
    style SuspCheck fill:#ef9a9a
    style JSCheck fill:#f48fb1
    style EvidenceScore fill:#ce93d8
    style HardRule fill:#ffab91
    style RuleEnd fill:#fff3e0
```

---

## 💭 詳細流程：Chain-of-Thought（步驟3）

```mermaid
graph TD
    CotStart([CoT 推理開始]) --> Input["📥 輸入:<br/>- 可見文字<br/>- URL 列表<br/>- 工具結果<br/>- 規則分數"]
    
    Input --> Think1["💡 第一層思考<br/>『題目理解』<br/>- 這是什麼內容?<br/>- 主要目的是?<br/>- 目標受眾是?"]
    
    Think1 --> Think2["📍 第二層思考<br/>『資訊抽取』<br/>- 內文有哪些可疑詞?<br/>- 有幾個外部連結?<br/>- 域名是否陌生?"]
    
    Think2 --> Think3["🔍 第三層思考<br/>『特徵分析』<br/>- 緊急感是否異常高?<br/>- 是否要求驗證資訊?<br/>- 涉及金錢交易?<br/>- 代碼是否可疑混淆?"]
    
    Think3 --> Think4["⚖️ 第四層思考<br/>『推理演繹』<br/>根據特徵組合:<br/>- 高風險組合?<br/>- 中風險跡象?<br/>- 或正常內容?"]
    
    Think4 --> Think5["📊 第五層思考<br/>『信心評估』<br/>根據證據充分度:<br/>- 特徵明確?<br/>- 跡象一致?<br/>給出信心百分比"]
    
    Think5 --> Output["✍️ 輸出推理文字<br/>（自由文字，含完整推理過程<br/>溫度 0.5：有創意但連貫）"]
    
    Output --> CotEnd([CoT 推理結束<br/>返回: cot_thinking 文字])
    
    style CotStart fill:#e8f5e9
    style Input fill:#c8e6c9
    style Think1 fill:#a5d6a7
    style Think2 fill:#81c784
    style Think3 fill:#66bb6a
    style Think4 fill:#4caf50
    style Think5 fill:#388e3c
    style Output fill:#2e7d32
    style CotEnd fill:#e8f5e9
```

---

## 🔍 詳細流程：結構化判斷（步驟4）

```mermaid
graph TD
    JSONStart([結構化判斷開始]) --> Input["📥 輸入:<br/>- 完整 CoT 推理文字<br/>- 原始內容<br/>- URL 和證據<br/>溫度 0.0<br/>（完全確定性）"]
    
    Input --> Parse["🔨 LLM 解析<br/>根據 CoT 推理內容<br/>輸出結構化 JSON:<br/>{<br/>&nbsp;&nbsp;is_potential_phishing: boolean<br/>&nbsp;&nbsp;risk_level: 'low'|'medium'|'high'<br/>&nbsp;&nbsp;explanation: [理由1, 理由2]<br/>&nbsp;&nbsp;confidence: 0-100<br/>}"]
    
    Parse --> Validate["✓ 驗證 JSON<br/>- 語法正確?<br/>- 所有欄位存在?<br/>- 數值範圍合理?"]
    
    Validate --> Valid{JSON<br/>有效?}
    
    Valid -->|否| Fallback["⚠️ 回退方案<br/>is_potential_phishing: false<br/>risk_level: low<br/>confidence: 30<br/>explanation: ['AI 判斷出錯']"]
    
    Valid -->|是| JSONEnd([結構化判斷結束<br/>返回: parsed JSON])
    
    Fallback --> JSONEnd
    
    style JSONStart fill:#e0f2f1
    style Input fill:#b2dfdb
    style Parse fill:#80cbc4
    style Validate fill:#4db6ac
    style Valid fill:#26a69a
    style Fallback fill:#ff7043
    style JSONEnd fill:#e0f2f1
```

---

## 🔀 詳細流程：規則-模型融合決策（步驟5）

```mermaid
graph TD
    MergeStart([融合決策開始]) --> ExtractModel["📋 提取模型判斷<br/>from JSON:<br/>- decision (boolean)<br/>- risk_level<br/>- confidence<br/>- explanations"]
    
    ExtractModel --> CheckHard{硬規則<br/>hard_flag<br/>= True?}
    
    CheckHard -->|是| HardOverride["🚨 硬規則優先<br/>覆蓋所有:<br/>is_potential_phishing: true<br/>risk_level: high<br/>confidence: 85%<br/>加註: ✓ 強制規則"]
    
    CheckHard -->|否| CheckConf{模型信心<br/>≥ 70%?}
    
    CheckConf -->|是：高信心| HighConf["✅ 模型優先<br/>保持模型判斷<br/>rule 提供補充<br/>confidence: +5%<br/>加註: ⚠️ 規則補充理由"]
    
    CheckConf -->|否：低信心| RuleInfluence["📋 規則決策"]
    
    RuleInfluence --> RuleScore{rule<br/>評分}
    
    RuleScore -->|≥ 7| FollowRule["跟隨規則判斷<br/>confidence: 75%<br/>加註: 📋 規則建議"]
    
    RuleScore -->|5-6| MediumRisk["調整為中度<br/>risk_level: medium<br/>confidence: 55%"]
    
    RuleScore -->|4-5| LightRisk["調整風險等級<br/>confidence: 50%"]
    
    RuleScore -->|< 4| KeepOriginal["保持模型判斷<br/>微調信心度"]
    
    HardOverride --> CheckDomain["💎 額外檢查<br/>（僅在低信心時）<br/>可疑域名？"]
    
    HighConf --> CheckDomain
    
    FollowRule --> CheckDomain
    MediumRisk --> CheckDomain
    LightRisk --> CheckDomain
    KeepOriginal --> CheckDomain
    
    CheckDomain -->|發現高風險域名| DomainFlag["🔴 域名高風險<br/>is_potential_phishing: true<br/>risk_level: high<br/>confidence: 75%"]
    
    CheckDomain -->|域名安全| Final["✅ 最終融合結果"]
    
    DomainFlag --> Final
    
    Final --> MergeEnd([融合決策結束<br/>返回: 最終判斷])
    
    style MergeStart fill:#fce4ec
    style ExtractModel fill:#f8bbd0
    style CheckHard fill:#f48fb1
    style HardOverride fill:#ec407a
    style CheckConf fill:#ec407a
    style HighConf fill:#a5d6a7
    style RuleInfluence fill:#ffcc80
    style RuleScore fill:#ffe0b2
    style FollowRule fill:#ff9800
    style MediumRisk fill:#ffb74d
    style LightRisk fill:#ffcc80
    style KeepOriginal fill:#fff9c4
    style CheckDomain fill:#f1f8e9
    style DomainFlag fill:#ef5350
    style Final fill:#81c784
    style MergeEnd fill:#fce4ec
```

---

## 📊 決策矩陣：信心 vs 規則評分

```
┌─────────────────┬────────────────────┬────────────────────┬────────────────────┐
│ 模型信心 / 規則 │     規則 ≤ 3       │    規則 4-6        │      規則 ≥ 7      │
├─────────────────┼────────────────────┼────────────────────┼────────────────────┤
│  high (≥ 70%)   │ ✅ 信任模型        │ ✅ 信任模型        │ ⚠️ 規則補充理由   │
│                 │ conf: 保持         │ + 規則補充       │ conf: +5%         │
├─────────────────┼────────────────────┼────────────────────┼────────────────────┤
│  low (< 70%)    │ ✓ 保持低風險      │ 📋 調整 medium    │ 🔀 跟隨規則       │
│                 │ conf: 保持         │ conf: 55%         │ conf: 75%         │
└─────────────────┴────────────────────┴────────────────────┴────────────────────┘

硬規則 hard_flag = true 時：無視所有上述邏輯，強制 high risk + 85% conf
```

---

## 🔄 完整範例：一份蝸牛檢測分析流程

### 輸入：可疑郵件 HTML

```html
<body>
  <p>親愛的客戶，您的帳戶已被鎖定。請立即點此驗證您的身份，否則您的帳戶將被永久關閉。</p>
  <a href="https://verify-account-secure.xyz/login">驗證帳戶</a>
</body>
```

### 執行流程

```
1️⃣ 提取資訊
   ├─ 可見文字: "親愛的客戶, 帳戶已被鎖定, 立即點此驗證..."
   ├─ URL: ["https://verify-account-secure.xyz/login"]
   └─ 工具結果: {} (暫時停用)

2️⃣ 規則評分
   ├─ 緊急語氣: "立即" ×1 → +2 分
   ├─ 身份驗證: "驗證身份" ×1 → +3 分
   ├─ 域名檢查: verify-account-secure.xyz
   │  └─ 可疑 TLD (.xyz) → +4 分
   │  └─ Phishing pattern ("verify-account") → +5 分
   ├─ hard_flag: 身份驗證 ≥1 AND 緊急語氣 ≥1 → TRUE
   └─ 最終評分: 2+3+4+5 = 14 分 (clamped to 10+) ⚡ hard_flag

3️⃣ CoT 推理（温度 0.5）
   推理文字:
   "
   這份內容看起來像是一份登入驗證通知。
   
   關鍵信號：
   - 使用了『立即』『永久關閉』等強烈緊急語氣
   - 要求用戶『驗證身份』，這是蝸牛常見的社交工程手法
   - 連結指向 verify-account-secure.xyz，一個陌生域名
   - .xyz TLD 是廉價域名，常被蝸牛利用
   - 域名名稱包含『verify-account-secure』，模仿正規銀行/平臺
   
   綜合判斷：這極有可能是蝸牛郵件。信心: 95%
   "

4️⃣ 結構化判斷（温度 0.0）
   JSON:
   {
     "is_potential_phishing": true,
     "risk_level": "high",
     "confidence": 95,
     "explanation": [
       "緊急語氣 + 身份驗證要求",
       "可疑域名: verify-account-secure.xyz",
       "Phishing pattern 偵測到"
     ]
   }

5️⃣ 規則-模型融合
   ├─ 模型信心: 95% ≥ 70% → 高信心
   ├─ hard_flag: TRUE → 強制執行
   └─ 最終決策:
       is_potential_phishing: TRUE ✓ (hard_flag override)
       risk_level: HIGH
       confidence: 85% (hard_flag 強制設定)
       explanations: [
         "✓ 規則判定：身份驗證+緊急語氣（強制優先）",
         "緊急語氣 + 身份驗證要求",
         "可疑域名: verify-account-secure.xyz",
         "Phishing pattern 偵測到"
       ]

📝 日誌記錄:
   {
     "time": "2025-12-04T12:34:56Z",
     "phase": "final",
     "rule": {"score": 14, "hard_flag": true, ...},
     "cot_thinking": "推理文字...",
     "llm_raw": "JSON 原始輸出...",
     "final": {...最終決策...},
     "elapsed": 2.345
   }
```

---

## 📐 架構說明

| 流程步驟 | 組件 | 輸入 | 輸出 | 溫度 | 用途 |
|---------|------|------|------|------|------|
| 1 | 提取 | HTML | 可見文字, URL | - | 資訊標準化 |
| 2 | 規則評分 | 文字, URL | 評分, hard_flag | - | 快速風險評估 |
| 3 | CoT 推理 | 文字, URL, 規則分數 | 推理文字 | 0.5 | 自由推理，富有變化 |
| 4 | 結構化判斷 | 文字, URL, CoT | JSON | 0.0 | 確定性輸出 |
| 5 | 融合決策 | JSON, 規則分數, hard_flag | 最終判斷 | - | 邏輯整合 |

---

## 🎓 CoT 的優勢

1. **透明性**：每一步推理都可見，易於調試和改進
2. **魯棒性**：即使單個信號模糊，多層推理可互相驗證
3. **可解釋性**：用戶可看到 AI 如何思考
4. **避免誤判**：信心低時，規則可提供第二層驗證
5. **適應性**：温度控制讓推理既準確又不過於死板

---

## 📝 註記

- 本系統目前 **tools 呼叫已停用**，所以 `evidence` 為空 dict
- 若要恢復工具呼叫，取消註解 `analyzer.py` 中的 `from tools import ...` 並恢復 `TOOL_REGISTRY`
- 所有決策及中間步驟都記錄在 `planner_tool_log.jsonl`，方便離線分析
- CoT 方法適合高風險決策；若只需快速判斷，可跳過步驟 3（推理），直接進行結構化判斷
