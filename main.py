
"""
MiniMax M2.5 繁體中文 Proxy Server
作為 Claude Code 和 MiniMax API 之間的中介，將輸出轉換為繁體中文

架構：
Claude Code → 本 Proxy (轉繁體) → MiniMax API
"""

import json
import os
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

from converter import to_traditional, to_traditional_json

# 載入環境變數
load_dotenv()

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MiniMax API 設定
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic")

# 設定細分的 timeout - 針對長請求優化
TIMEOUT = httpx.Timeout(
    connect=10.0,      # 建立連線 10 秒
    read=1800.0,       # 讀取資料 30 分鐘 (適合長時間思考的請求)
    write=30.0,        # 寫入資料 30 秒
    pool=5.0           # 從連線池取得連線 5 秒
)

# 請求大小限制 (10MB)
MAX_REQUEST_SIZE = 10 * 1024 * 1024

# 共享的 HTTP client (連線池重用)
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    global http_client
    logger.info(f"Proxy server starting, forwarding to: {MINIMAX_BASE_URL}")
    
    # 建立共享的 HTTP client
    http_client = httpx.AsyncClient(
        timeout=TIMEOUT,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=50
        )
    )
    logger.info("HTTP client initialized with connection pool")
    
    yield
    
    # 關閉 HTTP client
    if http_client:
        await http_client.aclose()
    logger.info("Proxy server shutting down")


