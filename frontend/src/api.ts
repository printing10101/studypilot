// 共享类型与 API 封装
export interface Space { id: string; name: string; description: string }
export interface Doc { id: string; filename: string; status: string; chunks: number; error: string }
export interface Citation { index: number; source: string; score: number; snippet: string }
export interface Msg {
  id?: string; mode: string; role: 'user' | 'assistant'; content: string
  expert?: string; citations?: Citation[]; created_at?: number
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
  local: { base_url: string; model: string; api_key_masked?: string; custom?: boolean }
  cloud: { base_url: string; model: string; api_key_masked: string; configured: boolean }
  max_context_chars: number
}
export interface UsageDashboard {
  window_days: number
  totals: { calls: number; success_rate: number; tokens_in: number; tokens_out: number; tokens_total: number }
  by_channel: Record<string, {
    calls: number; success_rate: number; tokens_in: number; tokens_out: number
    tokens_total: number; avg_latency_ms: number; p50_latency_ms: number
  }>
  daily: {
    date: string; calls: number; tokens_in: number; tokens_out: number
    local_in: number; local_out: number; cloud_in: number; cloud_out: number
  }[]
  by_task: Record<string, { calls: number; tokens_in: number; tokens_out: number; tokens_total: number; success_rate: number }>
  by_model: Record<string, { calls: number; tokens_in: number; tokens_out: number; tokens_total: number; channel: string; success_rate: number }>
  recent: { ts: number; task: string; channel: string; model: string; latency_ms: number; tokens_in: number; tokens_out: number; ok: boolean }[]
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
export interface TakenCourse {
  id: string; name: string; credit: number; grade: string
  gpa: number; semester: string; status: string
}
export interface AuditResult {
  program_found: boolean; school?: string; major?: string; coverage?: string
  note?: string; taken_count?: number
  requirements?: { total: number; done: number; taking: number; missing: number }
  core_states?: { name: string; category: string; state: string; expected_term: string; credit: number; grade: string }[]
  credits?: { total_required: number; total_earned: number; progress: number | null
    by_category: { category: string; required: number; earned: number; done: number; total: number }[] }
  gpa?: number | null
  prereq_violations?: { course: string; missing_prereqs: string[] }[]
  ready_next?: { name: string; expected_term: string; credit: number }[]
  unmatched?: { name: string; credit: number; grade: string }[]
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
  method?: string
}
export interface LearningMethodItem {
  id: string; name: string; utility: string
  summary: string; how: string; avoid?: string; evidence?: string; why?: string
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
  question_bank?: { total: number; used: number }
  velocity?: {
    window_days: number; mastered_in_window: number; concepts_per_day: number
    velocity_trend: string; concepts_total: number; concepts_mastered: number
    concepts_remaining: number
  } | null
  forecast?: {
    is_complete: boolean; concepts_remaining: number; confidence: string
    optimistic_days: number | null; expected_days: number | null; pessimistic_days: number | null
    optimistic_date: string | null; expected_date: string | null; pessimistic_date: string | null
  } | null
  methods?: {
    tip: string; focus: string; daily: string; items: LearningMethodItem[]
    persona?: PersonaSummary | null
  } | null
  metrics?: {
    consistency: { streak: number; active_7d: number; active_30d: number; last_active: string }
    load: { due_points: number; flash_due: number; tasks_today: number; load_score: number
      band: string; suggested_minutes: number; advice: string }
    calibration: { n: number; avg_bias: number; label: string; avg_predicted?: number; avg_actual?: number }
    countdown: { deadline: string; days_left: number; phase: string; strategy: string; goal_type: string } | null
  } | null
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
  learner_personas?: string[]
  updated_at?: number
}
export interface LearnerPersonaMeta {
  id: string; name: string; blurb: string; tip: string; session: string
}
export interface PersonaSummary {
  primary: string; name: string; labels: string[]
  explicit: string[]; inferred: string[]; evidence: string[]
  session?: string; tone?: string; tip?: string
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
export interface DueDocReview {
  id: string; filename: string; due_at: number; state: number
  stability: number; reps: number; never_reviewed: boolean
}
export interface BktParam { point: string; p_l0: number; p_t: number; p_g: number; p_s: number; source: string }
export interface TransferOpportunity {
  source_concept: string; source_space: string; source_mastery: number
  target_concept: string; target_space: string; target_space_id: string
  target_mastery: number; similarity: number; recommendation: string
}
// ---- 竞赛规划 ----
export interface CompetitionItem {
  id: string; name: string; abbr: string; tier: string; organizer: string
  window_label: string; team: string; prep_weeks: number
  majors: string[]; goals: Record<string, number>; why: string
}
export interface CompetitionPick {
  id: string; name: string; abbr: string; tier: string; organizer: string
  window_label: string; team: string; prep_weeks: number; why: string
  value: number; major_match: boolean; specialist: boolean
  suggested_date: string | null
  lands_in_time: boolean; enough_prep: boolean; feasible: boolean
  score: number; note?: string
}
export interface CompetitionAnalysis {
  goal: string; goal_label: string
  school: string; major: string; target: string
  deadline: string | null; deadline_source: string
  months_left: number | null
  tier1: CompetitionPick[]; tier2: CompetitionPick[]; tier3: CompetitionPick[]
  catalog_count: number
  strategy_md: string; strategy_error: string
}

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
export interface CampusSourceCfg { id: string; name: string; url: string }
export interface CampusItem {
  id: number; source: string; title: string; url: string
  published: string; fetched_at: number
}
export interface NotifyCfg {
  enabled: boolean; channel: string
  serverchan_sendkey: string; wecom_webhook: string; push_hour: number
}
export interface NotifyStatus { config: NotifyCfg; last_push_date: string; last_error: string }
export interface CampusStatus {  network: {
    state: 'campus' | 'campus_likely' | 'public' | 'offline'
    label: string; detail: string
    latency_campus_ms: number | null; latency_external_ms: number | null
    checked_at: number
  }
  last_sync: {
    ts: number; added: number; network: string; skipped: boolean
    sources: { id: string; name: string; ok: boolean; new?: number; error?: string }[]
  } | null
  counts: Record<string, number>
  total: number
  config: {
    auto_sync: boolean; interval_min: number
    sources: CampusSourceCfg[]
    campus_hosts: string[]; internal_hosts: string[]; public_cidrs: string[]
  }
}

const BASE = ''

// 页面间跳转的附加定位：sub = 目标页子页签（如测验页的 wrong 错题本），
// quizId = 要滚动定位并高亮的具体卷子（每日一题 / 复习题 / 出 N 题练它）
export interface NavExtra { sub?: string; quizId?: string }

// FastAPI 校验错误的 detail 是数组、业务错误是字符串，直接塞给 Error 会显示 [object Object]
async function errMsg(r: Response): Promise<string> {
  const body: any = await r.json().catch(() => ({ detail: r.statusText }))
  const d = body.detail
  const msg = typeof d === 'string' ? d
    : Array.isArray(d) ? d.map((e: any) =>
      `${(e.loc || []).slice(1).join('.')}${e.msg ? `: ${e.msg}` : ''}`).join('；')
    : d && typeof d === 'object' ? JSON.stringify(d)
      : ''
  return msg || `请求失败（HTTP ${r.status}）`
}

async function j<T>(res: Promise<Response>): Promise<T> {
  const r = await res
  if (!r.ok) throw new Error(await errMsg(r))
  // 200 但 body 非 JSON（如代理/错误页 HTML）时给出可读错误，而不是裸 SyntaxError
  return r.json().catch(() => { throw new Error('响应不是有效 JSON（服务可能正在重启）') })
}

// 写操作统一走状态检查：裸 fetch 对 HTTP 400/404/500 会当成功 resolve，
// 导致删除/打卡失败时界面毫无反应
async function ok(res: Promise<Response>): Promise<{ ok: boolean }> {
  const r = await res
  if (!r.ok) throw new Error(await errMsg(r))
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
  // 重新索引失败/中断的文档（原文件还在时无需重传）
  reindexDoc: (sid: string, did: string) =>
    j<{ id: string; status: string; chunks: number }>(
      fetch(`${BASE}/api/spaces/${sid}/documents/${did}/reindex`, { method: 'POST' })),
  // B站视频字幕导入：拉 CC/AI 字幕转写为带 [mm:ss] 时间戳的文档参与 RAG
  importVideo: (sid: string, url: string) =>
    j<{ id: string; bvid: string; title: string; subtitle_lan: string; status: string; chunks: number; note?: string }>(
      fetch(`${BASE}/api/spaces/${sid}/video/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
      })),
  listMessages: (sid: string, opts: { limit?: number; before?: number } = {}) =>
    j<{ messages: Msg[]; has_more: boolean }>(
      fetch(`${BASE}/api/spaces/${sid}/messages?limit=${opts.limit ?? 200}${opts.before != null ? `&before=${opts.before}` : ''}`)),
  listSkills: () => j<{ id: string; name: string }[]>(fetch(`${BASE}/api/skills`)),
  listExperts: () => j<{ id: string; name: string; description: string }[]>(fetch(`${BASE}/api/experts`)),
  runSkill: (sid: string, skill: string, params: object) =>
    j<any>(fetch(`${BASE}/api/spaces/${sid}/skills`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ skill, params }),
    })),
  // 注：SSE 流式版为独立导出函数 runSkillStream（见文件末尾，与 chatStream 并列）
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
  updateLlmConfig: (patch: { routing?: string; cloud_base_url?: string; cloud_api_key?: string
    cloud_model?: string; local_base_url?: string; local_api_key?: string; local_model?: string }) =>
    j<LlmStatus>(fetch(`${BASE}/api/llm/config`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    })),
  // 「测试连通」可携带表单里正在编辑的值：未传字段回退到已保存配置
  testLlm: (form?: { local_base_url?: string; local_api_key?: string; local_model?: string
    cloud_base_url?: string; cloud_api_key?: string; cloud_model?: string }) =>
    j<Record<string, { ok: boolean; latency_ms?: number; error?: string }>>(
      fetch(`${BASE}/api/llm/test`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form || {}),
      })),

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
  learnerPersonas: () => j<{ personas: LearnerPersonaMeta[] }>(fetch(`${BASE}/api/learner-personas`)),
  predictQuiz: (sid: string, quizId: string, predicted: number) =>
    j<{ quiz_id: string; predicted: number }>(fetch(`${BASE}/api/spaces/${sid}/quiz/${quizId}/predict`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ predicted }),
    })),
  auditCourses: () => j<{ courses: TakenCourse[] }>(fetch(`${BASE}/api/audit/courses`)),
  addAuditCourse: (body: { name: string; credit: number; grade: string; semester: string; status: string }) =>
    j<TakenCourse>(fetch(`${BASE}/api/audit/courses`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })),
  importAuditCourses: (text: string) =>
    j<{ added: number; method: string }>(fetch(`${BASE}/api/audit/courses/import`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
    })),
  deleteAuditCourse: (cid: string) => ok(fetch(`${BASE}/api/audit/courses/${cid}`, { method: 'DELETE' })),
  clearAuditCourses: () => j<{ removed: number }>(fetch(`${BASE}/api/audit/courses/clear`, { method: 'POST' })),
  runAudit: (school = '', major = '') =>
    j<AuditResult>(fetch(`${BASE}/api/audit/run?school=${encodeURIComponent(school)}&major=${encodeURIComponent(major)}`)),
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
  generateCareerPlan: (p: { school: string; major: string; year: string; goal_type: string; target: string; term: string; horizon: string }, signal?: AbortSignal) =>
    j<CareerPlan & { course_spaces: Record<string, string> }>(fetch(`${BASE}/api/planner/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p), signal,
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

  // ---- 竞品借鉴新功能 ----
  dailyQuestion: (sid: string) => j<{
    source: string; point: string; quiz_id?: string
    questions?: QuizQ[]; p_correct: number | null; note?: string
  }>(fetch(`${BASE}/api/spaces/${sid}/daily-question`)),
  transferOpportunities: () => j<TransferOpportunity[]>(fetch(`${BASE}/api/transfer-opportunities`)),
  // 竞赛规划
  competitionCatalog: () => j<{ items: CompetitionItem[]; count: number; note: string }>(
    fetch(`${BASE}/api/competitions/catalog`)),
  competitionAnalyze: (body: { goal?: string; use_llm?: boolean } & Partial<StudentProfile>) =>
    j<CompetitionAnalysis>(fetch(`${BASE}/api/competitions/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })),
  // Anki 导入导出
  ankiImport: (sid: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return j<{ imported: number; skipped: number; errors: string[] }>(
      fetch(`${BASE}/api/spaces/${sid}/anki/import`, { method: 'POST', body: fd }))
  },
  ankiExportUrl: (sid: string) => `${BASE}/api/spaces/${sid}/anki/export`,
  // 讲义笔记级 FSRS 复习
  dueDocReviews: (sid: string) => j<DueDocReview[]>(fetch(`${BASE}/api/spaces/${sid}/doc-reviews/due`)),
  gradeDocReview: (sid: string, did: string, rating: number) =>
    j<{ id: string; interval_human: string; reps: number }>(fetch(
      `${BASE}/api/spaces/${sid}/doc-reviews/${did}/grade`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    })),
  // BKT 参数个性化拟合
  bktFit: (sid: string) => j<{ fitted_count: number; params: Record<string, unknown> }>(
    fetch(`${BASE}/api/spaces/${sid}/bkt/fit`, { method: 'POST' })),
  bktParams: (sid: string) => j<Record<string, Omit<BktParam, 'point'>>>(
    fetch(`${BASE}/api/spaces/${sid}/bkt/params`)),
  llmUsage: (days = 30) => j<UsageDashboard>(fetch(`${BASE}/api/llm/usage?days=${days}`)),
  clearLlmStats: () => ok(fetch(`${BASE}/api/llm/stats/clear`, { method: 'POST' })),
  // 校园网感知 · 校园信息自动同步
  campusStatus: (force = false) =>
    j<CampusStatus>(fetch(`${BASE}/api/campus/status${force ? '?force=1' : ''}`)),
  campusSync: () => j<{ added: number; network: string; skipped: boolean }>(
    fetch(`${BASE}/api/campus/sync`, { method: 'POST' })),
  campusItems: (source = '', limit = 100, q = '') =>
    j<{ items: CampusItem[] }>(fetch(`${BASE}/api/campus/items?source=${encodeURIComponent(source)}&limit=${limit}&q=${encodeURIComponent(q)}`)),
  campusConfig: (patch: Record<string, unknown>) =>
    j<CampusStatus>(fetch(`${BASE}/api/campus/config`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    })),
  // ---- 外部推送提醒 ----
  notifyStatus: () => j<NotifyStatus>(fetch(`${BASE}/api/notify`)),
  saveNotify: (patch: Partial<NotifyCfg>) =>
    j<{ config: NotifyCfg }>(fetch(`${BASE}/api/notify`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    })),
  testNotify: () => j<{ ok: boolean; error?: string }>(
    fetch(`${BASE}/api/notify/test`, { method: 'POST' })),
  pushNotify: () => j<{ pushed: boolean; reason: string }>(
    fetch(`${BASE}/api/notify/push`, { method: 'POST' })),
}

// SSE 帧解析（chatStream / runSkillStream 共用）：按 \n\n 分帧可抗 chunk 分包截断，
// 不完整帧留在 buf 等下一包；: ping 心跳注释帧没有 data: 行，自动跳过
async function consumeSSE(
  r: Response,
  onEvent: (evt: any) => 'done' | void,
): Promise<void> {
  if (!r.body) throw new Error(`请求失败（${r.status}）`)
  const reader = r.body.getReader()
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
      let evt: any
      try {
        evt = JSON.parse(line.slice(5))
      } catch { continue }
      if (onEvent(evt) === 'done') return
    }
  }
}

async function sseResponse(res: Promise<Response>): Promise<Response> {
  const r = await res
  if (!r.ok || !r.body) {
    const detail = await r.json().catch(() => null)
    // detail 可能是 FastAPI 422 的数组：直接塞 Error 会显示 [object Object]
    const msg = typeof detail?.detail === 'string' ? detail.detail : `请求失败（${r.status}）`
    throw new Error(msg)
  }
  return r
}

export function chatStream(
  sid: string, mode: string, message: string,
  handlers: {
    onDelta: (t: string) => void
    onDone: (meta: { expert: string; citations: Citation[]; assistant_message_id?: string; user_message_id?: string }) => void
    onError?: (msg: string) => void
    onAbort?: () => void
  },
  opts: { guide?: boolean; signal?: AbortSignal } = {},
) {
  const { onDelta, onDone, onError, onAbort } = handlers
  // 失败必须回调 onError 并结束 busy：此前 fetch 无 catch、不查 r.ok、也不认 error 事件，
  // 模型不可用/断流时发送按钮永久禁用且无任何提示
  sseResponse(fetch(`${BASE}/api/spaces/${sid}/chat/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, message, guide: opts.guide || false }),
    signal: opts.signal,
  })).then((r) => consumeSSE(r, (evt) => {
    if (evt.type === 'delta') onDelta(evt.text)
    if (evt.type === 'done') {
      onDone({
        expert: evt.expert, citations: evt.citations,
        assistant_message_id: evt.assistant_message_id,
        user_message_id: evt.user_message_id,
      })
      return 'done'
    }
    if (evt.type === 'error') throw new Error(evt.message || '生成回答失败')
  })).catch((e: any) => {
    // 用户主动停止不算错误：保留已生成的部分内容，由 onAbort 收尾
    if (e?.name === 'AbortError') { onAbort?.(); return }
    onError?.(e?.message || '网络错误：无法连接服务')
  })
}

// SSE 版技能执行：onPhase 收到「正在检索讲义/生成/入库」等阶段进度；
// onDone 收到与同步版 runSkill 相同的返回值。长任务期间服务端以 SSE 心跳保活。
// 中止（AbortError）会回调 onAbort：调用方必须借此复位 busy，否则界面永久卡在生成中
export function runSkillStream(
  sid: string, skill: string, params: object,
  handlers: { onPhase?: (label: string) => void; onDone: (result: any) => void; onError?: (msg: string) => void; onAbort?: () => void },
  signal?: AbortSignal,
) {
  sseResponse(fetch(`${BASE}/api/spaces/${sid}/skills/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill, params }), signal,
  })).then((r) => consumeSSE(r, (evt) => {
    if (evt.type === 'phase') handlers.onPhase?.(evt.label)
    if (evt.type === 'done') { handlers.onDone(evt.result); return 'done' }
    if (evt.type === 'error') throw new Error(evt.message || '技能执行失败')
  })).catch((e: any) => {
    if (e?.name === 'AbortError') { handlers.onAbort?.(); return }
    handlers.onError?.(e?.message || '网络错误：无法连接服务')
  })
}
