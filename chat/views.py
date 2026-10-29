import json
import uuid
from contextlib import aclosing

from asgiref.sync import sync_to_async
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from bots.access import authorized_bot

from .dify import DifyAdapter, DifyError


class InputError(Exception):
    pass


def identifier(value, *, optional=False):
    if optional and value == "":
        return ""
    if not isinstance(value, str):
        raise InputError("對話或任務識別格式不正確。")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise InputError("對話或任務識別格式不正確。") from exc


def payload(request, allowed):
    if request.content_type != "application/json":
        raise InputError("請以 JSON 格式傳送資料。")
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InputError("JSON 格式不正確。") from exc
    if not isinstance(body, dict) or set(body) - set(allowed):
        raise InputError("請求包含不支援的欄位。")
    return body


async def resolve_context(request, pk):
    user = await request.auser()
    if not user.is_authenticated or not user.is_active:
        raise DifyError("登入已失效，請重新登入。", 401)
    bot = await sync_to_async(authorized_bot, thread_sensitive=True)(user, pk)
    return DifyAdapter(bot, user.dify_user_id)


def api(view):
    # Keep API errors JSON; never echo upstream bodies, keys, or exception details.
    from functools import wraps

    @wraps(view)
    async def wrapped(request, *args, **kwargs):
        try:
            return await view(request, *args, **kwargs)
        except InputError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Http404:
            return JsonResponse({"error": "找不到此 Bot 或沒有使用權限。"}, status=404)
        except DifyError as exc:
            return JsonResponse({"error": str(exc)}, status=exc.status)
    return never_cache(wrapped)


@api
@require_http_methods(["GET"])
async def conversations(request, pk):
    adapter = await resolve_context(request, pk)
    cursor = identifier(request.GET.get("last_id", ""), optional=True)
    return JsonResponse(await adapter.list_conversations(cursor))


@api
@require_http_methods(["GET"])
async def history(request, pk, conversation_id):
    adapter = await resolve_context(request, pk)
    cursor = identifier(request.GET.get("first_id", ""), optional=True)
    return JsonResponse(await adapter.list_messages(str(conversation_id), cursor))


@api
@require_http_methods(["POST"])
async def send(request, pk):
    adapter = await resolve_context(request, pk)
    body = payload(request, {"query", "conversation_id"})
    query = body.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 10000:
        raise InputError("訊息需為 1 至 10000 字元。")
    conversation_id = identifier(body.get("conversation_id", ""), optional=True)

    async def events():
        try:
            async with aclosing(adapter.send_message(query, conversation_id)) as stream:
                async for event in stream:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
        except DifyError as exc:
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n".encode()

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["X-Accel-Buffering"] = "no"
    return response


@api
@require_http_methods(["POST"])
async def stop(request, pk):
    adapter = await resolve_context(request, pk)
    body = payload(request, {"task_id"})
    task_id = identifier(body.get("task_id"))
    return JsonResponse(await adapter.stop_generation(task_id))
