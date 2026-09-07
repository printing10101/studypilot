// 共享类型与 API 封装
export interface Space { id: string; name: string; description: string }
export interface Doc { id: string; filename: string; status: string; chunks: number; error: string }
export interface Citation { index: number; source: string; score: number; snippet: string }
export interface Msg {
  id?: string; mode: string; role: 'user' | 'assistant'; content: string
  expert?: string; citations?: Citation[]
}
export interface QuizQ {
  id: string; type: string; question: string; options: string[]
  answer: string; knowledge_point: string
}
export interface QuizRecord {
  id: string; topic: string; questions: QuizQ[]
  answers: { qid: string; verdict: string; analysis: string; knowledge_point: string }[]
}
export interface MemoryData {
  l1_count: number
  l2: { id: string; content: string; created_at: number }[]
  l3: { id: string; kind: string; content: string; created_at: number }[]
}

const BASE = ''

async function j<T>(res: Promise<Response>): Promise<T> {
  const r = await res
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail || '请求失败')
  return r.json()
}

export const api = {
  health: () => j<{ status: string; llm: boolean; model: string }>(fetch(`${BASE}/api/health`)),
  listSpaces: () => j<Space[]>(fetch(`${BASE}/api/spaces`)),
  createSpace: (name: string, description: string) =>
    j<Space>(fetch(`${BASE}/api/spaces`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description }) })),
  deleteSpace: (id: string) => fetch(`${BASE}/api/spaces/${id}`, { method: 'DELETE' }),

  listDocs: (sid: string) => j<Doc[]>(fetch(`${BASE}/api/spaces/${sid}/documents`)),
  uploadDoc: (sid: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return j<Doc>(fetch(`${BASE}/api/spaces/${sid}/documents`, { method: 'POST', body: fd }))
  },
  listMessages: (sid: string) => j<Msg[]>(fetch(`${BASE}/api/spaces/${sid}/messages`)),
  chat: (sid: string, mode: string, message: string) =>
    j<{ reply: string; citations: Citation[]; expert: string }>(fetch(`${BASE}/api/spaces/${sid}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, message }),
    })),
  listSkills: () => j<{ id: string; name: string }[]>(fetch(`${BASE}/api/skills`)),
  listExperts: () => j<{ id: string; name: string; description: string }[]>(fetch(`${BASE}/api/experts`)),
  runSkill: (sid: string, skill: string, params: object) =>
    j<any>(fetch(`${BASE}/api/spaces/${sid}/skills`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ skill, params }),
    })),
  quizzes: (sid: string) => j<QuizRecord[]>(fetch(`${BASE}/api/spaces/${sid}/quizzes`)),
  memory: (sid: string) => j<MemoryData>(fetch(`${BASE}/api/spaces/${sid}/memory`)),
  clearMemory: (sid: string, level: number) => fetch(`${BASE}/api/spaces/${sid}/memory/${level}`, { method: 'DELETE' }),
}

export function chatStream(
  sid: string, mode: string, message: string,
  onDelta: (t: string) => void,
  onDone: (meta: { expert: string; citations: Citation[] }) => void,
) {
  fetch(`${BASE}/api/spaces/${sid}/chat/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, message }),
  }).then(async (r) => {
    const reader = r.body!.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (; ;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const p of parts) {
        const line = p.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        const evt = JSON.parse(line.slice(5))
        if (evt.type === 'delta') onDelta(evt.text)
        if (evt.type === 'done') onDone({ expert: evt.expert, citations: evt.citations })
      }
    }
  })
}
