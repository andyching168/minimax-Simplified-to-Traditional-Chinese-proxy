# OpenClaw 設定指南 - 使用繁體中文 Proxy

## 如何將 OpenClaw 的 MiniMax 端點改為本地 Proxy

### 方法一：修改 OpenClaw 設定檔（推薦）

1. **找到設定檔位置**
   ```bash
   # OpenClaw 設定檔通常在
   ~/.openclaw/openclaw.json
   ```

2. **編輯設定檔**
   ```bash
   nano ~/.openclaw/openclaw.json
   # 或使用你喜歡的編輯器
   ```

3. **修改 MiniMax 提供者設定**

   找到 `models.providers.minimax` 區段，將 `baseUrl` 改為本地 Proxy：

   **修改前：**
   ```json
   {
     "models": {
       "providers": {
         "minimax": {
           "baseUrl": "https://api.minimax.io/anthropic",
           "apiKey": "sk-cp-...",
           "api": "anthropic-messages",
           "authHeader": true
         }
       }
     }
   }
   ```

   **修改後：**
   ```json
   {
     "models": {
       "providers": {
         "minimax": {
           "baseUrl": "http://localhost:8000",
           "apiKey": "sk-cp-你的API金鑰",
           "api": "anthropic-messages",
           "authHeader": true
         }
       }
     }
   }
   ```

4. **重啟 OpenClaw Gateway**
   ```bash
   systemctl --user restart openclaw-gateway.service
   
   # 或手動重啟
   openclaw gateway --port 18789
   ```

### 方法二：使用環境變數

如果你不想修改設定檔，可以設定環境變數：

```bash
export MINIMAX_BASE_URL="http://localhost:8000"
```

然後在 `~/.config/systemd/user/openclaw-gateway.service` 加入環境變數。

### 完整設定範例

如果你想要完整的 MiniMax 設定（包含模型定義）：

```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "minimax": {
        "baseUrl": "http://localhost:8000",
        "apiKey": "${MINIMAX_API_KEY}",
        "api": "anthropic-messages",
        "authHeader": true,
        "models": [
          {
            "id": "MiniMax-M2.5",
            "name": "MiniMax M2.5 (繁體)",
            "reasoning": true,
            "input": ["text"],
            "cost": {
              "input": 15,
              "output": 60,
              "cacheRead": 2,
              "cacheWrite": 10
            },
            "contextWindow": 200000,
            "maxTokens": 8192
          },
          {
            "id": "MiniMax-M2.5-highspeed",
            "name": "MiniMax M2.5 Highspeed (繁體)",
            "reasoning": true,
            "input": ["text"],
            "cost": {
              "input": 15,
              "output": 60
            },
            "contextWindow": 200000,
            "maxTokens": 8192
          }
        ]
      }
    }
  }
}
```

### 使用流程

1. **啟動繁體中文 Proxy**
   ```bash
   cd ~/minimax-claude-proxy
   python main.py
   ```

2. **確認 Proxy 正在運行**
   ```bash
   curl http://localhost:8000/health
   # 應該回傳: {"status":"healthy","upstream":"https://api.minimax.io/anthropic"}
   ```

3. **重啟 OpenClaw**
   ```bash
   systemctl --user restart openclaw-gateway.service
   ```

4. **測試**
   ```bash
   openclaw agent --message "請用繁體中文介紹台灣" --thinking high
   ```

### 驗證設定

檢查 OpenClaw 是否正確使用你的 Proxy：

```bash
# 查看模型狀態
openclaw models status

# 查看 Gateway 日誌
journalctl --user -u openclaw-gateway.service -f
```

同時檢查 Proxy 的日誌，應該會看到來自 OpenClaw 的請求。

### 架構圖

```
OpenClaw
   ↓
http://localhost:8000 (你的 Proxy - 轉繁體)
   ↓
https://api.minimax.io/anthropic (MiniMax API)
```

### 注意事項

- 確保 Proxy Server 在 OpenClaw 之前啟動
- `apiKey` 填入你的 MiniMax API Key
- `api: "anthropic-messages"` 表示使用 Anthropic 相容格式
- 所有 MiniMax 的回應都會自動轉換為繁體中文

### 自動啟動 Proxy

建議建立一個 systemd service 讓 Proxy 自動啟動：

```bash
# 建立 service 檔案
nano ~/.config/systemd/user/minimax-proxy.service
```

內容：
```ini
[Unit]
Description=MiniMax Traditional Chinese Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/你的用戶名/minimax-claude-proxy
ExecStart=/usr/bin/python3 main.py
Restart=always
Environment="MINIMAX_BASE_URL=https://api.minimax.io/anthropic"

[Install]
WantedBy=default.target
```

啟用並啟動：
```bash
systemctl --user enable minimax-proxy.service
systemctl --user start minimax-proxy.service
```

這樣每次開機時 Proxy 都會自動啟動！
