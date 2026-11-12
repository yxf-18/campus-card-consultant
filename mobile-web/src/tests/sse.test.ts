import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamChat } from '@/utils/sse'
describe('streamChat', () => {
  afterEach(() => vi.restoreAllMocks())
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined })
  it('parses delta and done events', async () => {
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('event: delta\ndata: {"content":"你好"}\n\nevent: done\ndata: {"message_id":1,"session_id":2}\n\n')); controller.close() } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const events: any[] = []
    await streamChat({ question: 'test' }, event => events.push(event))
    expect(events.map(event => event.event)).toEqual(['delta', 'done'])
    expect(events[0].data.content).toBe('你好')
  })

  it('parses a final done event without a trailing blank line', async () => {
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('event: delta\ndata: {"content":"你好"}\n\nevent: done\ndata: {"message_id":9,"session_id":3}')); controller.close() } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const events: any[] = []
    await streamChat({ question: 'test' }, event => events.push(event))
    expect(events.map(event => event.event)).toEqual(['delta', 'done'])
    expect(events[1].data.message_id).toBe(9)
  })
})
