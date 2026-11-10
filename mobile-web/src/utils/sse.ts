export type SSEEvent = { event: string; data: any }
export async function streamChat(body: Record<string, unknown>, onEvent: (event: SSEEvent) => void, signal?: AbortSignal) {
  const token = localStorage.getItem('mobile_token')
  const response = await fetch('/api/v1/chat/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body), signal
  })
  if (!response.ok || !response.body) {
    let message = '问答请求失败'
    try { message = (await response.json()).message || message } catch { /* ignore */ }
    throw new Error(message)
  }
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
  const newline = String.fromCharCode(10)
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split(newline + newline); buffer = frames.pop() || ''
    for (const frame of frames) {
      let event = 'message'; const dataLines: string[] = []
      for (const line of frame.split(newline)) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (!dataLines.length) continue
      try { onEvent({ event, data: JSON.parse(dataLines.join(newline)) }) } catch { /* ignore malformed frame */ }
    }
  }
}
