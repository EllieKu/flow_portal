import {consumeSSE} from "./sse.mjs";
import {marked} from "../vendor/marked/marked.esm.js";
import DOMPurify from "../vendor/dompurify/purify.es.mjs";

marked.use({gfm: true, breaks: true});

const app = document.getElementById("chat-app");
const byId = (id) => document.getElementById(id);
const messages = byId("messages");
const conversations = byId("conversations");
const status = byId("chat-status");
const query = byId("query");
const csrf = app.querySelector("[name=csrfmiddlewaretoken]").value;
let assistantMark = "Bot";
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
  status.hidden = !text;
}

function renderMarkdown(node, markdown) {
  node.innerHTML = DOMPurify.sanitize(marked.parse(markdown));
}

function updateEmptyState() {
  byId("chat-empty").hidden = messages.childElementCount > 0;
}

function resizeComposer() {
  query.style.height = "0";
  query.style.height = `${Math.min(query.scrollHeight, 160)}px`;
  query.style.overflowY = query.scrollHeight > 160 ? "auto" : "hidden";
}

function setAppIcon(node, data) {
  node.replaceChildren();
  if (data.icon_type === "image" && data.icon_url) {
    const image = document.createElement("img");
    image.src = data.icon_url;
    image.alt = "";
    node.append(image);
  } else {
    node.textContent = data.icon || (data.title || byId("sidebar-title").textContent).charAt(0);
  }
  if (data.icon_background) node.style.backgroundColor = data.icon_background;
}

function controls() {
  const locked = busy || loading;
  const send = byId("send-message");
  const stop = byId("stop-generation");
  byId("new-conversation").disabled = locked;
  send.disabled = locked;
  send.hidden = busy;
  stop.hidden = !busy;
  query.disabled = locked;
  stop.disabled = !busy || !taskId || stopping;
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

async function loadSite() {
  try {
    const data = await (await request(app.dataset.siteUrl)).json();
    if (data.title) {
      byId("sidebar-title").textContent = data.title;
      byId("bot-title").textContent = data.title;
      document.title = `${data.title} · Flow Portal`;
    }

    const description = byId("bot-description");
    description.textContent = data.description || "";
    description.hidden = !data.description;

    setAppIcon(byId("site-icon"), data);
    setAppIcon(byId("empty-site-icon"), data);
    assistantMark = data.icon_type === "emoji" && data.icon ? data.icon : (data.title || "Bot").charAt(0);
    for (const label of messages.querySelectorAll(".message-assistant .message-avatar")) {
      label.textContent = assistantMark;
    }
    if (data.chat_color_theme) app.style.setProperty("--chat-accent", data.chat_color_theme);
    if (data.input_placeholder) query.placeholder = data.input_placeholder;

    const copyright = byId("site-copyright");
    copyright.textContent = data.copyright || "";
    byId("sidebar-footer").hidden = !data.copyright;
  } catch (_error) {
    // Keep the Portal Bot settings when Dify WebApp settings are unavailable.
  }
}

function message(role, text) {
  const node = document.createElement("article");
  node.className = `message message-${role}`;
  node.setAttribute("aria-label", role === "user" ? "你的訊息" : "Bot 回覆");
  const label = document.createElement("strong");
  label.className = role === "user" ? "message-avatar message-user-avatar" : "message-avatar";
  if (role === "user") {
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 24 24");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5Z");
    icon.append(path);
    label.append(icon);
  } else {
    label.textContent = assistantMark;
  }
  label.setAttribute("aria-hidden", "true");
  const content = document.createElement("div");
  content.className = "message-content";
  if (role === "assistant") {
    content.classList.add("markdown-body");
    content.dataset.markdown = text;
    renderMarkdown(content, text);
  } else {
    content.textContent = text;
  }
  if (role === "user") node.append(content, label);
  else node.append(label, content);
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
    updateEmptyState();
    conversationId = id;
    historyCursor = data.next_cursor;
    byId("older-messages").hidden = !data.has_more || !historyCursor;
    messages.scrollTop = older ? messages.scrollHeight - previousHeight : messages.scrollHeight;
    notice("");
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
  updateEmptyState();
  byId("older-messages").hidden = true;
  query.value = "";
  resizeComposer();
  notice("");
  controls();
  query.focus();
});
byId("more-conversations").addEventListener("click", () => loadConversations());
byId("older-messages").addEventListener("click", () => loadHistory(conversationId, true));
query.addEventListener("input", resizeComposer);
query.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    byId("message-form").requestSubmit();
  }
});

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
  updateEmptyState();
  notice("等待回覆…");
  let accepted = false;
  try {
    const response = await post(app.dataset.sendUrl, {query: text, conversation_id: conversationId}, current.signal);
    if (!response.headers.get("content-type")?.includes("text/event-stream")) {
      throw new Error("未收到聊天串流，請重新登入或聯絡管理員。");
    }
    query.value = "";
    resizeComposer();
    await consumeSSE(response.body, (chunk) => {
      if (chunk.conversation_id) conversationId = chunk.conversation_id;
      if (chunk.task_id) taskId = chunk.task_id;
      if (chunk.event === "start") accepted = true;
      if (chunk.event === "delta") {
        reply.content.dataset.markdown += chunk.text;
        renderMarkdown(reply.content, reply.content.dataset.markdown);
        notice("回覆中…");
      } else if (chunk.event === "replace") {
        reply.content.dataset.markdown = chunk.text;
        renderMarkdown(reply.content, chunk.text);
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
updateEmptyState();
resizeComposer();
loadSite();
loadConversations(true);
