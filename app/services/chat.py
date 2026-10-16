"""PhantomAPI — Chat completion service.

All business logic for processing chat requests lives here.
Route handlers call these functions and return the result directly.

Luna mode: the gateway drives ChatGPT's free web chat, which serves the
GPT-5.6 Luna model. ANY model string a client requests is resolved to Luna —
there is exactly one backend model.
"""

import json
import shutil
import tempfile
import time
import uuid

from fastapi import HTTPException

from app.services.browser import engine, ServerBusyError
from app.utils.prompt import format_prompt
from app.utils.parser import parse_tool_calls
from app.utils.vision import extract_image_urls, materialize_images
from app.utils import metrics

LUNA_MODEL = "gpt-5.6-luna"


def resolve_model(requested: str | None) -> str:
    """Map any requested model string to the Luna backend model."""
    if requested and requested != LUNA_MODEL:
        print(f"[PhantomAPI] 🔁 Model '{requested}' -> '{LUNA_MODEL}' (Luna)")
    return LUNA_MODEL


def prepare_images(messages: list) -> tuple:
    """Extract image parts and materialize to temp files.

    Returns (paths, cleanup_dir). Caller must remove cleanup_dir afterwards.
    """
    urls = extract_image_urls(messages)
    if not urls:
        return [], None
    tmp_dir = tempfile.mkdtemp(prefix="phantom_vision_")
    paths = materialize_images(urls, tmp_dir)
    if paths:
        print(f"[PhantomAPI] 🖼️ {len(paths)} image(s) ready for upload")
    return paths, tmp_dir


def _busy_error() -> HTTPException:
    """Translate an exhausted chat-slot pool into HTTP 503."""
    metrics.record_busy()
    return HTTPException(
        status_code=503,
        detail="Server busy: all chat slots occupied. Try again in a few seconds.",
    )


def process_chat_completion(messages: list, model: str, tools: list | None = None) -> dict:
    """Process a chat completion request and return an OpenAI-compatible response."""
    started = metrics.record_start()
    model = resolve_model(model)
    image_paths, tmp_dir = prepare_images(messages)
    try:
        prompt = format_prompt(messages, tools=tools)
        start = time.time()

        print(f"[PhantomAPI] 📨 Request ({len(prompt)} chars)")
        try:
            response_text = engine.chat(prompt, images=image_paths)
        except ServerBusyError:
            raise _busy_error()

        p_tokens = len(prompt.split())
        c_tokens = len(response_text.split())
        tool_calls = parse_tool_calls(response_text) if tools else None

        metrics.record_end(started, True)
        return _build_chat_response(response_text, tool_calls, model, int(start), p_tokens, c_tokens)
    except HTTPException:
        metrics.record_end(started, False)
        raise
    except Exception:
        metrics.record_end(started, False)
        raise
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def process_responses_api(messages: list, model: str, tools: list | None = None) -> dict:
    """Process a Responses API request and return the formatted response."""
    started = metrics.record_start()
    model = resolve_model(model)
    image_paths, tmp_dir = prepare_images(messages)
    try:
        prompt = format_prompt(messages, tools=tools)
        start = time.time()

        try:
            response_text = engine.chat(prompt, images=image_paths)
        except ServerBusyError:
            raise _busy_error()

        p_tokens = len(prompt.split())
        c_tokens = len(response_text.split())
        tool_calls = parse_tool_calls(response_text) if tools else None

        metrics.record_end(started, True)
        return _build_responses_response(response_text, tool_calls, model, int(start), p_tokens, c_tokens)
    except HTTPException:
        metrics.record_end(started, False)
        raise
    except Exception:
        metrics.record_end(started, False)
        raise
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Streaming (Server-Sent Events)
# ---------------------------------------------------------------------------

