#!/bin/bash
# 測試 MiniMax 繁體中文 Proxy 與 OpenClaw 整合

echo "=========================================="
echo "測試 MiniMax 繁體中文 Proxy + OpenClaw"
echo "=========================================="
echo ""

# 1. 檢查 Proxy 是否運行
echo "1. 檢查 Proxy Server..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ Proxy Server 正在運行"
    curl -s http://localhost:8000/health | python3 -m json.tool
else
    echo "✗ Proxy Server 未運行"
    echo "請執行: cd ~/minimax-claude-proxy && python main.py"
    exit 1
fi

echo ""

# 2. 檢查 OpenClaw Gateway
echo "2. 檢查 OpenClaw Gateway..."
if systemctl --user is-active --quiet openclaw-gateway.service; then
    echo "✓ OpenClaw Gateway 正在運行"
else
    echo "✗ OpenClaw Gateway 未運行"
    echo "請執行: systemctl --user start openclaw-gateway.service"
    exit 1
fi

echo ""

# 3. 檢查 OpenClaw 設定
echo "3. 檢查 OpenClaw MiniMax 設定..."
BASEURL=$(grep -A 2 '"minimax"' ~/.openclaw/openclaw.json | grep baseUrl | cut -d'"' -f4)
echo "目前 baseUrl: $BASEURL"
if [ "$BASEURL" = "http://localhost:8000" ]; then
    echo "✓ OpenClaw 已設定為使用本地 Proxy"
else
    echo "✗ OpenClaw 尚未設定為使用本地 Proxy"
    echo "目前設定為: $BASEURL"
fi

echo ""

# 4. 測試 OpenClaw 模型
echo "4. 測試 OpenClaw 模型狀態..."
openclaw models status 2>&1 | grep -i minimax || echo "無法取得模型狀態"

echo ""
echo "=========================================="
echo "設定完成！"
echo "=========================================="
echo ""
echo "使用方式："
echo "  openclaw agent --message '請用繁體中文介紹台灣' --thinking high"
echo "  openclaw agent --message '寫一個 Python 程式' -m m2.5"
echo ""
echo "或透過 Telegram 直接對話測試繁體中文輸出"
echo ""
