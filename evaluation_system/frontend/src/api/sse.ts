import type { SseEvent } from "../types/api";

export function parseSseBlock(block: string): SseEvent | null {
  let id: string | undefined;
  let event = "message";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line) continue;
    if (line.startsWith(":")) {
      if (line.toLowerCase().includes("redis unavailable")) return { event: "redis_unavailable", data: { error_code: "EVALUATION_REDIS_UNAVAILABLE" } };
      continue;
    }
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (!data.length && event === "message") return null;
  try {
    const parsed = data.length ? JSON.parse(data.join("\n")) : {};
    return { id, event, data: parsed && typeof parsed === "object" ? parsed : { value: parsed } };
  } catch {
    return { id, event, data: { parse_error: true } };
  }
}

export async function streamSse(
  response: Response,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  if (!response.body) throw new Error("SSE_STREAM_UNAVAILABLE");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) onEvent(event);
    }
    if (done) break;
  }
  const final = parseSseBlock(buffer);
  if (final) onEvent(final);
}
