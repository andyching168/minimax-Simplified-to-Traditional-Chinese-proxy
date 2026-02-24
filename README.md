# MiniMax M2.5 繁體中文 Proxy Server

將 MiniMax M2.5 的輸出自動轉換為繁體中文的透明 Proxy Server。
專為 Claude Code 等使用 Anthropic SDK 的工具設計。

## 架構

```
Claude Code / Anthropic SDK
           ↓
    本 Proxy Server (轉繁體中文)
           ↓
    MiniMax API (api.minimax.io)
```

## 功能特色

- **透明代理**：完全相容 Anthropic API 格式
- **自動繁體轉換**：使用 OpenCC 將簡體中文轉換為台灣正體
- **程式碼保護**：程式碼區塊不會被轉換
- **串流支援**：完整支援 SSE 串流回應
- **詞彙轉換**：同時轉換大陸用語為台灣用語（軟件→軟體）

## 快速開始

### 1. 安裝

```bash
cd minimax-claude-proxy
pip install -r requirements.txt
```

### 2. 啟動 Proxy Server

```bash
python main.py
```

Server 會在 `http://localhost:8000` 啟動。

### 3. 設定 Claude Code

在 Claude Code 的設定檔中加入：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8000",
    "ANTHROPIC_AUTH_TOKEN": "<你的_MINIMAX_API_KEY>",
    "ANTHROPIC_MODEL": "MiniMax-M2.5",
    "ANTHROPIC_SMALL_FAST_MODEL": "MiniMax-M2.5",
    "API_TIMEOUT_MS": "300000"
  }
}
```

或設定環境變數：

```bash
export ANTHROPIC_BASE_URL=http://localhost:8000
export ANTHROPIC_AUTH_TOKEN=your_minimax_api_key
export ANTHROPIC_MODEL=MiniMax-M2.5
```

## 使用其他 Anthropic SDK 工具

### Python

```python
import anthropic

client = anthropic.Anthropic(
    api_key="your-minimax-api-key",
    base_url="http://localhost:8000"
)

message = client.messages.create(
    model="MiniMax-M2.5",
    max_tokens=4096,
    messages=[
        {"role": "user", "content": "請解釋什麼是 API"}
    ]
)

print(message.content[0].text)  # 輸出為繁體中文
```

### Node.js

```javascript
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({
  apiKey: 'your-minimax-api-key',
  baseURL: 'http://localhost:8000'
});

const message = await client.messages.create({
  model: 'MiniMax-M2.5',
  max_tokens: 4096,
  messages: [
    { role: 'user', content: '請解釋什麼是 API' }
  ]
});

console.log(message.content[0].text);  // 繁體中文
```

### cURL

```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-minimax-api-key" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "MiniMax-M2.5",
    "max_tokens": 4096,
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'
```

## 可用模型

| 模型名稱 | 說明 |
|---------|------|
| MiniMax-M2.5 | 旗艦模型，性能最強 |
| MiniMax-M2.5-highspeed | 高速版，約 100 TPS |
| MiniMax-M2.1 | 多語言編程優化 |
| MiniMax-M2.1-highspeed | M2.1 高速版 |
| MiniMax-M2 | 基礎模型 |

## 環境變數

| 變數 | 說明 | 預設值 |
|-----|------|-------|
| `HOST` | 監聽位址 | `0.0.0.0` |
| `PORT` | 監聽埠 | `8000` |
| `MINIMAX_BASE_URL` | MiniMax API 位址 | `https://api.minimaxi.com/anthropic` |
| `API_TIMEOUT_MS` | 超時時間（毫秒） | `300000` |

## 繁體中文轉換

使用 [OpenCC](https://github.com/BYVoid/OpenCC) 的 `s2twp` 配置：

- **字元轉換**：簡體 → 繁體
- **詞彙轉換**：大陸用語 → 台灣用語
  - 軟件 → 軟體
  - 視頻 → 影片
  - 內存 → 記憶體
  - 等等...

**不轉換的內容**：
- 程式碼區塊（\`\`\` 和 \`）
- XML/HTML 標籤

## 專案結構

```
minimax-claude-proxy/
├── main.py           # Proxy Server 主程式
├── converter.py      # 簡繁轉換模組
├── models.py         # 資料模型（可選）
├── requirements.txt  # 相依套件
├── .env.example      # 環境變數範例
└── README.md
```

## 取得 MiniMax API Key

1. 前往 [MiniMax 開放平台](https://platform.minimaxi.com/)
2. 註冊並登入
3. 在「帳戶管理 > 接口密鑰」取得 API Key

## 常見問題

### Q: 程式碼會被轉換嗎？

不會。程式碼區塊（用 \`\`\` 或 \` 包裹的內容）會被保留原樣。

### Q: 可以用在其他 Anthropic SDK 工具嗎？

可以。只要該工具支援設定 `base_url`，都可以使用本 Proxy。

### Q: 支援串流嗎？

支援。串流回應會即時轉換為繁體中文。

## License

MIT
