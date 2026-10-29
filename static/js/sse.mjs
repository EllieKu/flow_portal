// The backend emits JSON SSE frames; decode incrementally across UTF-8 boundaries.
export async function consumeSSE(body, onEvent) {
  if (!body) throw new Error("瀏覽器無法讀取串流。");
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let data = [];
  let terminal = false;
  function line(value) {
    if (value.endsWith("\r")) value = value.slice(0, -1);
    if (value === "") {
      if (data.length) {
        const event = JSON.parse(data.join("\n"));
        data = [];
        if (["end", "error"].includes(event.event)) terminal = true;
        onEvent(event);
      }
    } else if (value.startsWith("data:")) {
      data.push(value.slice(5).replace(/^ /, ""));
    }
  }
  try {
    while (!terminal) {
      const {value, done} = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, {stream: true});
      let end;
      while ((end = buffer.indexOf("\n")) >= 0) {
        line(buffer.slice(0, end));
        buffer = buffer.slice(end + 1);
        if (terminal) break;
      }
      if (done) break;
    }
    if (!terminal) throw new Error("串流已中斷，請重新載入歷史紀錄確認結果。");
  } finally {
    try { await reader.cancel(); } finally { reader.releaseLock(); }
  }
}
