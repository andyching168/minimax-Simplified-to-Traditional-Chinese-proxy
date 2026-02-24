
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
TIMEOUT = float(os.getenv("API_TIMEOUT_MS", "300000")) / 1000  # 轉換為秒


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    logger.info(f"Proxy server starting, forwarding to: {MINIMAX_BASE_URL}")
    yield
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
    """
    logger.info(f"🎯 Received POST /v1/messages from {request.client.host if request.client else 'unknown'}")
    try:
        # 取得請求資料
        body = await request.body()
        request_data = json.loads(body) if body else {}
        
        is_stream = request_data.get("stream", False)
        headers = get_forwarding_headers(request)
        
        logger.info(f"Proxying request - model: {request_data.get('model')}, stream: {is_stream}")
        
        if is_stream:
            return StreamingResponse(
                stream_proxy(request_data, headers),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # 非串流請求
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
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


async def stream_proxy(request_data: dict[str, Any], headers: dict[str, str]):
    """串流代理"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{MINIMAX_BASE_URL}/v1/messages",
                headers=headers,
                json=request_data
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield f"data: {error_body.decode()}\n\n"
                    return
                
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
                try:
                    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                        async with client.stream(
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
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
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
    logger.info(f"📥 Catch-all proxy: {request.method} /{path} from {request.client.host if request.client else 'unknown'}")
    try:
        body = await request.body()
        headers = get_forwarding_headers(request)
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(
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
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          MiniMax M2.5 繁體中文 Proxy Server                  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  本機位址: http://{host}:{port:<5}                               ║
║  上游 API: {MINIMAX_BASE_URL:<43} ║
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
        reload=True,
        log_level="info"
    )
