from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import requests

_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("bandelion.ai.audit")


def _call(system: str, user: str, max_tokens: int, temperature: float) -> str:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        return ""
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    audit_logger.info(
        "ia.request model=%s mode=chat system_chars=%s user_chars=%s max_tokens=%s temperature=%s",
        model, len(system), len(user), max_tokens, temperature,
    )
    started = time.monotonic()
    resp = requests.post(
        _MISTRAL_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=20,
    )
    audit_logger.info(
        "ia.response model=%s mode=chat status=%s elapsed_ms=%s",
        model, resp.status_code, int((time.monotonic() - started) * 1000),
    )
    if not resp.ok:
        logger.warning("Mistral API error status=%s", resp.status_code)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def ask(
    system: str,
    user: str,
    *,
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> str:
    """Generic async Mistral call. Returns '' on error or missing key."""
    if not os.getenv("MISTRAL_API_KEY", ""):
        audit_logger.warning("ia.skip reason=missing_api_key mode=chat")
        return ""
    try:
        return await asyncio.to_thread(_call, system, user, max_tokens, temperature)
    except Exception as e:
        logger.warning("Mistral ask error: %s", e)
        return ""


def _call_with_tools(system: str, user: str, tools: list[dict]) -> dict:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    tool_names = [tool.get("function", {}).get("name", "unknown") for tool in tools]
    audit_logger.info(
        "ia.request model=%s mode=tools system_chars=%s user_chars=%s tools=%s",
        model, len(system), len(user), ",".join(tool_names),
    )
    started = time.monotonic()
    response = requests.post(
        _MISTRAL_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.4},
        timeout=25,
    )
    response.raise_for_status()
    audit_logger.info(
        "ia.response model=%s mode=tools status=%s elapsed_ms=%s",
        model, response.status_code, int((time.monotonic() - started) * 1000),
    )
    return {"messages": messages, "message": response.json()["choices"][0]["message"], "model": model}


async def ask_with_tools(system: str, user: str, tools: list[dict], execute_tool) -> str:
    """Run Mistral tool calls and return the final natural-language answer.

    Calls proposed in one turn are executed concurrently. Executors must enforce
    Discord permissions and all side-effect safeguards themselves.
    """
    if not os.getenv("MISTRAL_API_KEY", ""):
        audit_logger.warning("ia.skip reason=missing_api_key mode=tools")
        return ""
    try:
        state = await asyncio.to_thread(_call_with_tools, system, user, tools)
        messages, message, model = state["messages"], state["message"], state["model"]
        messages.append(message)
        for _ in range(3):
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                audit_logger.info("ia.tools.complete rounds=%s final_chars=%s", _ + 1, len(message.get("content") or ""))
                return message.get("content") or "Listo."

            audit_logger.info(
                "ia.tools.proposed round=%s count=%s names=%s",
                _ + 1, len(tool_calls), ",".join(call.get("function", {}).get("name", "unknown") for call in tool_calls),
            )

            async def invoke(call: dict) -> dict:
                function = call.get("function", {})
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                audit_logger.info(
                    "ia.tool.start name=%s argument_keys=%s",
                    function.get("name", "unknown"), ",".join(sorted(arguments.keys())),
                )
                started = time.monotonic()
                result = await execute_tool(function.get("name", ""), arguments)
                audit_logger.info(
                    "ia.tool.complete name=%s ok=%s elapsed_ms=%s",
                    function.get("name", "unknown"), bool(result.get("ok")), int((time.monotonic() - started) * 1000),
                )
                return {"role": "tool", "name": function.get("name", ""), "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}

            messages.extend(await asyncio.gather(*(invoke(call) for call in tool_calls)))
            raw = await asyncio.to_thread(
                requests.post,
                _MISTRAL_URL,
                headers={"Authorization": f"Bearer {os.getenv('MISTRAL_API_KEY')}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.4},
                timeout=25,
            )
            raw.raise_for_status()
            audit_logger.info("ia.tools.followup status=%s round=%s", raw.status_code, _ + 1)
            message = raw.json()["choices"][0]["message"]
            messages.append(message)
        return message.get("content") or "Terminé las acciones solicitadas."
    except Exception as exc:
        logger.warning("Mistral tool call error type=%s", type(exc).__name__)
        audit_logger.exception("ia.tools.failed error_type=%s", type(exc).__name__)
        return ""
