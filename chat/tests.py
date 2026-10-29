import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest import skipIf
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import AsyncClient, RequestFactory, SimpleTestCase, TestCase, tag
from django.urls import reverse

from bots.models import Bot

from . import views
from .dify import DifyAdapter, DifyError, SSEParser, httpx

CONVERSATION = "01a71da2-846c-4b83-8b96-15a3bbf1f910"
TASK = "66ba2908-4539-4007-879b-d010c6bcf0ba"


class SSEParserTests(SimpleTestCase):
    def test_comments_ping_and_multiline_json(self):
        parser = SSEParser()
        self.assertIsNone(parser.feed(": comment"))
        self.assertIsNone(parser.feed(""))
        parser.feed("event: ping")
        self.assertEqual(parser.feed(""), {"event": "ping"})
        parser.feed('data: {"event": "message",')
        parser.feed('data: "answer": "你好"}')
        self.assertEqual(parser.feed(""), {"event": "message", "answer": "你好"})

    def test_invalid_json_or_non_object_is_rejected(self):
        for value in ["invalid", "[]", "null"]:
            parser = SSEParser()
            parser.feed(f"data: {value}")
            with self.assertRaises(DifyError):
                parser.feed("")


@skipIf(httpx is None, "Install requirements.txt to test the HTTPX Dify adapter")
class DifyAdapterTests(SimpleTestCase):
    def setUp(self):
        self.bot = SimpleNamespace(api_base_url="https://dify.example.test/v1", api_key="app-test-secret")
        self.user_id = uuid.uuid4()
        self.requests = []

    def adapter(self, response):
        def handler(request):
            self.requests.append(request)
            return response
        return DifyAdapter(self.bot, self.user_id, transport=httpx.MockTransport(handler))

    def stream(self, events):
        text = "event: ping\n\n" + "".join(
            f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events
        )
        return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})

    def collect(self, adapter):
        async def run():
            return [event async for event in adapter.send_message("你好", CONVERSATION)]
        return asyncio.run(run())

    def test_list_conversations_uses_server_identity_and_cursor(self):
        adapter = self.adapter(httpx.Response(200, json={"data": [
            {"id": CONVERSATION, "name": "History", "inputs": {"private": "hidden"}},
        ], "has_more": True}))
        result = asyncio.run(adapter.list_conversations(CONVERSATION))
        request = self.requests[0]
        self.assertEqual(request.url.path, "/v1/conversations")
        self.assertEqual(request.url.params["user"], str(self.user_id))
        self.assertEqual(request.url.params["last_id"], CONVERSATION)
        self.assertEqual(request.headers["authorization"], "Bearer app-test-secret")
        self.assertNotIn("inputs", result["data"][0])
        self.assertEqual(result["next_cursor"], CONVERSATION)

    def test_history_is_chronological_and_cursor_points_to_oldest(self):
        adapter = self.adapter(httpx.Response(200, json={"data": [
            {"id": "new", "query": "q2", "answer": "a2", "created_at": 2},
            {"id": "old", "query": "q1", "answer": "a1", "created_at": 1},
        ], "has_more": True}))
        result = asyncio.run(adapter.list_messages(CONVERSATION, TASK))
        self.assertEqual(result["next_cursor"], "old")
        self.assertEqual([row["id"] for row in result["data"]], ["old", "new"])
        self.assertEqual(self.requests[0].url.params["conversation_id"], CONVERSATION)
        self.assertEqual(self.requests[0].url.params["first_id"], TASK)
        self.assertEqual(self.requests[0].url.params["user"], str(self.user_id))

    def test_stream_preserves_identity_and_normalizes_events(self):
        adapter = self.adapter(self.stream([
            {"event": "message", "answer": "你好", "conversation_id": CONVERSATION, "task_id": TASK},
            {"event": "message_replace", "answer": "您好"},
            {"event": "message_end", "conversation_id": CONVERSATION},
        ]))
        events = self.collect(adapter)
        self.assertEqual([e["event"] for e in events], ["ping", "start", "delta", "replace", "start", "end"])
        body = json.loads(self.requests[0].content)
        self.assertEqual(body["user"], str(self.user_id))
        self.assertEqual(body["conversation_id"], CONVERSATION)
        self.assertEqual(body["response_mode"], "streaming")

    def test_utf8_and_sse_frames_can_span_network_chunks(self):
        wire = ('data: {"event":"message","answer":"你好"}\r\n\r\n'
                'data: {"event":"message_end"}\r\n\r\n').encode()

        class Chunks(httpx.AsyncByteStream):
            async def __aiter__(self):
                for byte in wire:
                    yield bytes([byte])

        adapter = self.adapter(httpx.Response(
            200, stream=Chunks(), headers={"content-type": "text/event-stream"},
        ))
        events = self.collect(adapter)
        self.assertEqual(events[0], {"event": "delta", "text": "你好"})
        self.assertEqual(events[-1]["event"], "end")

    def test_workflow_waits_for_successful_finish(self):
        adapter = self.adapter(self.stream([
            {"event": "workflow_started"}, {"event": "message_end"},
            {"event": "workflow_finished", "data": {"status": "succeeded"}},
        ]))
        self.assertEqual(self.collect(adapter)[-1]["event"], "end")

    def test_failed_workflow_and_premature_eof_are_not_success(self):
        for events in [
            [{"event": "message", "answer": "partial"}],
            [{"event": "workflow_started"}, {"event": "message_end"},
             {"event": "workflow_finished", "data": {"status": "failed"}}],
            [{"event": "error", "message": "private upstream detail"}],
        ]:
            with self.assertRaises(DifyError) as result:
                self.collect(self.adapter(self.stream(events)))
            self.assertNotIn("private upstream detail", str(result.exception))

    def test_stop_uses_task_and_same_identity(self):
        adapter = self.adapter(httpx.Response(200, json={"result": "success"}))
        asyncio.run(adapter.stop_generation(TASK))
        self.assertEqual(self.requests[0].url.path, f"/v1/chat-messages/{TASK}/stop")
        self.assertEqual(json.loads(self.requests[0].content), {"user": str(self.user_id)})

    def test_upstream_errors_do_not_expose_secrets(self):
        for status in [400, 401, 404, 429, 500, 302]:
            adapter = self.adapter(httpx.Response(status, text="app-test-secret"))
            with self.assertRaises(DifyError) as result:
                asyncio.run(adapter.list_conversations())
            self.assertNotIn("app-test-secret", str(result.exception))

    def test_timeout_and_invalid_json_are_safe_errors(self):
        def timeout(request):
            raise httpx.ReadTimeout("secret upstream address")
        adapter = DifyAdapter(self.bot, self.user_id, transport=httpx.MockTransport(timeout))
        with self.assertRaises(DifyError) as result:
            asyncio.run(adapter.list_conversations())
        self.assertEqual(result.exception.status, 504)
        with self.assertRaises(DifyError):
            asyncio.run(self.adapter(httpx.Response(200, text="not JSON")).list_conversations())

    def test_missing_key_fails_without_upstream_request(self):
        self.bot.api_key = ""
        with self.assertRaises(DifyError) as result:
            DifyAdapter(self.bot, self.user_id)
        self.assertEqual(result.exception.status, 503)

    def test_environment_variable_is_not_used_as_a_key(self):
        self.bot.api_key = "DIFY_TEST_KEY"
        with patch.dict("os.environ", {"DIFY_TEST_KEY": "a-different-secret"}):
            adapter = self.adapter(httpx.Response(200, json={"data": []}))
            asyncio.run(adapter.list_conversations())
        self.assertEqual(self.requests[0].headers["authorization"], "Bearer DIFY_TEST_KEY")


class ChatViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.adapter = SimpleNamespace(
            list_conversations=AsyncMock(return_value={"data": [], "has_more": False}),
            list_messages=AsyncMock(return_value={"data": [], "has_more": False}),
            stop_generation=AsyncMock(return_value={"result": "success"}),
        )
        self.context = patch("chat.views.resolve_context", AsyncMock(return_value=self.adapter))
        self.context.start()
        self.addCleanup(self.context.stop)

    def test_history_and_conversation_cursors_are_forwarded(self):
        response = asyncio.run(views.conversations(self.factory.get("/", {"last_id": TASK}), 1))
        self.assertEqual(response.status_code, 200)
        self.adapter.list_conversations.assert_awaited_once_with(TASK)
        response = asyncio.run(views.history(self.factory.get("/", {"first_id": TASK}), 1, uuid.UUID(CONVERSATION)))
        self.assertEqual(response.status_code, 200)
        self.adapter.list_messages.assert_awaited_once_with(CONVERSATION, TASK)

    def test_rejects_bad_json_unknown_fields_and_invalid_identifiers(self):
        for body in ["not JSON", "[]", {"query": ""}, {"query": "x" * 10001},
                     {"query": "hello", "user": "someone-else"},
                     {"query": "hello", "conversation_id": "../secrets"}]:
            request = self.factory.post("/", data=body, content_type="application/json")
            self.assertEqual(asyncio.run(views.send(request, 1)).status_code, 400)

    def test_stop_rejects_spoofed_user_or_bad_task(self):
        for body in [{"task_id": "../bad"}, {"task_id": TASK, "user": "someone-else"}]:
            request = self.factory.post("/", data=body, content_type="application/json")
            self.assertEqual(asyncio.run(views.stop(request, 1)).status_code, 400)
        self.adapter.stop_generation.assert_not_awaited()

    def test_stream_preserves_partial_text_and_reports_error(self):
        async def stream(query, conversation_id):
            yield {"event": "delta", "text": "partial"}
            raise DifyError("generation interrupted")
        self.adapter.send_message = stream
        request = self.factory.post("/", data={"query": "hello", "conversation_id": CONVERSATION}, content_type="application/json")
        async def run():
            response = await views.send(request, 1)
            self.assertEqual(response["X-Accel-Buffering"], "no")
            self.assertIn("no-store", response["Cache-Control"])
            return b"".join([chunk async for chunk in response.streaming_content]).decode()
        result = asyncio.run(run())
        self.assertIn('"text": "partial"', result)
        self.assertIn('"event": "error"', result)


@tag("async")
class ChatIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="chatmember")
        self.bot = Bot.objects.create(name="Support", api_key="app-chat-test-key")
        self.bot.allowed_users.add(self.user)

    def tearDown(self):
        cache.clear()

    async def test_api_requires_login_and_bot_grant(self):
        client = AsyncClient()
        url = reverse("chat:conversations", args=[self.bot.pk])
        self.assertEqual((await client.get(url)).status_code, 401)
        await client.aforce_login(self.user)
        with patch("chat.views.DifyAdapter") as adapter:
            adapter.return_value.list_conversations = AsyncMock(return_value={"data": []})
            self.assertEqual((await client.get(url)).status_code, 200)
            adapter.assert_called_once()
            self.assertEqual(adapter.call_args.args[1], self.user.dify_user_id)
        other = await get_user_model().objects.acreate(username="other")
        await client.aforce_login(other)
        self.assertEqual((await client.get(url)).status_code, 404)

    async def test_post_requires_csrf(self):
        client = AsyncClient(enforce_csrf_checks=True)
        await client.aforce_login(self.user)
        response = await client.post(reverse("chat:send", args=[self.bot.pk]),
                                     {"query": "hello"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
