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
  answer?: string; knowledge_point: string  // 判卷前服务端会剥离 answer
}
export interface QuizRecord {
  id: string; topic: string; questions: QuizQ[]
  answers: { qid: string; verdict: string; analysis: string; knowledge_point: string
    user_answer?: string; correct_answer?: string }[]
}
export interface MemoryData {
  l1_count: number
  l2: { id: string; content: string; created_at: number }[]
  l3: { id: string; kind: string; content: string; created_at: number }[]
}
export interface Book {
  id: string; title: string; author: string; subject: string; publisher: string
  license: string; note: string; pdf_url: string; source_url: string
  status: string; path: string; error: string
}
export interface MasteryPoint {
  id: string; point: string; score: number; attempts: number; correct: number
  wrong: number; box: number; due_at: number; status: string; updated_at: number
}
export interface MasteryData {
  points: MasteryPoint[]
  weak_count: number
  mastered_count: number
  due: MasteryPoint[]
  recent_feedback: { id: string; rating: string; understood: number; confusion: string }[]
}
export interface LlmStatus {
  routing: string
  local: { base_url: string; model: string }
  cloud: { base_url: string; model: string; api_key_masked: string; configured: boolean }
  max_context_chars: number
}
export interface HandbookMeta { id: string; title: string; space_id: string; created_at: number }
export interface Handbook {
  id: string; title: string; profile: Record<string, unknown>
  space_id: string; content: string; created_at: number
  sources?: string[]
}
export interface WrongQ {
  id: string; type: string; question: string; options: string[]; answer: string
  knowledge_point: string; verdict: string; analysis: string; user_answer: string
  quiz_id: string; quiz_topic: string; quiz_created_at: number
}
export interface Flashcard {
  id: string; front: string; back: string; point: string
  box: number; due_at: number
  state?: number; stability?: number; reps?: number; lapses?: number
  preview?: Record<string, number>  // FSRS 四档评分的下次间隔（秒），仅到期复习流附带
}
export interface PlanTask {
  id: string; phase: string; content: string; accept: string
  points: string[]; due_date: string; done: number; done_at: number
}
export interface TodayData {
  date: string
  due_points: MasteryPoint[]
  due_total: number
  flash_due: number; flash_total: number
  tasks_today: PlanTask[]
  tasks_unscheduled: PlanTask[]
  done_today: PlanTask[]
  wrong_count: number
}
export interface GraphNode {
  point: string; p_known: number | null; status: string
  attempts: number; correct: number; wrong: number
}
export interface GraphEdge { from_point: string; to_point: string; source: string }
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[] }
export interface MasteryHistoryPoint { point: string; score: number; verdict: string; created_at: number }
export interface TeachResult {
  verdict: string; missed: string[]; wrong: string[]
  analysis: string; knowledge_point: string
}
export interface StudentProfile {
  current_school: string; major: string; year: string; rank_hint: string
  flags: string[]; goal_type: string; target_school: string
  target_major: string; timeline: string; notes: string
  updated_at?: number
}
export interface SpaceOverview {
  id: string; name: string; points: number; weak: number; mastered: number
  avg: number; due: number; quizzes: number; flash_due: number
}
export interface DefectPoint {
  point: string; p_known: number; eff_known: number; retention: number
  risk: number; inherited_risk: number
  prereqs: { point: string; p_known: number; status: string; eff: number }[]
  downstream: string[]
  evidence: { attempts: number; wrong: number; correct: number; box: number
    due_in_hours: number; error_types: Record<string, number> }
  note: string
}
export interface DefectDiag {
  has_graph: boolean; edge_count: number
  repair_order: string[]; chains: string[][]; points: DefectPoint[]
}
export interface CurriculumMeta { file: string; course: string; concepts: number }