# 建立 FastAPI 應用程式
app = FastAPI(
    title="MiniMax 繁體中文 Proxy",
    description="將 MiniMax M2.5 的輸出轉換為繁體中文的 Proxy Server",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 請求大小限制 middleware
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """限制請求大小以避免記憶體問題"""
    # Log ALL incoming requests
    logger.info(f"📥 Incoming request: {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
    
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > MAX_REQUEST_SIZE:
                logger.warning(f"Request too large: {size} bytes (max: {MAX_REQUEST_SIZE})")
                return JSONResponse(
                    status_code=413,
                    content={
                        "type": "error",
                        "error": {
                            "type": "request_too_large",
                            "message": f"Request size {size} exceeds maximum {MAX_REQUEST_SIZE} bytes"
                        }
                    }
                )
        except ValueError:
            pass  # 無效的 content-length，繼續處理
    
    return await call_next(request)


def convert_response_content(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """轉換回應內容中的文字為繁體中文"""
    converted = []
    for block in content:
        block_copy = block.copy()
        
        if block.get("type") == "text" and "text" in block:
            block_copy["text"] = to_traditional(block["text"])
        elif block.get("type") == "thinking" and "thinking" in block:
            block_copy["thinking"] = to_traditional(block["thinking"])
        elif block.get("type") == "tool_use" and "input" in block:
            block_copy["input"] = to_traditional_json(block["input"])
        
        converted.append(block_copy)
    
    return converted


def convert_stream_chunk(chunk_data: dict[str, Any]) -> dict[str, Any]:
    """轉換串流資料中的文字為繁體中文"""
    data = chunk_data.copy()
    
    # content_block_start
    if "content_block" in data:
        cb = data["content_block"]
        if cb.get("type") == "text" and "text" in cb:
            cb["text"] = to_traditional(cb["text"])
        elif cb.get("type") == "thinking" and "thinking" in cb:
            cb["thinking"] = to_traditional(cb["thinking"])
    
    # content_block_delta
    if "delta" in data:
        delta = data["delta"]
        if delta.get("type") == "text_delta" and "text" in delta:
            delta["text"] = to_traditional(delta["text"])
        elif delta.get("type") == "thinking_delta" and "thinking" in delta:
            delta["thinking"] = to_traditional(delta["thinking"])
    
    # message (非串流或最終訊息)
    if "message" in data and "content" in data.get("message", {}):
        data["message"]["content"] = convert_response_content(data["message"]["content"])
    
    # 直接的 content 欄位
    if "content" in data and isinstance(data["content"], list):
        data["content"] = convert_response_content(data["content"])
    
    return data


def get_forwarding_headers(request: Request) -> dict[str, str]:
    """取得要轉發到 MiniMax 的 headers"""
    headers = {}
    
    # 複製必要的 headers
    forward_headers = [
        "content-type",
        "x-api-key",
        "anthropic-version",
        "anthropic-beta",
        "authorization",
    ]
    
    for header in forward_headers:
        value = request.headers.get(header)
        if value:
            headers[header] = value
    
    # 確保有 Content-Type
    if "content-type" not in headers:
        headers["content-type"] = "application/json"
    
    return headers


@app.get("/")
async def root():
    """根路徑"""
    return {
        "service": "MiniMax 繁體中文 Proxy",
        "version": "1.0.0",
        "upstream": MINIMAX_BASE_URL,
        "description": "將 MiniMax M2.5 輸出轉換為繁體中文"
    }


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "healthy", "upstream": MINIMAX_BASE_URL}


@app.post("/v1/messages")
async def proxy_messages(request: Request):
    """
    代理 /v1/messages 請求
    轉發到 MiniMax API 並將回應轉換為繁體中文
    
    注意：由於 MiniMax API 的串流模式連接需要 15-20 秒（超過一般客戶端 timeout），
    我們將串流請求轉換為非串流請求（8秒完成），然後在 proxy 端模擬串流回應。
    """
    if http_client is None:
        return JSONResponse(
            status_code=503,
            content={"type": "error", "error": {"type": "service_unavailable", "message": "HTTP client not initialized"}}
        )
    
    logger.info(f"🎯 Received POST /v1/messages from {request.client.host if request.client else 'unknown'}")
    try:
        # 取得請求資料
        body = await request.body()
        request_data = json.loads(body) if body else {}
        
        is_stream_requested = request_data.get("stream", False)
        headers = get_forwarding_headers(request)
        
        logger.info(f"Proxying request - model: {request_data.get('model')}, stream requested: {is_stream_requested}")
        
        if is_stream_requested:
            # 客戶端要求串流，但我們用非串流模式調用 MiniMax（更快），
            # 然後在 proxy 端轉換成串流格式
            request_data_non_stream = request_data.copy()
            request_data_non_stream["stream"] = False
            
            return StreamingResponse(
                stream_from_non_stream(request_data_non_stream, headers),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # 非串流請求
            response = await http_client.post(
                f"{MINIMAX_BASE_URL}/v1/messages",
                headers=headers,
                json=request_data
            )
            
            if response.status_code != 200:
                return JSONResponse(
                    status_code=response.status_code,
                    content=response.json() if response.content else {"error": "Unknown error"}
                )
            
            result = response.json()
            
            # 診斷日誌：記錄 tool_use 內容（非串流模式）
            content_blocks = result.get("content", [])
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    tool_id = block.get("id", "unknown")
                    logger.info(f"🔧 Tool use detected: name={tool_name}, id={tool_id}, input={json.dumps(tool_input, ensure_ascii=False)}")
                    if not tool_input or (isinstance(tool_input, dict) and len(tool_input) == 0):
                        logger.warning(f"⚠️ Empty tool input detected for tool '{tool_name}'! Full block: {json.dumps(block, ensure_ascii=False)}")
            
            # 轉換回應內容為繁體中文
            if "content" in result:
                result["content"] = convert_response_content(result["content"])
            
            logger.info("Response converted to Traditional Chinese")
            return JSONResponse(content=result)
    
    except httpx.TimeoutException:
        logger.error("Request to MiniMax API timed out")
        return JSONResponse(
            status_code=504,
            content={"type": "error", "error": {"type": "timeout", "message": "Request timed out"}}
        )
    except Exception as e:
        logger.error(f"Proxy error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"type": "error", "error": {"type": "internal_error", "message": str(e)}}
        )


async def stream_from_non_stream(request_data: dict[str, Any], headers: dict[str, str]):
    """
    使用非串流模式調用 MiniMax API（更快），然後將回應轉換成串流格式
    這樣可以避免 MiniMax 串流模式的 15-20 秒連接延遲
    
    重要：在等待 API 回應時發送 ping 事件保持連線活躍
    """
    if http_client is None:
        yield 'data: {"type":"error","error":{"type":"service_unavailable","message":"HTTP client not initialized"}}\n\n'
        return
    
    import asyncio
    import time
    
    # 創建一個 Future 來儲存 API 回應
    api_response = None
    api_error = None
    api_done = False
    
    async def call_api():
        nonlocal api_response, api_error, api_done
        max_retries = 3
        retry_delays = [0, 2, 5]  # 延遲秒數：第一次立即，第二次 2 秒，第三次 5 秒
        
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                if attempt == 0:
                    logger.info("Using non-stream mode to avoid MiniMax stream connection delay")
                else:
                    logger.info(f"Retry attempt #{attempt + 1} after connection failure")
                
                response = await http_client.post(
                    f"{MINIMAX_BASE_URL}/v1/messages",
                    headers=headers,
                    json=request_data
                )
                api_duration = time.time() - start_time
                logger.info(f"MiniMax API call completed in {api_duration:.2f}s, status: {response.status_code}")
                api_response = response
                api_error = None  # 成功時清除錯誤
                api_done = True
                return  # 成功，退出重試迴圈
                
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(f"Attempt #{attempt + 1} failed: {type(e).__name__}: {e}")
                api_error = e
                
                # 如果還有重試機會，等待後重試
                if attempt < max_retries - 1:
                    delay = retry_delays[attempt + 1]
                    logger.info(f"Waiting {delay}s before retry...")
                    await asyncio.sleep(delay)
                else:
                    # 最後一次嘗試失敗
                    if isinstance(e, httpx.TimeoutException):
                        logger.error(f"API call timeout after {max_retries} attempts: {type(e).__name__}")
                        api_error = Exception(f"Request timed out after {max_retries} attempts")
                    else:
                        logger.error(f"API connection error after {max_retries} attempts: {type(e).__name__}")
                        api_error = Exception(f"Connection failed after {max_retries} attempts: {e}")
                        
            except Exception as e:
                logger.error(f"API call error: {type(e).__name__}: {e}", exc_info=True)
                api_error = e
                break  # 非連線錯誤不重試
        
        api_done = True
    
    # 在背景啟動 API 調用
    api_task = asyncio.create_task(call_api())
    
    # 先發送一個 message_start 事件（使用暫時的 ID）
    temp_message_start = {
        "type": "message_start",
        "message": {
            "id": f"pending-{int(time.time())}",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": request_data.get("model", "MiniMax-M2.5"),
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }
    }
    yield f"event: message_start\ndata: {json.dumps(temp_message_start, ensure_ascii=False)}\n\n"
    
    # 發送一個空的 content_block_start 來表示正在處理
    thinking_block_start = {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "thinking", "thinking": ""}
    }
    yield f"event: content_block_start\ndata: {json.dumps(thinking_block_start, ensure_ascii=False)}\n\n"
    
    # 每 3 秒發送一個 ping（空的 thinking delta）保持連線
    ping_count = 0
    while not api_done:
        await asyncio.sleep(3)
        if not api_done:
            ping_count += 1
            # 發送空的 thinking delta 作為 keepalive
            ping_event = {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": ""}
            }
            yield f"event: content_block_delta\ndata: {json.dumps(ping_event, ensure_ascii=False)}\n\n"
            logger.info(f"Sent keepalive ping #{ping_count}")
    
    # 等待 API 任務完成
    await api_task
    
    # 處理錯誤
    if api_error:
        error_event = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": f"Error: {str(api_error)}"}
        }
        yield f"event: content_block_delta\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        
        # 發送結束事件
        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n"
        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'error'}}, ensure_ascii=False)}\n\n"
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'}, ensure_ascii=False)}\n\n"
        return
    
    if api_response is None:
        yield f'data: {{"type":"error","error":{{"type":"internal_error","message":"No response received"}}}}\n\n'
        return
    
    if api_response.status_code != 200:
        error_data = api_response.json() if api_response.content else {"error": "Unknown error"}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        return
    
    try:
        result = api_response.json()
    except Exception as e:
        yield f'data: {{"type":"error","error":{{"type":"parse_error","message":"{str(e)}"}}}}\n\n'
        return
    
    # 診斷日誌：記錄 tool_use 內容
    content_blocks = result.get("content", [])
    for block in content_blocks:
        if block.get("type") == "tool_use":
            tool_name = block.get("name", "unknown")
            tool_input = block.get("input", {})
            tool_id = block.get("id", "unknown")
            logger.info(f"🔧 Tool use detected: name={tool_name}, id={tool_id}, input={json.dumps(tool_input, ensure_ascii=False)}")
            # 檢查是否有空的 input
            if not tool_input or (isinstance(tool_input, dict) and len(tool_input) == 0):
                logger.warning(f"⚠️ Empty tool input detected for tool '{tool_name}'! Full block: {json.dumps(block, ensure_ascii=False)}")
    
    # 轉換為繁體中文
    if "content" in result:
        result["content"] = convert_response_content(result["content"])
    
    # 關閉之前的 thinking block（我們發送了空的）
    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n"
    
    # 現在發送真正的內容
    content_blocks = result.get("content", [])
    for index, block in enumerate(content_blocks):
        actual_index = index + 1  # 因為 index 0 已經用於 keepalive thinking
        
        # content_block_start - 對於 tool_use 需要特殊處理
        if block.get("type") == "tool_use":
            # tool_use 的 content_block_start 中 input 應該是空字串
            # 實際的 input 會通過 input_json_delta 發送
            block_for_start = {
                "type": "tool_use",
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "input": {}  # 空的 input，實際內容通過 delta 發送
            }
            block_start = {
                "type": "content_block_start",
                "index": actual_index,
                "content_block": block_for_start
            }
        else:
            block_start = {
                "type": "content_block_start",
                "index": actual_index,
                "content_block": block
            }
        yield f"event: content_block_start\ndata: {json.dumps(block_start, ensure_ascii=False)}\n\n"
        
        # content_block_delta - 逐字發送（模擬打字效果）
        if block.get("type") == "thinking" and "thinking" in block:
            text = block["thinking"]
            chunk_size = 10
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i+chunk_size]
                delta = {
                    "type": "content_block_delta",
                    "index": actual_index,
                    "delta": {"type": "thinking_delta", "thinking": chunk}
                }
                yield f"event: content_block_delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)
        
        elif block.get("type") == "text" and "text" in block:
            text = block["text"]
            chunk_size = 5
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i+chunk_size]
                delta = {
                    "type": "content_block_delta",
                    "index": actual_index,
                    "delta": {"type": "text_delta", "text": chunk}
                }
                yield f"event: content_block_delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)
        
        elif block.get("type") == "tool_use" and "input" in block:
            # 對於 tool_use，需要發送 input_json_delta 事件
            # Anthropic 串流格式要求逐步發送 JSON input
            input_json = json.dumps(block["input"], ensure_ascii=False)
            chunk_size = 20  # JSON 字串分塊大小
            for i in range(0, len(input_json), chunk_size):
                chunk = input_json[i:i+chunk_size]
                delta = {
                    "type": "content_block_delta",
                    "index": actual_index,
                    "delta": {"type": "input_json_delta", "partial_json": chunk}
                }
                yield f"event: content_block_delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
        
        # content_block_stop
        block_stop = {"type": "content_block_stop", "index": actual_index}
        yield f"event: content_block_stop\ndata: {json.dumps(block_stop, ensure_ascii=False)}\n\n"
    
    # 發送 message_delta
    message_delta = {
        "type": "message_delta",
        "delta": {
            "stop_reason": result.get("stop_reason", "end_turn"),
            "stop_sequence": result.get("stop_sequence")
        },
        "usage": result.get("usage", {})
    }
    yield f"event: message_delta\ndata: {json.dumps(message_delta, ensure_ascii=False)}\n\n"
    
    # 發送 message_stop
    message_stop = {"type": "message_stop"}
    yield f"event: message_stop\ndata: {json.dumps(message_stop, ensure_ascii=False)}\n\n"
    
    logger.info("Simulated stream response completed")