def _sse_chunk(payload: dict) -> str:
    """Format one SSE data frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_chat_completion(messages: list, model: str, tools: list | None = None):
    """Yield SSE frames for a streaming chat completion.

    Sync generator — Starlette runs it in a worker thread, so the event
    loop stays free. Emits OpenAI-style chat.completion.chunk frames,
    a tool_calls delta at the end when tools were requested and parsed,
    then [DONE].
    """
    started = metrics.record_start()
    model = resolve_model(model)
    image_paths, tmp_dir = prepare_images(messages)
    response_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    created = int(time.time())
    try:
        prompt = format_prompt(messages, tools=tools)
        print(f"[PhantomAPI] 📨 Stream request ({len(prompt)} chars)")

        # Role preamble
        yield _sse_chunk({
            "id": response_id, "object": "chat.completion.chunk", "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        })

        full_text = ""
        try:
            for delta in engine.chat_stream(prompt, images=image_paths):
                full_text += delta
                yield _sse_chunk({
                    "id": response_id, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                })
        except ServerBusyError:
            raise _busy_error()

        # Tool calls (if any) go out as a final delta, OpenAI-style
        tool_calls = parse_tool_calls(full_text) if tools else None
        if tool_calls:
            yield _sse_chunk({
                "id": response_id, "object": "chat.completion.chunk", "created": created,
                "model": model,
                "choices": [{
                    "index": 0, "delta": {"tool_calls": tool_calls},
                    "finish_reason": "tool_calls",
                }],
            })
        else:
            yield _sse_chunk({
                "id": response_id, "object": "chat.completion.chunk", "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            })

        metrics.record_end(started, True)
        yield "data: [DONE]\n\n"
    except HTTPException:
        metrics.record_end(started, False)
        raise
    except Exception:
        metrics.record_end(started, False)
        raise
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _sse_event(event: str, payload: dict) -> str:
    """Format one named SSE event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_responses_api(messages: list, model: str, tools: list | None = None):
    """Yield SSE events for a streaming Responses API request.

    Emits response.created, response.output_text.delta frames, then
    response.completed with the full response object (Responses API shape).
    """
    started = metrics.record_start()
    model = resolve_model(model)
    image_paths, tmp_dir = prepare_images(messages)
    response_id = f"resp-{uuid.uuid4().hex[:29]}"
    created = int(time.time())
    try:
        prompt = format_prompt(messages, tools=tools)
        print(f"[PhantomAPI] 📨 Stream responses request ({len(prompt)} chars)")

        base_obj = {"id": response_id, "object": "response", "created_at": created,
                    "model": model, "status": "in_progress", "output": []}
        yield _sse_event("response.created", base_obj)

        full_text = ""
        try:
            for delta in engine.chat_stream(prompt, images=image_paths):
                full_text += delta
                yield _sse_event("response.output_text.delta", {
                    "type": "response.output_text.delta", "delta": delta})
        except ServerBusyError:
            raise _busy_error()

        tool_calls = parse_tool_calls(full_text) if tools else None
        if tool_calls:
            output = [{
                "type": "function_call", "id": tc["id"], "call_id": tc["id"],
                "name": tc["function"]["name"], "arguments": tc["function"]["arguments"],
                "status": "completed"} for tc in tool_calls]
        else:
            output = [{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": full_text}]}]
        words = full_text.split()
        usage = {"input_tokens": len(prompt.split()), "output_tokens": len(words),
                 "total_tokens": len(prompt.split()) + len(words)}

        metrics.record_end(started, True)
        yield _sse_event("response.completed", {
            "id": response_id, "object": "response", "created_at": created,
            "model": model, "status": "completed", "output": output, "usage": usage})
    except HTTPException:
        metrics.record_end(started, False)
        raise
    except Exception:
        metrics.record_end(started, False)
        raise
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Private response builders
# ---------------------------------------------------------------------------

def _build_chat_response(
    text: str, tool_calls: list | None, model: str, created: int, p_tokens: int, c_tokens: int
) -> dict:
    """Build an OpenAI-compatible chat completion response dict."""
    response_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    usage = {"prompt_tokens": p_tokens, "completion_tokens": c_tokens, "total_tokens": p_tokens + c_tokens}

    if tool_calls:
        message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
        finish_reason = "tool_calls"
    else:
        message = {"role": "assistant", "content": text}
        finish_reason = "stop"

    return {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": usage,
    }


def _build_responses_response(
    text: str, tool_calls: list | None, model: str, created: int, p_tokens: int, c_tokens: int
) -> dict:
    """Build a Responses API response dict."""
    response_id = f"resp-{uuid.uuid4().hex[:29]}"
    usage = {"input_tokens": p_tokens, "output_tokens": c_tokens, "total_tokens": p_tokens + c_tokens}

    if tool_calls:
        output = [
            {
                "type": "function_call",
                "id": tc["id"],
                "call_id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": tc["function"]["arguments"],
                "status": "completed",
            }
            for tc in tool_calls
        ]
    else:
        output = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]

    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "model": model,
        "status": "completed",
        "output": output,
        "usage": usage,
    }