// ---- 学涯规划 ----
export interface SyllabusSchool {
  name: string; abbr?: string[]; city: string; province: string
  region: string; tier: '985' | '211'; strong: string[]
}
export interface SyllabusStats { schools: number; schools_985: number; programs: number; official: number; custom: number }
export interface SyllabusOfficial { school: string; major: string; source_version: string; source_url: string; sections: string[] }
export interface SyllabusFulltext {
  school: string; major: string; source_version: string
  source_url: string; source_note: string; chars: number; text: string
}
export interface SyllabusMajors {
  school: string; tier: string
  official_majors: string[]
  template_majors: string[]
  custom_majors: string[]; strong: string[]
}
export interface SemesterPlan { term: string; key_courses: string[]; milestone: string }
export interface Program {
  school: string; school_tier: string; major: string; matched_major: string | null
  coverage: 'official' | 'custom+official' | 'custom' | 'template' | 'none'
  note?: string; source_note?: string; custom_source?: string; school_strong?: string[]
  source_type?: string; source_version?: string; source_url?: string
  official_source?: boolean; has_fulltext?: boolean
  official_sections?: string[]
  category?: string; degree?: string; duration_years?: number
  credits_reference?: Record<string, number>
  training_goal?: string; core_courses?: string[]
  featured_courses?: string; grad_requirements?: string; exam_notes?: string
  course_structure_note?: string
  course_groups?: { group: string; courses: { name: string; credit: number }[] }[]
  course_prereqs?: Record<string, string[]>
  semester_plan?: SemesterPlan[]
  paths?: Record<string, unknown>
}
export interface CourseEntry {
  id?: string; course: string; day: number; period: string
  weeks: string; teacher: string; room: string; kind: string
}
export interface ScheduleData {
  term: string; terms: { term: string; courses: number }[]; courses: CourseEntry[]
}
export interface CareerTask {
  id: string; phase: string; content: string; accept: string; course: string
  done: boolean; done_at: number
}
export interface CareerPlanMeta {
  id: string; title: string; school: string; major: string; goal_type: string
  target: string; term: string; horizon: string; summary: string; created_at: number
}
export interface CareerPlan extends CareerPlanMeta {
  tasks: CareerTask[]; markdown: string
}

const BASE = ''

async function j<T>(res: Promise<Response>): Promise<T> {
  const r = await res
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail || '请求失败')
  return r.json()
}

// 写操作统一走状态检查：裸 fetch 对 HTTP 400/404/500 会当成功 resolve，
// 导致删除/打卡失败时界面毫无反应
async function ok(res: Promise<Response>): Promise<{ ok: boolean }> {
  const r = await res
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail || '请求失败')
  return r.json().catch(() => ({ ok: true }))
}