async def stream_proxy(request_data: dict[str, Any], headers: dict[str, str]):
    """串流代理"""
    if http_client is None:
        yield 'data: {"type":"error","error":{"type":"service_unavailable","message":"HTTP client not initialized"}}\n\n'
        return
    
    try:
        async with http_client.stream(
            "POST",
            f"{MINIMAX_BASE_URL}/v1/messages",
            headers=headers,
            json=request_data
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield f"data: {error_body.decode()}\n\n"
                return
            
            # 直接轉發所有資料，不做任何延遲
            async for line in response.aiter_lines():
                if not line:
                    continue
                
                if line.startswith("event:"):
                    # 直接轉發 event 行
                    yield f"{line}\n"
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    
                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue
                    
                    try:
                        data = json.loads(data_str)
                        # 轉換為繁體中文
                        converted = convert_stream_chunk(data)
                        yield f"data: {json.dumps(converted, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        # 無法解析的資料直接轉發
                        yield f"{line}\n"
                else:
                    # 其他行直接轉發
                    yield f"{line}\n"
    
    except httpx.TimeoutException:
        yield f'data: {{"type":"error","error":{{"type":"timeout","message":"Request timed out"}}}}\n\n'
    except Exception as e:
        logger.error(f"Stream proxy error: {e}", exc_info=True)
        yield f'data: {{"type":"error","error":{{"type":"internal_error","message":"{str(e)}"}}}}\n\n'


async def _handle_openai_chat_completions(request: Request, endpoint_name: str = "/v1/chat/completions"):
    """
    處理 OpenAI chat completions 請求的共用邏輯
    將 OpenAI 格式轉換為 Anthropic 格式，然後轉發到 MiniMax
    """
    if http_client is None:
        return JSONResponse(
            status_code=503,
            content={"error": {"type": "service_unavailable", "message": "HTTP client not initialized"}}
        )
    
    logger.info(f"🎯 Received POST {endpoint_name} (OpenAI format) from {request.client.host if request.client else 'unknown'}")
    try:
        body = await request.body()
        openai_request = json.loads(body) if body else {}
        
        # 將 OpenAI messages 格式轉換為 Anthropic 格式
        messages = []
        system_prompt = None
        
        for msg in openai_request.get("messages", []):
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                system_prompt = content
            elif role == "user":
                messages.append({"role": "user", "content": content})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": content})
        
        # 構建 Anthropic 格式請求
        anthropic_request = {
            "model": openai_request.get("model", "MiniMax-M2.5"),
            "messages": messages,
            "max_tokens": openai_request.get("max_tokens", 8192),
            "stream": openai_request.get("stream", False),
        }
        
        if system_prompt:
            anthropic_request["system"] = system_prompt
        
        if "temperature" in openai_request:
            anthropic_request["temperature"] = openai_request["temperature"]
        
        if "top_p" in openai_request:
            anthropic_request["top_p"] = openai_request["top_p"]
        
        is_stream = anthropic_request.get("stream", False)
        headers = get_forwarding_headers(request)
        
        logger.info(f"Converted OpenAI → Anthropic - model: {anthropic_request.get('model')}, stream: {is_stream}")
        
        if is_stream:
            # 串流模式：需要將 Anthropic SSE 轉換為 OpenAI SSE
            async def openai_stream():
                assert http_client is not None  # 已在外部函數檢查
                try:
                    # 立即發送一個初始 chunk，避免客戶端 timeout
                    initial_chunk = {
                        "id": "",
                        "object": "chat.completion.chunk",
                        "created": int(openai_request.get("created", 0)) if isinstance(openai_request.get("created"), (int, float)) else 0,
                        "model": anthropic_request["model"],
                        "choices": []
                    }
                    yield f"data: {json.dumps(initial_chunk, ensure_ascii=False)}\n\n"
                    
                    async with http_client.stream(
                        "POST",
                        f"{MINIMAX_BASE_URL}/v1/messages",
                        headers=headers,
                        json=anthropic_request
                    ) as response:
                        if response.status_code != 200:
                            error_body = await response.aread()
                            yield f"data: {error_body.decode()}\n\n"
                            return
                        
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                yield "data: [DONE]\n\n"
                                continue
                            
                            try:
                                anthropic_chunk = json.loads(data_str)
                                # 轉換為繁體中文
                                anthropic_chunk = convert_stream_chunk(anthropic_chunk)
                                
                                # 轉換為 OpenAI 格式
                                openai_chunk = {
                                    "id": anthropic_chunk.get("id", ""),
                                    "object": "chat.completion.chunk",
                                    "created": int(json.loads(body).get("created", 0)) if body else 0,
                                    "model": anthropic_request["model"],
                                    "choices": []
                                }
                                
                                if anthropic_chunk.get("type") == "content_block_delta":
                                    delta = anthropic_chunk.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        openai_chunk["choices"].append({
                                            "index": 0,
                                            "delta": {"content": delta.get("text", "")},
                                            "finish_reason": None
                                        })
                                elif anthropic_chunk.get("type") == "message_stop":
                                    openai_chunk["choices"].append({
                                        "index": 0,
                                        "delta": {},
                                        "finish_reason": "stop"
                                    })
                                
                                yield f"data: {json.dumps(openai_chunk, ensure_ascii=False)}\n\n"
                            except json.JSONDecodeError:
                                pass
                
                except Exception as e:
                    logger.error(f"OpenAI stream error: {e}", exc_info=True)
                    yield f'data: {{"error":{{"message":"{str(e)}"}}}}\n\n'
            
            return StreamingResponse(
                openai_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # 非串流模式
            response = await http_client.post(
                f"{MINIMAX_BASE_URL}/v1/messages",
                headers=headers,
                json=anthropic_request
            )
            
            if response.status_code != 200:
                return JSONResponse(
                    status_code=response.status_code,
                    content=response.json() if response.content else {"error": "Unknown error"}
                )
            
            anthropic_result = response.json()
            
            # 轉換回應內容為繁體中文
            if "content" in anthropic_result:
                anthropic_result["content"] = convert_response_content(anthropic_result["content"])
            
            # 轉換為 OpenAI 格式
            openai_result = {
                "id": anthropic_result.get("id", ""),
                "object": "chat.completion",
                "created": int(openai_request.get("created", 0)),
                "model": anthropic_request["model"],
                "choices": [],
                "usage": {
                    "prompt_tokens": anthropic_result.get("usage", {}).get("input_tokens", 0),
                    "completion_tokens": anthropic_result.get("usage", {}).get("output_tokens", 0),
                    "total_tokens": (
                        anthropic_result.get("usage", {}).get("input_tokens", 0) +
                        anthropic_result.get("usage", {}).get("output_tokens", 0)
                    )
                }
            }
            
            # 提取文字內容
            text_content = ""
            for content_block in anthropic_result.get("content", []):
                if content_block.get("type") == "text":
                    text_content += content_block.get("text", "")
            
            logger.info(f"Extracted text content length: {len(text_content)} chars")
            
            openai_result["choices"].append({
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text_content
                },
                "finish_reason": anthropic_result.get("stop_reason", "stop")
            })
            
            logger.info("Response converted to Traditional Chinese (OpenAI format)")
            return JSONResponse(content=openai_result)
    
    except Exception as e:
        logger.error(f"OpenAI endpoint error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e), "type": "internal_error"}}
        )


# OpenAI 相容端點（帶 /v1/ 前綴）
@app.post("/v1/chat/completions")
async def openai_chat_completions_v1(request: Request):
    """OpenAI 相容端點 (標準路徑)"""
    return await _handle_openai_chat_completions(request, "/v1/chat/completions")


# OpenAI 相容端點（不帶 /v1/ 前綴，用於某些客戶端）
@app.post("/chat/completions")
async def openai_chat_completions(request: Request):
    """OpenAI 相容端點 (簡化路徑)"""
    return await _handle_openai_chat_completions(request, "/chat/completions")


# 其他 Anthropic API 端點的透明代理
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_all(request: Request, path: str):
    """透明代理其他所有請求（不做轉換）"""
    if http_client is None:
        return JSONResponse(
            status_code=503,
            content={"type": "error", "error": {"type": "service_unavailable", "message": "HTTP client not initialized"}}
        )
    
    logger.info(f"📥 Catch-all proxy: {request.method} /{path} from {request.client.host if request.client else 'unknown'}")
    try:
        body = await request.body()
        headers = get_forwarding_headers(request)
        
        response = await http_client.request(
            method=request.method,
            url=f"{MINIMAX_BASE_URL}/{path}",
            headers=headers,
            content=body if body else None,
            params=dict(request.query_params)
        )
        
        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if response.content else None
        )
    
    except Exception as e:
        logger.error(f"Proxy error for {path}: {e}")
        return JSONResponse(
            status_code=500,
            content={"type": "error", "error": {"type": "internal_error", "message": str(e)}}
        )


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    # 開發模式：設為 True 以啟用自動重載（注意：會在檔案變更時中斷進行中的請求）
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          MiniMax M2.5 繁體中文 Proxy Server                  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  本機位址: http://{host}:{port:<5}                               ║
║  上游 API: {MINIMAX_BASE_URL:<43} ║
║  自動重載: {"開啟 (開發模式)" if reload else "關閉 (生產模式)":<43} ║
║                                                              ║
║  Claude Code 設定範例:                                       ║
║  {{                                                           ║
║    "env": {{                                                  ║
║      "ANTHROPIC_BASE_URL": "http://localhost:{port}",         ║
║      "ANTHROPIC_AUTH_TOKEN": "<YOUR_MINIMAX_API_KEY>",       ║
║      "ANTHROPIC_MODEL": "MiniMax-M2.5"                       ║
║    }}                                                         ║
║  }}                                                           ║
║                                                              ║
║  功能: 自動將 MiniMax 輸出轉換為繁體中文                     ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
