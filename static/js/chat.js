import {consumeSSE} from "./sse.mjs";

const app = document.getElementById("chat-app");
const byId = (id) => document.getElementById(id);
const messages = byId("messages");
const conversations = byId("conversations");
const status = byId("chat-status");
const query = byId("query");
const csrf = app.querySelector("[name=csrfmiddlewaretoken]").value;
let conversationId = "";
let taskId = "";
let historyCursor = "";
let listCursor = "";
let busy = false;
let loading = false;
let stopping = false;
let controller = null;
let listLoading = false;

function notice(text, error = false) {
  status.textContent = text;
  status.className = error ? "error" : "muted";
}

function controls() {
  const locked = busy || loading;
  byId("new-conversation").disabled = locked;
  byId("send-message").disabled = locked;
  query.disabled = locked;
  byId("stop-generation").disabled = !busy || !taskId || stopping;
  byId("older-messages").disabled = locked;
  byId("more-conversations").disabled = locked || listLoading;
  for (const button of conversations.querySelectorAll("button")) {
    button.disabled = locked;
    button.setAttribute("aria-current", button.dataset.id === conversationId ? "true" : "false");
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {"X-CSRFToken": csrf, ...options.headers},
  });
  if (response.redirected) throw new Error("登入已失效，請重新登入。");
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `請求失敗（${response.status}），請重新整理或稍後再試。`);
  }
  return response;
}

function post(url, body, signal) {
  return request(url, {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body), signal});
}

function message(role, text) {
  const node = document.createElement("article");
  node.className = `message message-${role}`;
  const label = document.createElement("strong");
  label.textContent = role === "user" ? "你" : "Bot";
  const content = document.createElement("div");
  content.textContent = text;
  node.append(label, content);
  return {node, content};
}

async function loadConversations(reset = false) {
  if (listLoading) return;
  listLoading = true;
  controls();
  try {
    const url = new URL(app.dataset.conversationsUrl, location.origin);
    if (!reset && listCursor) url.searchParams.set("last_id", listCursor);
    const data = await (await request(url)).json();
    if (reset) conversations.replaceChildren();
    for (const row of data.data) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = row.name;
      button.dataset.id = row.id;
      button.addEventListener("click", () => loadHistory(row.id));
      const item = document.createElement("li");
      item.append(button);
      conversations.append(item);
    }
    listCursor = data.next_cursor;
    byId("more-conversations").hidden = !data.has_more || !listCursor;
  } catch (error) {
    notice(error.message, true);
  } finally {
    listLoading = false;
    controls();
  }
}

async function loadHistory(id, older = false) {
  if (busy || loading) return;
  loading = true;
  controls();
  notice("載入對話中…");
  try {
    const url = new URL(`${app.dataset.conversationsUrl}${encodeURIComponent(id)}/messages/`, location.origin);
    if (older && historyCursor) url.searchParams.set("first_id", historyCursor);
    const data = await (await request(url)).json();
    const fragment = document.createDocumentFragment();
    for (const row of data.data) {
      fragment.append(message("user", row.query).node, message("assistant", row.answer).node);
    }
    const previousHeight = messages.scrollHeight;
    if (older) messages.prepend(fragment);
    else messages.replaceChildren(fragment);
    conversationId = id;
    historyCursor = data.next_cursor;
    byId("older-messages").hidden = !data.has_more || !historyCursor;
    messages.scrollTop = older ? messages.scrollHeight - previousHeight : messages.scrollHeight;
    notice("已載入歷史對話，可繼續傳送訊息。");
  } catch (error) {
    notice(error.message, true);
  } finally {
    loading = false;
    controls();
  }
}

byId("new-conversation").addEventListener("click", () => {
  if (busy || loading) return;
  conversationId = "";
  historyCursor = "";
  taskId = "";
  messages.replaceChildren();
  byId("older-messages").hidden = true;
  query.value = "";
  notice("輸入訊息以開始新對話。");
  controls();
  query.focus();
});
byId("more-conversations").addEventListener("click", () => loadConversations());
byId("older-messages").addEventListener("click", () => loadHistory(conversationId, true));

byId("message-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = query.value.trim();
  if (!text || busy || loading) return;
  busy = true;
  taskId = "";
  stopping = false;
  const current = new AbortController();
  controller = current;
  controls();
  messages.append(message("user", text).node);
  const reply = message("assistant", "");
  messages.append(reply.node);
  notice("等待回覆…");
  let accepted = false;
  try {
    const response = await post(app.dataset.sendUrl, {query: text, conversation_id: conversationId}, current.signal);
    if (!response.headers.get("content-type")?.includes("text/event-stream")) {
      throw new Error("未收到聊天串流，請重新登入或聯絡管理員。");
    }
    query.value = "";
    await consumeSSE(response.body, (chunk) => {
      if (chunk.conversation_id) conversationId = chunk.conversation_id;
      if (chunk.task_id) taskId = chunk.task_id;
      if (chunk.event === "start") accepted = true;
      if (chunk.event === "delta") {
        reply.content.textContent += chunk.text;
        notice("回覆中…");
      } else if (chunk.event === "replace") {
        reply.content.textContent = chunk.text;
      } else if (chunk.event === "end") {
        notice("回覆完成。");
      } else if (chunk.event === "error") {
        throw new Error(chunk.message);
      }
      controls();
      messages.scrollTop = messages.scrollHeight;
    });
  } catch (error) {
    if (error.name !== "AbortError") {
      reply.node.dataset.incomplete = "true";
      notice(error.message, true);
    }
  } finally {
    busy = false;
    stopping = false;
    taskId = "";
    controller = null;
    controls();
    query.focus();
    // Refresh only after Dify has accepted a generation; no automatic resend.
    if (accepted) await loadConversations(true);
  }
});

byId("stop-generation").addEventListener("click", async () => {
  if (!busy || !taskId || stopping) return;
  const current = controller;
  stopping = true;
  controls();
  try {
    await post(app.dataset.stopUrl, {task_id: taskId});
    if (controller === current && busy) {
      notice("已送出停止請求；完整紀錄以 Dify 為準。");
      current.abort();
    }
  } catch (error) {
    if (controller === current) notice(error.message, true);
  } finally {
    if (controller === current) {
      stopping = false;
      controls();
    }
  }
});

window.addEventListener("pagehide", () => controller?.abort());
loadConversations(true);