export const api = {
  health: () => j<{ status: string; llm: boolean; model: string }>(fetch(`${BASE}/api/health`)),
  listSpaces: () => j<Space[]>(fetch(`${BASE}/api/spaces`)),
  createSpace: (name: string, description: string) =>
    j<Space>(fetch(`${BASE}/api/spaces`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description }) })),
  deleteSpace: (id: string) => ok(fetch(`${BASE}/api/spaces/${id}`, { method: 'DELETE' })),

  listDocs: (sid: string) => j<Doc[]>(fetch(`${BASE}/api/spaces/${sid}/documents`)),
  uploadDoc: (sid: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return j<Doc>(fetch(`${BASE}/api/spaces/${sid}/documents`, { method: 'POST', body: fd }))
  },
  deleteDoc: (sid: string, did: string) =>
    ok(fetch(`${BASE}/api/spaces/${sid}/documents/${did}`, { method: 'DELETE' })),
  listMessages: (sid: string) => j<Msg[]>(fetch(`${BASE}/api/spaces/${sid}/messages`)),
  chat: (sid: string, mode: string, message: string, guide = false) =>
    j<{ reply: string; citations: Citation[]; expert: string }>(fetch(`${BASE}/api/spaces/${sid}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, message, guide }),
    })),
  listSkills: () => j<{ id: string; name: string }[]>(fetch(`${BASE}/api/skills`)),
  listExperts: () => j<{ id: string; name: string; description: string }[]>(fetch(`${BASE}/api/experts`)),
  runSkill: (sid: string, skill: string, params: object) =>
    j<any>(fetch(`${BASE}/api/spaces/${sid}/skills`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ skill, params }),
    })),
  quizzes: (sid: string) => j<QuizRecord[]>(fetch(`${BASE}/api/spaces/${sid}/quizzes`)),
  memory: (sid: string) => j<MemoryData>(fetch(`${BASE}/api/spaces/${sid}/memory`)),
  clearMemory: (sid: string, level: number) => ok(fetch(`${BASE}/api/spaces/${sid}/memory/${level}`, { method: 'DELETE' })),

  library: (query = '', subject = '') =>
    j<Book[]>(fetch(`${BASE}/api/library?query=${encodeURIComponent(query)}&subject=${encodeURIComponent(subject)}`)),
  librarySubjects: () => j<string[]>(fetch(`${BASE}/api/library/subjects`)),
  uploadBook: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return j<{ id: string; status: string }>(fetch(`${BASE}/api/library/upload`, { method: 'POST', body: fd }))
  },
  fetchBook: (bid: string) =>
    j<{ id: string; status: string; bytes: number }>(fetch(`${BASE}/api/library/${bid}/fetch`, { method: 'POST' })),
  attachBook: (bid: string, sid: string) =>
    j<{ document_id: string; status: string; chunks: number }>(fetch(`${BASE}/api/library/${bid}/attach`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ space_id: sid }),
    })),
  bookSpaces: (bid: string) => j<Space[]>(fetch(`${BASE}/api/library/${bid}/spaces`)),
  deleteBook: (bid: string) => ok(fetch(`${BASE}/api/library/${bid}`, { method: 'DELETE' })),

  sendFeedback: (sid: string, message_id: string, rating: string, understood: number, confusion: string) =>
    j<{ ok: boolean; points: string[] }>(fetch(`${BASE}/api/spaces/${sid}/feedback`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id, rating, understood, confusion }),
    })),
  mastery: (sid: string) => j<MasteryData>(fetch(`${BASE}/api/spaces/${sid}/mastery`)),
  reviewDue: (sid: string) => j<{ due: MasteryPoint[]; weakest: MasteryPoint[] }>(
    fetch(`${BASE}/api/spaces/${sid}/review/due`)),
  llmConfig: () => j<LlmStatus>(fetch(`${BASE}/api/llm/config`)),
  updateLlmConfig: (patch: { routing?: string; cloud_base_url?: string; cloud_api_key?: string; cloud_model?: string }) =>
    j<LlmStatus>(fetch(`${BASE}/api/llm/config`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    })),
  testLlm: () => j<Record<string, { ok: boolean; latency_ms?: number; error?: string }>>(
    fetch(`${BASE}/api/llm/test`, { method: 'POST' })),

  generateHandbook: (profile: object) =>
    j<Handbook>(fetch(`${BASE}/api/handbook/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(profile),
    })),
  handbooks: () => j<HandbookMeta[]>(fetch(`${BASE}/api/handbook`)),
  handbook: (hid: string) => j<Handbook>(fetch(`${BASE}/api/handbook/${hid}`)),
  deleteHandbook: (hid: string) => ok(fetch(`${BASE}/api/handbook/${hid}`, { method: 'DELETE' })),

  wrongQuestions: (sid: string) => j<WrongQ[]>(fetch(`${BASE}/api/spaces/${sid}/wrong-questions`)),
  redoWrong: (sid: string, qids: string[]) =>
    j<{ quiz_id: string; questions: QuizQ[]; redo_count: number }>(fetch(`${BASE}/api/spaces/${sid}/wrong-questions/redo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qids }),
    })),
  flashcards: (sid: string, due = false) =>
    j<{ cards: Flashcard[]; stats: { total: number; due: number } }>(
      fetch(`${BASE}/api/spaces/${sid}/flashcards?due=${due ? 1 : 0}`)),
  gradeFlashcard: (sid: string, fid: string, rating: number) =>
    j<{ id: string; box: number; due_at: number; interval: number; reps: number; lapses: number }>(
      fetch(`${BASE}/api/spaces/${sid}/flashcards/${fid}/grade`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rating }),
      })),
  clearFlashcards: (sid: string) => ok(fetch(`${BASE}/api/spaces/${sid}/flashcards`, { method: 'DELETE' })),
  plan: (sid: string) => j<{ tasks: PlanTask[]; done: number; total: number }>(
    fetch(`${BASE}/api/spaces/${sid}/plan`)),
  togglePlanTask: (sid: string, tid: string, done: boolean) =>
    ok(fetch(`${BASE}/api/spaces/${sid}/plan/${tid}/toggle`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ done }),
    })),
  setTaskDate: (sid: string, tid: string, dueDate: string) =>
    j<{ id: string; due_date: string }>(fetch(`${BASE}/api/spaces/${sid}/plan/${tid}/date`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ due_date: dueDate }),
    })),
  today: (sid: string) => j<TodayData>(fetch(`${BASE}/api/spaces/${sid}/today`)),
  graph: (sid: string) => j<GraphData>(fetch(`${BASE}/api/spaces/${sid}/graph`)),
  masteryHistory: (sid: string) => j<MasteryHistoryPoint[]>(fetch(`${BASE}/api/spaces/${sid}/mastery/history`)),
  importUrl: (url: string, title: string) =>
    j<{ id: string; title: string; chars: number }>(fetch(`${BASE}/api/library/url`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, title }),
    })),
  connectors: () => j<{ builtin: { name: string; description: string }[]; mcp: { name: string; command: string[] }[] }>(
    fetch(`${BASE}/api/connectors`)),
  registerMcp: (name: string, command: string[]) =>
    ok(fetch(`${BASE}/api/connectors/mcp`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, command }),
    })),
  removeMcp: (name: string) => ok(fetch(`${BASE}/api/connectors/mcp/${encodeURIComponent(name)}`, { method: 'DELETE' })),

  // 导出：返回原始 markdown 文本供前端另存
  exportMd: async (sid: string, kind: 'report' | 'wrong' | 'plan') => {
    const r = await fetch(`${BASE}/api/spaces/${sid}/export?kind=${kind}`)
    if (!r.ok) throw new Error('导出失败')
    return r.text()
  },

  profile: () => j<StudentProfile>(fetch(`${BASE}/api/profile`)),
  saveProfile: (p: StudentProfile) =>
    j<StudentProfile>(fetch(`${BASE}/api/profile`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p),
    })),
  profileOverview: () => j<{ spaces: SpaceOverview[] }>(fetch(`${BASE}/api/profile/overview`)),
  defects: (sid: string) => j<DefectDiag>(fetch(`${BASE}/api/spaces/${sid}/defects`)),
  curriculums: () => j<CurriculumMeta[]>(fetch(`${BASE}/api/curriculum`)),

  // ---- 学涯规划 ----
  syllabusStats: () => j<SyllabusStats>(fetch(`${BASE}/api/syllabus/stats`)),
  officialSources: () => j<SyllabusOfficial[]>(fetch(`${BASE}/api/syllabus/official`)),
  syllabusFulltext: (school: string, major: string) =>
    j<SyllabusFulltext>(fetch(`${BASE}/api/syllabus/fulltext?school=${encodeURIComponent(school)}&major=${encodeURIComponent(major)}`)),
  schools: (q = '', region = '', tier = '') =>
    j<SyllabusSchool[]>(fetch(`${BASE}/api/syllabus/schools?q=${encodeURIComponent(q)}&region=${encodeURIComponent(region)}&tier=${encodeURIComponent(tier)}`)),
  majorsForSchool: (school: string) =>
    j<SyllabusMajors>(fetch(`${BASE}/api/syllabus/majors?school=${encodeURIComponent(school)}`)),
  program: (school: string, major: string) =>
    j<Program>(fetch(`${BASE}/api/syllabus/program?school=${encodeURIComponent(school)}&major=${encodeURIComponent(major)}`)),
  importSyllabusText: (school: string, major: string, text: string) =>
    j<{ school: string; major: string; fields_found: string[] }>(fetch(`${BASE}/api/syllabus/import`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ school, major, text }),
    })),
  importSyllabusFile: (school: string, major: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return j<{ school: string; major: string; fields_found: string[] }>(
      fetch(`${BASE}/api/syllabus/import/file?school=${encodeURIComponent(school)}&major=${encodeURIComponent(major)}`,
        { method: 'POST', body: fd }))
  },
  schedule: (term = '') => j<ScheduleData>(fetch(`${BASE}/api/schedule?term=${encodeURIComponent(term)}`)),
  importScheduleText: (text: string) =>
    j<{ courses: CourseEntry[]; method: string }>(fetch(`${BASE}/api/schedule/import`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
    })),
  importScheduleFile: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return j<{ courses: CourseEntry[]; method: string }>(
      fetch(`${BASE}/api/schedule/import/file`, { method: 'POST', body: fd }))
  },
  saveSchedule: (term: string, courses: CourseEntry[]) =>
    j<{ term: string; saved: number; courses: CourseEntry[] }>(fetch(`${BASE}/api/schedule`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ term, courses }),
    })),
  deleteSchedule: (term: string) =>
    ok(fetch(`${BASE}/api/schedule?term=${encodeURIComponent(term)}`, { method: 'DELETE' })),
  careerPlans: () => j<CareerPlanMeta[]>(fetch(`${BASE}/api/planner`)),
  careerPlan: (pid: string) => j<CareerPlan>(fetch(`${BASE}/api/planner/${pid}`)),
  generateCareerPlan: (p: { school: string; major: string; year: string; goal_type: string; target: string; term: string; horizon: string }) =>
    j<CareerPlan & { course_spaces: Record<string, string> }>(fetch(`${BASE}/api/planner/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p),
    })),
  toggleCareerTask: (pid: string, taskId: string, done: boolean) =>
    ok(fetch(`${BASE}/api/planner/${pid}/toggle`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, done }),
    })),
  pushCareerPlan: (pid: string, spaceId: string, replace = false) =>
    j<{ synced: number; kept_done?: number }>(fetch(`${BASE}/api/planner/${pid}/push`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ space_id: spaceId, replace }),
    })),
  deleteCareerPlan: (pid: string) => ok(fetch(`${BASE}/api/planner/${pid}`, { method: 'DELETE' })),
}

