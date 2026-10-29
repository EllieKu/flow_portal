"""Dify's chat API, with no local conversation or generation state."""

import json
import re
from urllib.parse import urlparse

try:
    import httpx
except ModuleNotFoundError:
    httpx = None
from django.conf import settings


class DifyError(Exception):
    def __init__(self, message="Dify 服務暫時無法使用，請稍後再試。", status=502):
        super().__init__(message)
        self.status = status


def check_response(response):
    if response.status_code == 404:
        raise DifyError("找不到此對話或任務，請重新選擇對話或建立新對話。", 404)
    if response.status_code in {401, 403}:
        raise DifyError("Dify 連線認證失敗，請聯絡管理員。")
    if response.status_code == 429:
        raise DifyError("Dify 目前忙碌，請稍後再試。", 429)
    if response.status_code == 400:
        raise DifyError("Dify 無法處理此請求，請確認應用設定及對話是否有效。", 400)
    if not 200 <= response.status_code < 300:
        raise DifyError()


class SSEParser:
    """Consume decoded SSE lines; HTTPX handles network/UTF-8 boundaries."""

    def __init__(self):
        self.data = []
        self.event = ""

    def feed(self, line):
        if line:
            field, _, value = line.partition(":")
            if field == "data":
                self.data.append(value.removeprefix(" "))
            elif field == "event":
                self.event = value.removeprefix(" ")
            return None
        data, event = self.data, self.event
        self.data, self.event = [], ""
        if not data:
            return {"event": "ping"} if event == "ping" else None
        try:
            payload = json.loads("\n".join(data))
        except (ValueError, TypeError) as exc:
            raise DifyError("Dify 串流格式異常，請重新載入歷史紀錄。") from exc
        if not isinstance(payload, dict):
            raise DifyError("Dify 串流格式異常，請重新載入歷史紀錄。")
        return payload


class DifyAdapter:
    def __init__(self, bot, user_id, *, transport=None):
        if httpx is None:
            raise DifyError("Dify 連線服務尚未就緒，請聯絡管理員。", 503)
        key = bot.api_key.strip()
        if not key:
            raise DifyError("此 Bot 尚未設定 Dify 金鑰，請聯絡管理員。", 503)
        self.base_url = bot.api_base_url.rstrip("/") + "/"
        self.user = str(user_id)
        self.key = key
        self.transport = transport

    def client(self):
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.key}"},
            timeout=httpx.Timeout(settings.DIFY_READ_TIMEOUT, connect=10),
            follow_redirects=False,
            transport=self.transport,
        )

    async def request(self, method, path, **kwargs):
        try:
            async with self.client() as client:
                response = await client.request(method, path, **kwargs)
                check_response(response)
                data = response.json()
                if not isinstance(data, dict):
                    raise DifyError()
                return data
        except httpx.TimeoutException as exc:
            raise DifyError("Dify 回應逾時，請稍後再試。", 504) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DifyError() from exc

    async def list_conversations(self, last_id=""):
        data = await self.request("GET", "conversations", params={
            "user": self.user, "limit": 20, "last_id": last_id,
            "sort_by": "-updated_at",
        })
        try:
            rows = [{"id": row["id"], "name": row.get("name") or "未命名對話"}
                    for row in data["data"]]
            return {"data": rows, "has_more": bool(data.get("has_more")),
                    "next_cursor": rows[-1]["id"] if rows else ""}
        except (KeyError, TypeError) as exc:
            raise DifyError() from exc

    async def get_site(self):
        data = await self.request("GET", "site")

        def text_value(name, limit):
            value = data.get(name)
            return value[:limit] if isinstance(value, str) else ""

        icon_type = data.get("icon_type")
        if icon_type not in {"emoji", "image"}:
            icon_type = ""
        icon_url = text_value("icon_url", 2000)
        if icon_url and urlparse(icon_url).scheme not in {"http", "https"}:
            icon_url = ""

        def color_value(name):
            value = data.get(name)
            return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else ""

        return {
            "title": text_value("title", 200),
            "description": text_value("description", 2000),
            "icon_type": icon_type,
            "icon": text_value("icon", 100),
            "icon_url": icon_url,
            "icon_background": color_value("icon_background"),
            "chat_color_theme": color_value("chat_color_theme"),
            "input_placeholder": text_value("input_placeholder", 200),
            "copyright": text_value("copyright", 500),
        }

    async def list_messages(self, conversation_id, first_id=""):
        data = await self.request("GET", "messages", params={
            "user": self.user, "conversation_id": conversation_id,
            "limit": 20, "first_id": first_id,
        })
        try:
            rows = [{"id": row["id"], "query": row.get("query", ""),
                     "answer": row.get("answer", ""),
                     "created_at": row.get("created_at", 0)} for row in data["data"]]
            rows.sort(key=lambda row: row["created_at"])
            return {"data": rows, "has_more": bool(data.get("has_more")),
                    "next_cursor": rows[0]["id"] if rows else ""}
        except (KeyError, TypeError) as exc:
            raise DifyError() from exc

    async def stop_generation(self, task_id):
        await self.request("POST", f"chat-messages/{task_id}/stop", json={"user": self.user})
        return {"result": "success"}

    async def send_message(self, query, conversation_id=""):
        body = {"user": self.user, "query": query, "inputs": {},
                "response_mode": "streaming", "conversation_id": conversation_id}
        parser = SSEParser()
        workflow = False
        ending = None
        try:
            async with self.client() as client:
                async with client.stream("POST", "chat-messages", json=body) as response:
                    check_response(response)
                    if "text/event-stream" not in response.headers.get("content-type", ""):
                        raise DifyError("Dify 未回傳預期的串流格式。")
                    async for line in response.aiter_lines():
                        event = parser.feed(line)
                        if event is None:
                            continue
                        kind = event.get("event")
                        identifiers = {key: event[key] for key in
                                       ("conversation_id", "task_id", "message_id")
                                       if isinstance(event.get(key), str)}
                        if identifiers:
                            yield {"event": "start", **identifiers}
                        if kind == "workflow_started":
                            workflow = True
                        elif kind in {"message", "agent_message"}:
                            if not isinstance(event.get("answer", ""), str):
                                raise DifyError("Dify 串流格式異常。")
                            yield {"event": "delta", "text": event.get("answer", "")}
                        elif kind == "message_replace":
                            if not isinstance(event.get("answer", ""), str):
                                raise DifyError("Dify 串流格式異常。")
                            yield {"event": "replace", "text": event.get("answer", "")}
                        elif kind == "message_end":
                            ending = {"event": "end", **identifiers}
                            if not workflow:
                                yield ending
                                return
                        elif kind == "workflow_finished":
                            result = event.get("data")
                            if not isinstance(result, dict) or result.get("status") != "succeeded" or ending is None:
                                raise DifyError("Dify 執行未完成，請重新載入歷史紀錄。")
                            yield ending
                            return
                        elif kind in {"workflow_paused", "human_input_required"}:
                            raise DifyError("此應用需要人工輸入，目前聊天頁尚未支援此功能。")
                        elif kind == "error":
                            raise DifyError("Dify 生成失敗，請重新載入歷史紀錄。")
                        elif kind == "ping":
                            yield {"event": "ping"}
                    # An EOF is not a successful generation.
                    raise DifyError("Dify 串流已中斷，請重新載入歷史紀錄確認結果。")
        except httpx.TimeoutException as exc:
            raise DifyError("Dify 回應逾時，請重新載入歷史紀錄。", 504) from exc
        except httpx.HTTPError as exc:
            raise DifyError() from exc