export function chatStream(
  sid: string, mode: string, message: string,
  onDelta: (t: string) => void,
  onDone: (meta: { expert: string; citations: Citation[]; assistant_message_id?: string }) => void,
  guide = false,
  onError?: (msg: string) => void,
) {
  // 失败必须回调 onError 并结束 busy：此前 fetch 无 catch、不查 r.ok、也不认 error 事件，
  // 模型不可用/断流时发送按钮永久禁用且无任何提示
  fetch(`${BASE}/api/spaces/${sid}/chat/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, message, guide }),
  }).then(async (r) => {
    if (!r.ok || !r.body) {
      const detail = await r.json().catch(() => null)
      throw new Error(detail?.detail || `请求失败（${r.status}）`)
    }
    const reader = r.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let finished = false
    for (; ;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const p of parts) {
        const line = p.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        let evt: any
        try {
          evt = JSON.parse(line.slice(5))
        } catch { continue }
        if (evt.type === 'delta') onDelta(evt.text)
        if (evt.type === 'done') {
          finished = true
          onDone({ expert: evt.expert, citations: evt.citations, assistant_message_id: evt.assistant_message_id })
        }
        if (evt.type === 'error') throw new Error(evt.message || '生成回答失败')
      }
    }
    if (!finished) throw new Error('连接中断，未收到完整回答')
  }).catch((e: any) => onError?.(e?.message || '网络错误：无法连接服务'))
}
