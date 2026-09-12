// 学涯中心：合并原「学涯规划」与「成长手册」两页。
// 档案只在「个人中心」维护一次——这里展示只读摘要，不再重复整张表单。
// 子页签：学籍与方案 / 课程表 / 成绩审核 / 学涯计划 / 成长手册
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, AuditResult, CareerPlan, CompetitionAnalysis, CompetitionItem, CompetitionPick, CourseEntry, Handbook, HandbookMeta, Program, ScheduleData, Space, StudentProfile, SyllabusFulltext, SyllabusMajors, SyllabusOfficial, SyllabusSchool, SyllabusStats, TakenCourse } from '../api'
import { downloadMd, Icon, SubTabs } from '../ui'
import { Md } from '../md'
import { useUX } from '../ux'

const DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const GOALS = ['保研', '考研', '就业', '竞赛', '出国', '期末', '毕业']
// 个人档案页的目标词表（"推免/保研"等）映射到规划页词表，避免同一档案在两页显示不一致
const goalAlias = (g: string) => {
  if (GOALS.includes(g)) return g
  if (/推免|保研/.test(g)) return '保研'
  return '考研'
}
const HORIZONS = ['本学期', '本学年', '至毕业']
const PERIOD_ORDER = ['1-2', '3-4', '5-6', '7-8', '9-10', '11-12']

function periodKey(p: string): number {
  const n = parseInt((p || '').split('-')[0])
  return isNaN(n) ? 99 : n
}

function periodLabel(p: string): string {
  return p ? `第${p}节` : '未排时段'
}

export function CareerView({ spaces, currentSid, onGoto }: {
  spaces: Space[]; currentSid: string; onGoto: (t: string) => void
}) {
  const { toast, confirm: uxConfirm, select: uxSelect } = useUX()
  const [sub, setSub] = useState('program')

  // 学籍（个人档案只读来源 + 查找用输入）
  const [profile, setProfile] = useState<StudentProfile | null>(null)
  const [profileErr, setProfileErr] = useState('')  // 加载失败 ≠ 「正在读取」：否则成长手册/竞赛页永远转圈
  const [school, setSchool] = useState('')
  const [major, setMajor] = useState('')
  const [year, setYear] = useState('')
  const [schools, setSchools] = useState<SyllabusSchool[]>([])
  const [majorsInfo, setMajorsInfo] = useState<SyllabusMajors | null>(null)
  const [program, setProgram] = useState<Program | null>(null)
  const [fulltext, setFulltext] = useState<SyllabusFulltext | null>(null)
  const [stats, setStats] = useState<SyllabusStats | null>(null)
  const [official, setOfficial] = useState<SyllabusOfficial[]>([])

  // 课程表
  const [schedule, setSchedule] = useState<ScheduleData | null>(null)
  const [draft, setDraft] = useState<CourseEntry[]>([])
  const [draftDirty, setDraftDirty] = useState(false)  // 草稿已改未保存：被覆盖前必须确认
  const [pasteText, setPasteText] = useState('')
  const [msg, setMsg] = useState('')

  // 已修课程 · 完成度审核
  const [taken, setTaken] = useState<TakenCourse[]>([])
  const [auditRes, setAuditRes] = useState<AuditResult | null>(null)
  const [newCourse, setNewCourse] = useState({ name: '', credit: '', grade: '', semester: '', status: 'done' })
  const [transcriptText, setTranscriptText] = useState('')

  // 目标计划
  const [goalType, setGoalType] = useState('考研')
  const [target, setTarget] = useState('')
  const [horizon, setHorizon] = useState('本学期')
  const [plans, setPlans] = useState<CareerPlan[]>([])
  const [openPlan, setOpenPlan] = useState('')

  const [busy, setBusy] = useState('')
  // 培养手册文本导入：window.prompt 是单行输入框，多行手册文本放不进来，改用页内弹层
  const [hbPasteOpen, setHbPasteOpen] = useState(false)
  const [hbPasteText, setHbPasteText] = useState('')

  // 成长手册
  const [handbooks, setHandbooks] = useState<HandbookMeta[]>([])
  const [currentHb, setCurrentHb] = useState<Handbook | null>(null)

  useEffect(() => {
    api.profile().then((p) => {
      setProfile(p)
      setSchool(p.current_school || '')
      setMajor(p.major || '')
      setYear(p.year || '')
      setGoalType(goalAlias(p.goal_type))
      setTarget([p.target_school, p.target_major].filter(Boolean).join(' '))
      setProfileErr('')
    }).catch((e: any) => setProfileErr(e?.message || '网络错误'))
    api.syllabusStats().then(setStats).catch(() => {})
    api.officialSources().then(setOfficial).catch(() => {})
    api.schools().then(setSchools).catch(() => {})
    // 首次加载失败也走兜底骨架：schedule 为 null 时学期名输入框永远无法输入，整个页签死锁
    api.schedule().then((s) => { setSchedule(s); setDraft(s.courses); setDraftDirty(false) }).catch(() => {
      setSchedule({ term: '', terms: [], courses: [] })
      setDraft([])
    })
    api.auditCourses().then((r) => setTaken(r.courses)).catch(() => {})
    api.handbooks().then(setHandbooks).catch(() => {})
    loadPlans()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 请求序号守卫：防抖只是减少请求，慢的旧响应仍可能晚到覆盖新结果
  const majorSeq = useRef(0)
  const progSeq = useRef(0)
  useEffect(() => {
    // 300ms 防抖：学校/专业每击键一个请求会造成响应竞态
    if (!school) { setMajorsInfo(null); return }
    const t = setTimeout(() => {
      const id = ++majorSeq.current
      api.majorsForSchool(school).then((m) => {
        if (id === majorSeq.current) setMajorsInfo(m)
      }).catch(() => { if (id === majorSeq.current) setMajorsInfo(null) })
    }, 300)
    return () => clearTimeout(t)
  }, [school])

  useEffect(() => {
    if (school && major) {
      const t = setTimeout(() => {
        const id = ++progSeq.current
        api.program(school, major).then((p) => {
          if (id !== progSeq.current) return
          setProgram(p); setFulltext(null)
        }).catch(() => { if (id === progSeq.current) setProgram(null) })
      }, 300)
      return () => clearTimeout(t)
    } else { setProgram(null); setFulltext(null) }
  }, [school, major])

  const flash = (text: string) => {
    // 常驻提示：解析结果的关键引导（「检查无误后点保存」）不该 2.5 秒后消失；
    // 下一次操作会覆盖，或点 ✕ 手动关闭
    setMsg(text)
  }

  const loadFulltext = async () => {
    if (fulltext) { setFulltext(null); return }
    try { setFulltext(await api.syllabusFulltext(school, major)) } catch (e: any) { toast('error', e.message) }
  }

  const methodLabel = (m: string) => (m === 'llm' ? '智能解析' : m === 'rule' ? '规则解析' : m)

  const saveMySchool = async () => {
    if (!profile) {
      // 档案未加载成功时静默 no-op 会让人以为已保存；必须给明确反馈
      toast('error', '个人档案尚未加载成功，无法写入。请刷新页面重试。')
      return
    }
    try {
      const p = await api.saveProfile({ ...profile, current_school: school, major, year })
      setProfile(p)
      flash('✓ 已写入个人档案')
    } catch (e: any) { toast('error', '保存档案失败：' + (e.message || '未知错误')) }
  }

  // ---------- 课程表操作 ----------
  const reloadSchedule = async (term?: string) => {
    if (draftDirty) {
      const go = await uxConfirm({ title: '覆盖未保存的修改', message: '课程表有修改尚未保存，继续将丢失这些修改。', confirmText: '继续' })
      if (!go) return
    }
    api.schedule(term).then((s) => { setSchedule(s); setDraft(s.courses); setDraftDirty(false) }).catch(() => {
      // 读取失败也要给出可编辑的骨架：schedule 为 null 时学期名输入框永远无法输入
      // （onChange 直接丢弃），而导入/保存又都要求先填学期名 → 整个页签死锁
      setSchedule((s) => s || { term: '', terms: [], courses: [] })
      setDraft([])
    })
  }

  const importText = async () => {
    if (!schedule?.term) { toast('warn', '请先填写学期名（如 2025-2026-1 或 大三上）'); return }
    if (draftDirty) {
      const go = await uxConfirm({ title: '覆盖未保存的修改', message: '课程表有修改尚未保存，重新解析将覆盖这些修改。', confirmText: '重新解析' })
      if (!go) return
    }
    setBusy('schedule')
    try {
      const r = await api.importScheduleText(pasteText)
      setDraft(r.courses); setDraftDirty(false)
      flash(`解析出 ${r.courses.length} 门课（${methodLabel(r.method)}），检查无误后点「保存课程表」`)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const importFile = async (f: File) => {
    if (!schedule?.term) { toast('warn', '请先填写学期名（如 2025-2026-1 或 大三上）'); return }
    if (draftDirty) {
      const go = await uxConfirm({ title: '覆盖未保存的修改', message: '课程表有修改尚未保存，重新解析将覆盖这些修改。', confirmText: '重新解析' })
      if (!go) return
    }
    setBusy('schedule')
    try {
      const r = await api.importScheduleFile(f)
      setDraft(r.courses); setDraftDirty(false)
      flash(`解析出 ${r.courses.length} 门课（${methodLabel(r.method)}），检查无误后点「保存课程表」`)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const saveSchedule = async () => {
    if (!schedule?.term) { toast('warn', '请先填写学期名'); return }
    setBusy('schedule')
    try {
      const r = await api.saveSchedule(schedule.term, draft)
      setDraft(r.courses); setDraftDirty(false)
      await reloadSchedule(schedule.term)
      flash(`✓ 已保存 ${r.saved} 门课`)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const setDraftAt = (i: number, patch: Partial<CourseEntry>) => {
    setDraftDirty(true)
    setDraft((d) => d.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  }

  // 周视图网格数据
  const weekGrid = useMemo(() => {
    const periods = Array.from(new Set([...PERIOD_ORDER, ...draft.map((c) => c.period)]))
      .filter(Boolean).sort((a, b) => periodKey(a) - periodKey(b))
    const grid: Record<string, CourseEntry[]> = {}
    for (const c of draft) {
      const key = `${c.day}-${c.period || 'x'}`
      ;(grid[key] = grid[key] || []).push(c)
    }
    return { periods, grid }
  }, [draft])

  // ---------- 培养方案导入 ----------
  const importHandbookFile = async (f: File) => {
    setBusy('syllabus')
    try {
      const r = await api.importSyllabusFile(school, major, f)
      const p = await api.program(r.school, r.major)
      setProgram(p)
      flash(`✓ 培养方案已导入并校准（抽取到 ${r.fields_found.length} 类字段）`)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const importHandbookText = async () => {
    const text = hbPasteText.trim()
    if (!text) { toast('warn', '请先粘贴培养手册/培养方案文本'); return }
    setBusy('syllabus')
    try {
      const r = await api.importSyllabusText(school, major, text)
      const p = await api.program(r.school, r.major)
      setProgram(p)
      flash(`✓ 培养方案已导入并校准（抽取到 ${r.fields_found.length} 类字段）`)
      setHbPasteOpen(false); setHbPasteText('')
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  // ---------- 已修课程 · 完成度审核 ----------
  const loadTaken = () => api.auditCourses().then((r) => setTaken(r.courses)).catch(() => {})

  const refreshAudit = async (silent = false) => {
    try {
      setAuditRes(await api.runAudit(school, major))
    } catch (e: any) {
      // 自动重算（加课/导入后）失败保持静默；用户点「审核」按钮必须有反馈，否则按钮像坏的
      if (!silent) toast('error', '审核失败：' + (e.message || '未知错误'))
    }
  }

  const addCourse = async () => {
    if (!newCourse.name.trim()) { toast('warn', '请填写课程名'); return }
    // 学分误输非数字静默存 0 会让学分进度/GPA 失真：非法输入必须当场拦下
    if (newCourse.credit.trim() && (isNaN(Number(newCourse.credit)) || Number(newCourse.credit) <= 0)) {
      toast('warn', `学分应为正数，当前输入「${newCourse.credit}」无效`)
      return
    }
    setBusy('course')
    try {
      await api.addAuditCourse({ name: newCourse.name.trim(), credit: parseFloat(newCourse.credit) || 0,
        grade: newCourse.grade.trim(), semester: newCourse.semester.trim(), status: newCourse.status })
      setNewCourse({ name: '', credit: '', grade: '', semester: '', status: 'done' })
      await loadTaken()
      await refreshAudit(true)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const importTranscript = async () => {
    setBusy('transcript')
    try {
      const r = await api.importAuditCourses(transcriptText)
      setTranscriptText('')
      await loadTaken()
      await refreshAudit(true)
      toast('success', `已导入 ${r.added} 门课程（${r.method === 'llm' ? '智能解析' : '规则解析'}）`)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const removeCourse = async (cid: string) => {
    // 单门成绩记录单击即删且触发重算，与「清空」的保护强度倒挂了：补上确认
    const c = taken.find((t) => t.id === cid)
    if (!(await uxConfirm({ title: '删除已修课程',
      message: `删除「${c?.name || '该课程'}」的成绩记录？审核结果会随之重算。`,
      confirmText: '删除', danger: true }))) return
    try { await api.deleteAuditCourse(cid); await loadTaken(); await refreshAudit(true) } catch (e: any) { toast('error', e.message) }
  }

  const clearCourses = async () => {
    if (!(await uxConfirm({ title: '清空已修课程', message: `清空全部 ${taken.length} 门已修课程？`, confirmText: '清空', danger: true }))) return
    try {
      const r = await api.clearAuditCourses()
      await loadTaken(); setAuditRes(null)
      toast('success', `已清空 ${r.removed} 门`)
    } catch (e: any) { toast('error', e.message) }
  }

  // ---------- 目标计划 ----------
  const loadPlans = () =>
    api.careerPlans().then(async (metas) => {
      // allSettled：单份计划损坏/404 不应把整个计划列表静默清空
      const results = await Promise.allSettled(metas.map((m) => api.careerPlan(m.id)))
      setPlans(results.filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled').map((r) => r.value))
    }).catch(() => {})

  const genAbort = useRef<AbortController | null>(null)
  const generate = async () => {
    setBusy('plan')
    const ctrl = new AbortController()
    genAbort.current = ctrl
    try {
      const p = await fetchWithSignal(ctrl.signal)
      await loadPlans()
      setOpenPlan(p.id)
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        // 服务端通常仍会生成完毕：提示稍后回来查看，而不是让用户以为计划丢了
        toast('info', '已停止等待。计划可能仍在后台生成，稍后重新进入本页可见')
        loadPlans()
      } else toast('error', e.message)
    }
    genAbort.current = null
    setBusy('')
  }
  const fetchWithSignal = (signal: AbortSignal) =>
    api.generateCareerPlan({ school, major, year, goal_type: goalType, target, term: schedule?.term || '', horizon }, signal)

  const toggleTask = async (pid: string, taskId: string, done: boolean) => {
    try {
      await api.toggleCareerTask(pid, taskId, done)
      const full = await api.careerPlan(pid)
      setPlans((ps) => ps.map((p) => (p.id === pid ? full : p)))
    } catch (e: any) { toast('error', '打卡失败：' + (e.message || '未知错误')) }
  }

  const pushPlan = async (pid: string) => {
    if (!spaces.length) { toast('warn', '还没有课程空间：先在左侧新建一个'); return }
    const sid = await uxSelect({ title: '同步到哪个课程空间？', options: spaces.map((s) => ({ value: s.id, label: s.name })) })
    if (!sid) return
    try {
      const r = await api.pushCareerPlan(pid, sid)
      const spaceName = spaces.find((s) => s.id === sid)?.name || ''
      toast('success', `已同步 ${r.synced} 条任务到「${spaceName}」的学习计划`)
      onGoto('today')
    } catch (e: any) { toast('error', e.message) }
  }

  const removePlan = async (pid: string) => {
    if (!(await uxConfirm({ title: '删除计划', message: '已同步到课程空间的任务会一并移除。', confirmText: '删除', danger: true }))) return
    try {
      const r: any = await api.deleteCareerPlan(pid)
      setPlans((ps) => ps.filter((p) => p.id !== pid))
      if (r?.removed_pushed_tasks) toast('success', `已删除计划，并移除 ${r.removed_pushed_tasks} 条关联任务`)
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  const planTotal = plans.reduce((a, p) => a + p.tasks.filter((t) => !t.done).length, 0)

  // ---------- 成长手册 ----------
  const generateHandbook = async () => {
    if (!profile) return
    if (!profile.target_school) { toast('warn', '还没有目标院校——先到「个人中心」的档案里填写'); return }
    setBusy('handbook')
    try {
      const h = await api.generateHandbook({ ...profile, space_id: currentSid || '' })
      setCurrentHb(h)
      api.handbooks().then(setHandbooks).catch(() => {})
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const openHandbook = async (id: string) => {
    try { setCurrentHb(await api.handbook(id)) } catch (e: any) { toast('error', '打开失败：' + (e.message || '未知错误')) }
  }
  const removeHandbook = async (id: string) => {
    if (!(await uxConfirm({ title: '删除手册', message: '此操作不可恢复。', confirmText: '删除', danger: true }))) return
    try {
      await api.deleteHandbook(id)
      if (currentHb?.id === id) setCurrentHb(null)
      api.handbooks().then(setHandbooks).catch(() => {})
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  return (
    <div className="content">
      <SubTabs value={sub} onChange={setSub} tabs={[
        ['program', '① 学籍与培养方案'], ['schedule', '② 课程表'], ['audit', '③ 成绩审核'],
        ['plan', `④ 学涯计划${planTotal ? `（${planTotal} 待办）` : ''}`], ['handbook', '⑤ 成长手册'],
        ['compete', '⑥ 竞赛规划'],
      ]} />

      {/* ① 学籍与培养方案 */}
      {sub === 'program' && (
        <>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>我的学校与专业</h3>
            <p className="sub">收录全国 985/211 高校（可搜简称如「示例大学」「华科」）；专业覆盖 21 个主流培养方案框架，未覆盖的专业可导入本校培养手册校准。档案在学校/专业/年级变动后可一键写回「个人中心」。</p>
            {stats && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                <span className="badge">985/211 院校 {stats.schools} 所（985 {stats.schools_985}）</span>
                <span className="badge">培养方案 {stats.programs} 套</span>
                <span className="badge">官方政策层 {stats.official} 份</span>
                <span className="badge">本校导入 {stats.custom} 份</span>
              </div>
            )}
            {official.length > 0 && (
              <details style={{ marginTop: 8 }}>
                <summary className="sub" style={{ cursor: 'pointer' }}>
                  已收录官方政策层的学校专业（{official.length} 项，点击展开看来源）
                </summary>
                <div style={{ display: 'grid', gap: 4, marginTop: 6, marginBottom: 6 }}>
                  {official.map((o) => (
                    <span key={`${o.school}-${o.major}`} className="sub">
                      <b>{o.school}</b> · {o.major} · {o.source_version}
                      {o.source_url && (
                        <a href={o.source_url} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>原文 ↗</a>
                      )}
                    </span>
                  ))}
                </div>
              </details>
            )}
            {profileErr ? (
              <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span className="sub" style={{ color: 'var(--red)' }}>⚠ 个人档案加载失败：{profileErr}（成长手册与竞赛规划依赖档案）</span>
                <button className="btn small" onClick={() => {
                  setProfileErr('')
                  api.profile().then((p) => {
                    setProfile(p); setSchool(p.current_school || ''); setMajor(p.major || '')
                    setYear(p.year || ''); setGoalType(goalAlias(p.goal_type))
                    setTarget([p.target_school, p.target_major].filter(Boolean).join(' '))
                  }).catch((e: any) => setProfileErr(e?.message || '网络错误'))
                }}>重试</button>
              </div>
            ) : null}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
              <div>
                <input type="text" list="sp-schools" placeholder="选择/输入学校（如 示例大学、华科）"
                  value={school} onChange={(e) => setSchool(e.target.value)} />
                <datalist id="sp-schools">
                  {schools.map((s) => <option key={s.name} value={s.name}>{`${s.tier} · ${s.region} · ${s.strong.slice(0, 2).join('/')}`}</option>)}
                </datalist>
              </div>
              <div>
                <input type="text" list="sp-majors" placeholder="选择/输入专业（如 计算机科学与技术）"
                  value={major} onChange={(e) => setMajor(e.target.value)} disabled={!school} />
                <datalist id="sp-majors">
                  {[...(majorsInfo?.official_majors || []), ...(majorsInfo?.custom_majors || []),
                    ...(majorsInfo?.template_majors || []), ...(majorsInfo?.strong || [])]
                    .map((m) => <option key={m} value={m} />)}
                </datalist>
              </div>
              <input type="text" placeholder="当前年级（如 大三上）" value={year}
                onChange={(e) => setYear(e.target.value)} />
              <button className="btn ghost" onClick={saveMySchool} disabled={!!profileErr}
                title={profileErr ? '档案未加载成功，无法写入' : undefined}>写入个人档案</button>
            </div>
            {majorsInfo && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                {majorsInfo.tier && <span className="badge">{majorsInfo.tier} 院校</span>}
                {majorsInfo.official_majors.length > 0 &&
                  <span className="badge" style={{ borderColor: 'var(--green)', color: 'var(--green)' }}>
                    官方方案层已收录：{majorsInfo.official_majors.join('、')}（全文可按来源 URL 获取）</span>}
                {majorsInfo.custom_majors.length > 0 &&
                  <span className="badge" style={{ borderColor: 'var(--green)', color: 'var(--green)' }}>
                    已导入本校方案 {majorsInfo.custom_majors.length} 个</span>}
                {majorsInfo.strong.slice(0, 5).map((s) => (
                  <span key={s} className="badge" style={{ cursor: 'pointer' }} onClick={() => setMajor(s)}>{s}</span>
                ))}
              </div>
            )}
          </div>

          {program && (
            <div className="card">
              <h3>培养方案{program.major ? ` · ${program.major}` : ''}
                {program.school_tier && <span className="badge" style={{ marginLeft: 8 }}>{program.school_tier}</span>}
              </h3>
              {program.coverage === 'none' ? (
                <p className="sub">{program.note}</p>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 4px' }}>
                    {program.coverage.includes('official')
                      ? <span className="badge" style={{ borderColor: 'var(--green)', color: 'var(--green)' }}>✓ 官方培养方案{program.source_version ? `（${program.source_version}）` : ''}</span>
                      : null}
                    {program.coverage.includes('custom') && <span className="badge" style={{ borderColor: 'var(--green)', color: 'var(--green)' }}>本校导入</span>}
                    {program.coverage === 'template' && <span className="badge">通用框架</span>}
                    {program.degree && <span className="badge">{program.degree}</span>}
                    {program.category && <span className="badge">{program.category}</span>}
                    {program.custom_source && <span className="badge">导入来源：{program.custom_source}</span>}
                  </div>
                  {program.coverage === 'template' && program.source_note && (
                    <p className="sub" style={{ margin: '4px 0 10px' }}>{program.source_note}</p>
                  )}
                  {program.training_goal && <p style={{ margin: '8px 0' }}><b>培养目标：</b>{program.training_goal}</p>}
                  {program.credits_reference && Object.keys(program.credits_reference).length > 0 && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0' }}>
                      {Object.entries(program.credits_reference).map(([k, v]) => (
                        <span key={k} className="badge">{k} <b>{v}</b> 学分</span>
                      ))}
                    </div>
                  )}
                  {program.core_courses && program.core_courses.length > 0 && (
                    <>
                      <b>专业核心课（{program.core_courses.length} 门）</b>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '8px 0 12px' }}>
                        {program.core_courses.map((c) => <span key={c} className="badge">{c}</span>)}
                      </div>
                    </>
                  )}
                  {program.course_groups && program.course_groups.length > 0 && (
                    <table className="quiz" style={{ marginBottom: 12 }}>
                      <thead><tr><th style={{ width: 260 }}>课程组（官方口径）</th><th>课程与学分</th></tr></thead>
                      <tbody>
                        {program.course_groups.map((g) => (
                          <tr key={g.group}>
                            <td><b>{g.group}</b></td>
                            <td>{g.courses.map((c) => `${c.name}（${c.credit}学分）`).join('、')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {program.semester_plan && program.semester_plan.length > 0 && (
                    <table className="quiz" style={{ marginBottom: 12 }}>
                      <thead><tr><th style={{ width: 90 }}>学期</th><th>关键课程</th><th>阶段要点</th></tr></thead>
                      <tbody>
                        {program.semester_plan.map((s) => (
                          <tr key={s.term}>
                            <td><b>{s.term}</b></td>
                            <td>{(s.key_courses || []).join('、')}</td>
                            <td className="sub">{s.milestone}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {program.grad_requirements && (
                    <p className="sub" style={{ margin: '4px 0', whiteSpace: 'pre-wrap' }}><b>毕业要求：</b>{program.grad_requirements}</p>
                  )}
                  {program.featured_courses && (
                    <p className="sub" style={{ margin: '4px 0' }}><b>特色课程：</b>{program.featured_courses}</p>
                  )}
                  {program.exam_notes && (
                    <p className="sub" style={{ margin: '4px 0', whiteSpace: 'pre-wrap' }}><b>要点：</b>{program.exam_notes}</p>
                  )}
                  {program.course_structure_note && (
                    <p className="sub" style={{ margin: '4px 0', whiteSpace: 'pre-wrap' }}><b>课程结构（官方说明）：</b>{program.course_structure_note}</p>
                  )}
                  {program.paths && (
                    <details>
                      <summary style={{ cursor: 'pointer' }}><b>升学 / 就业路径参考</b></summary>
                      <div className="md" style={{ marginTop: 8 }}>
                        <PathList paths={program.paths} />
                      </div>
                    </details>
                  )}
                  {(program.has_fulltext || program.source_url) && (
                    <div style={{ marginTop: 12, padding: '10px 12px', border: '1px solid var(--hairline)', borderRadius: 10, background: 'rgba(99,140,255,.05)' }}>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <b className="sub">官方来源：</b>
                        {program.source_url && (
                          <a href={program.source_url} target="_blank" rel="noreferrer" className="sub" style={{ color: 'var(--accent, #7aa2ff)' }}>
                            {program.source_url}
                          </a>
                        )}
                        {program.has_fulltext && (
                          <button className="btn ghost small" onClick={loadFulltext}>
                            {fulltext ? '收起全文' : '查看官方培养方案全文'}
                          </button>
                        )}
                      </div>
                      {fulltext && (
                        <pre className="sub" style={{
                          whiteSpace: 'pre-wrap', maxHeight: 420, overflowY: 'auto', marginTop: 8,
                          padding: 12, borderRadius: 8, background: 'rgba(10,14,28,.5)', fontSize: 12.5, lineHeight: 1.65,
                        }}>{fulltext.text}</pre>
                      )}
                      {fulltext && fulltext.source_note && <p className="sub" style={{ marginTop: 6 }}>{fulltext.source_note}</p>}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    <button className="btn ghost small" disabled={busy === 'syllabus' || !school}
                      onClick={() => document.getElementById('syllabus-file')?.click()}>
                      {busy === 'syllabus' ? '解析中…' : '导入本校培养手册（PDF/截图）校准'}
                    </button>
                    <button className="btn ghost small" disabled={busy === 'syllabus' || !school}
                      onClick={() => setHbPasteOpen((o) => !o)}>
                      粘贴文本导入
                    </button>
                    <input id="syllabus-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.txt,.md" hidden
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) importHandbookFile(f); e.target.value = '' }} />
                  </div>
                  {hbPasteOpen && (
                    <div style={{ marginTop: 10 }}>
                      <textarea
                        placeholder="把本校培养手册/培养方案文本粘贴到这里（PDF 里全选复制即可，支持多行长文本）"
                        style={{ width: '100%', minHeight: 160 }}
                        value={hbPasteText}
                        onChange={(e) => setHbPasteText(e.target.value)} />
                      <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
                        <button className="btn small" disabled={busy === 'syllabus' || !hbPasteText.trim()} onClick={importHandbookText}>
                          {busy === 'syllabus' ? '抽取中…' : '开始抽取导入'}
                        </button>
                        <button className="btn ghost small" onClick={() => { setHbPasteOpen(false); setHbPasteText('') }}>取消</button>
                        <span className="sub">文本需至少 80 字，系统只抽取手册中明确出现的信息</span>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* ② 课程表 */}
      {sub === 'schedule' && (
        <div className="card">
          <h3>本学期课程表</h3>
          <p className="sub">上传教务系统截图（离线 OCR）、Excel 导出或直接粘贴文本，自动解析成课表；解析结果可逐格修正。学涯计划生成会参考这份课表。</p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
            <input type="text" list="sp-terms" placeholder="学期名（如 2025-2026-1 / 大三上）" style={{ width: 240 }}
              value={schedule?.term || ''} onChange={(e) => setSchedule((s) => (s ? { ...s, term: e.target.value } : s))} />
            <datalist id="sp-terms">{(schedule?.terms || []).map((t) => <option key={t.term} value={t.term} />)}</datalist>
            <button className="btn ghost small" disabled={busy === 'schedule'}
              onClick={() => document.getElementById('schedule-file')?.click()}>上传截图 / Excel / CSV</button>
            <input id="schedule-file" type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,.xlsx,.csv,.json,.txt,.md" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); e.target.value = '' }} />
            {(schedule?.terms.length || 0) > 0 && (
              <select value="" onChange={(e) => e.target.value && reloadSchedule(e.target.value)}>
                <option value="">切换已有学期…</option>
                {schedule!.terms.map((t) => <option key={t.term} value={t.term}>{t.term}（{t.courses} 门）</option>)}
              </select>
            )}
            {schedule && schedule.term && (
              <button className="btn danger ghost small" onClick={async () => {
                if (!(await uxConfirm({ title: '清空课程表', message: `清空「${schedule.term}」的课程表？`, confirmText: '清空', danger: true }))) return
                try {
                  await api.deleteSchedule(schedule.term); await reloadSchedule(schedule.term)
                } catch (e: any) { toast('error', '清空失败：' + (e.message || '未知错误')) }
              }}>清空本学期</button>
            )}
          </div>
          <textarea placeholder="或把课程表文本粘贴到这里（每行一门课，含 周X / 第X节 / 教室 更准）"
            style={{ width: '100%', marginTop: 10, minHeight: 64 }}
            value={pasteText} onChange={(e) => setPasteText(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="btn ghost small" disabled={busy === 'schedule' || !pasteText.trim()} onClick={importText}>
              {busy === 'schedule' ? '解析中…' : '解析粘贴文本'}
            </button>
            <button className="btn small" disabled={busy === 'schedule' || !draft.length} onClick={saveSchedule}>保存课程表</button>
            {msg && (
              <span className="sub" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                {msg}
                <button className="btn ghost small" style={{ padding: '0 6px' }} aria-label="关闭提示"
                  onClick={() => setMsg('')}>✕</button>
              </span>
            )}
          </div>

          {draft.length > 0 && (
            <>
              {/* 周视图 */}
              <div style={{ overflowX: 'auto', marginTop: 14 }}>
                <table className="quiz week-grid">
                  <thead><tr><th style={{ width: 70 }}></th>{DAYS.map((d) => <th key={d}>{d}</th>)}</tr></thead>
                  <tbody>
                    {weekGrid.periods.map((p) => (
                      <tr key={p}>
                        <td><b>{periodLabel(p)}</b></td>
                        {DAYS.map((_, di) => {
                          const cell = weekGrid.grid[`${di + 1}-${p}`] || []
                          return (
                            <td key={di}>
                              {cell.map((c) => (
                                <div key={c.course + c.weeks} className="week-cell">
                                  <b>{c.course}</b>
                                  <span>{[c.weeks, c.room].filter(Boolean).join(' · ')}</span>
                                </div>
                              ))}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* 编辑列表 */}
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: 'pointer' }} className="sub">逐条修正（{draft.length} 门）</summary>
                <table className="quiz" style={{ marginTop: 8 }}>
                  <thead><tr><th>课程</th><th>星期</th><th>节次</th><th>周次</th><th>教室</th><th>教师</th><th></th></tr></thead>
                  <tbody>
                    {draft.map((c, i) => (
                      <tr key={i}>
                        <td><input type="text" value={c.course} onChange={(e) => setDraftAt(i, { course: e.target.value })} /></td>
                        <td>
                          <select value={c.day} onChange={(e) => setDraftAt(i, { day: parseInt(e.target.value) })}>
                            <option value={0}>未定</option>
                            {DAYS.map((d, di) => <option key={d} value={di + 1}>{d}</option>)}
                          </select>
                        </td>
                        <td><input type="text" value={c.period} style={{ width: 70 }} onChange={(e) => setDraftAt(i, { period: e.target.value })} /></td>
                        <td><input type="text" value={c.weeks} style={{ width: 90 }} onChange={(e) => setDraftAt(i, { weeks: e.target.value })} /></td>
                        <td><input type="text" value={c.room} style={{ width: 100 }} onChange={(e) => setDraftAt(i, { room: e.target.value })} /></td>
                        <td><input type="text" value={c.teacher} style={{ width: 90 }} onChange={(e) => setDraftAt(i, { teacher: e.target.value })} /></td>
                        <td><button className="btn danger ghost small" onClick={() => { setDraftDirty(true); setDraft((d) => d.filter((_, j) => j !== i)) }}>✕</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </>
          )}
        </div>
      )}

      {/* ③ 成绩审核 */}
      {sub === 'audit' && (
        <div className="card">
          <h3>已修课程 · 完成度审核</h3>
          <p className="sub">录入已修/在修课程（支持粘贴成绩单文本批量导入），对照培养方案自动核对：
          核心课已修·在修·缺失三态、先修链违规、学分进度与 GPA——让「看方案」变成「查进度」。</p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10, alignItems: 'center' }}>
            <input type="text" placeholder="课程名（如 高等数学）" style={{ width: 200 }} value={newCourse.name}
              onChange={(e) => setNewCourse((c) => ({ ...c, name: e.target.value }))} />
            <input type="text" placeholder="学分" style={{ width: 70 }} value={newCourse.credit}
              onChange={(e) => setNewCourse((c) => ({ ...c, credit: e.target.value }))} />
            <input type="text" placeholder="成绩(92/优秀/A-)" style={{ width: 110 }} value={newCourse.grade}
              onChange={(e) => setNewCourse((c) => ({ ...c, grade: e.target.value }))} />
            <input type="text" placeholder="学期(大一上)" style={{ width: 100 }} value={newCourse.semester}
              onChange={(e) => setNewCourse((c) => ({ ...c, semester: e.target.value }))} />
            <select value={newCourse.status} onChange={(e) => setNewCourse((c) => ({ ...c, status: e.target.value }))}>
              <option value="done">已修</option>
              <option value="taking">修读中</option>
            </select>
            <button className="btn small" disabled={busy === 'course'} onClick={addCourse}>添加</button>
            <button className="btn small" disabled={busy === 'audit'} onClick={() => { setBusy('audit'); refreshAudit(false).finally(() => setBusy('')) }}>对照培养方案审核</button>
            {taken.length > 0 && (
              <button className="btn danger ghost small" onClick={clearCourses}>清空</button>
            )}
          </div>
          <textarea placeholder="或把成绩单文本粘贴到这里，每行一门课：课程名 学分 成绩 学期（如「高等数学 5 92 大一上」，也可只写「数据结构 88」）"
            style={{ width: '100%', marginTop: 10, minHeight: 56 }}
            value={transcriptText} onChange={(e) => setTranscriptText(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
            <button className="btn ghost small" disabled={busy === 'transcript' || !transcriptText.trim()} onClick={importTranscript}>
              {busy === 'transcript' ? '解析中…' : '批量导入成绩'}
            </button>
            {taken.length > 0 && <span className="badge">已录 {taken.length} 门</span>}
          </div>

          {taken.length > 0 && (
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: 'pointer' }} className="sub">已修课程清单（{taken.length} 门）</summary>
              <table className="quiz" style={{ marginTop: 8 }}>
                <thead><tr><th>课程</th><th>学分</th><th>成绩</th><th>绩点</th><th>学期</th><th>状态</th><th></th></tr></thead>
                <tbody>
                  {taken.map((t) => (
                    <tr key={t.id}>
                      <td>{t.name}</td>
                      <td>{t.credit || '—'}</td>
                      <td>{t.grade || '—'}</td>
                      <td>{t.gpa >= 0 ? t.gpa.toFixed(1) : '—'}</td>
                      <td>{t.semester || '—'}</td>
                      <td>{t.status === 'taking' ? '修读中' : '已修'}</td>
                      <td><button className="btn danger ghost small" onClick={() => removeCourse(t.id)}>✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}

          {auditRes && !auditRes.program_found && (
            <p className="sub" style={{ marginTop: 10 }}>{auditRes.note}</p>
          )}
          {auditRes && auditRes.program_found && (
            <div style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <span className="badge">已修 <b>{auditRes.requirements!.done}</b> / 在修 <b>{auditRes.requirements!.taking}</b> / 缺失 <b>{auditRes.requirements!.missing}</b>（共 {auditRes.requirements!.total} 门要求课程）</span>
                {auditRes.credits && auditRes.credits.total_required > 0 && (
                  <span className="badge">总学分 <b>{auditRes.credits.total_earned}</b> / {auditRes.credits.total_required}
                    {auditRes.credits.progress != null && `（${Math.round(auditRes.credits.progress * 100)}%）`}</span>
                )}
                {auditRes.gpa != null && <span className="badge">GPA <b>{auditRes.gpa}</b>（4.0 制）</span>}
              </div>
              {auditRes.credits && auditRes.credits.by_category.length > 0 && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                  {auditRes.credits.by_category.map((c) => (
                    <span key={c.category} className={`badge ${c.earned >= c.required ? '' : 'expert'}`}>
                      {c.category.split('（')[0]}：{c.earned}/{c.required} 学分
                    </span>
                  ))}
                </div>
              )}
              {auditRes.prereq_violations!.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <b style={{ color: 'var(--red)' }}>⚠ 先修链审核未通过</b>
                  {auditRes.prereq_violations!.map((v) => (
                    <p key={v.course} className="sub" style={{ margin: '4px 0 0' }}>
                      <b>{v.course}</b>：先修 {v.missing_prereqs.join('、')} 尚未修读
                    </p>
                  ))}
                </div>
              )}
              {auditRes.ready_next!.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <b>✓ 先修已齐、下学期可修（{auditRes.ready_next!.length} 门）</b>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                    {auditRes.ready_next!.map((c) => (
                      <span key={c.name} className="badge" style={{ borderColor: 'var(--green)', color: 'var(--green)' }}>
                        {c.name}{c.expected_term ? `（建议 ${c.expected_term}）` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: 'pointer' }} className="sub">要求课程三态明细（✅ 已修 / 🔵 修读中 / ❌ 缺失）</summary>
                <div style={{ display: 'grid', gap: 4, marginTop: 8 }}>
                  {auditRes.core_states!.map((c) => (
                    <span key={c.name} className="sub">
                      {c.state === 'done' ? '✅' : c.state === 'taking' ? '🔵' : '❌'} <b>{c.name}</b>
                      {c.grade && ` · ${c.grade}`}
                      {c.state === 'missing' && c.expected_term && ` · 建议 ${c.expected_term}`}
                      <span style={{ opacity: 0.6 }}> · {c.category}</span>
                    </span>
                  ))}
                </div>
              </details>
              {auditRes.unmatched && auditRes.unmatched.length > 0 && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer' }} className="sub">
                    未匹配到培养方案的已修课程（{auditRes.unmatched.length} 门，计入总学分但不影响核心课审核）
                  </summary>
                  <p className="sub" style={{ marginTop: 6 }}>{auditRes.unmatched.map((u) => u.name).join('、')}</p>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      {/* ④ 学涯计划 */}
      {sub === 'plan' && (
        <>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>目标导向学习计划</h3>
            <p className="sub">以你的目标为主线，结合培养方案先修链、本学期课表与各空间薄弱点，生成分阶段可打卡计划；可一键同步到课程空间的「学习计划」执行。</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, marginTop: 12 }}>
              <select value={goalType} onChange={(e) => setGoalType(e.target.value)}>
                {GOALS.map((g) => <option key={g} value={g}>目标：{g}</option>)}
              </select>
              <input type="text" placeholder="目标去向（如 华中科技大学 计算机技术 / 大厂后端岗）"
                value={target} onChange={(e) => setTarget(e.target.value)} disabled={busy === 'plan'} />
              <select value={horizon} onChange={(e) => setHorizon(e.target.value)} disabled={busy === 'plan'}>
                {HORIZONS.map((h) => <option key={h} value={h}>跨度：{h}</option>)}
              </select>
              <button className="btn" disabled={busy === 'plan'} onClick={generate}>
                {busy === 'plan' ? <><span className="spin" /> 生成中（约 1 分钟）</> : '生成学习计划'}
              </button>
              {busy === 'plan' && (
                <button className="btn ghost" onClick={() => genAbort.current?.abort()}>停止等待</button>
              )}
            </div>
            {/* 生成期间目标输入被禁用：避免「正在生成的是旧目标」的困惑 */}
            {busy === 'plan' && <p className="sub" style={{ marginTop: 8 }}>正在按「目标：{goalType}{target ? ` → ${target}` : ''}」生成，期间不能修改目标。</p>}
            {!school || !major ? (
              <p className="sub" style={{ marginTop: 8 }}>提示：先在「① 学籍与培养方案」选择学校与专业，计划会更贴合培养方案。</p>
            ) : schedule && !schedule.courses.length ? (
              <p className="sub" style={{ marginTop: 8 }}>提示：导入本学期课表后，计划会按在读课程分配精力。</p>
            ) : null}
          </div>

          {plans.length > 0 && (
            <div className="card">
              <h3>我的学涯计划 {planTotal > 0 && <span className="badge expert" style={{ marginLeft: 8 }}>{planTotal} 项待完成</span>}</h3>
              {plans.map((p) => {
                const total = p.tasks.length
                const done = p.tasks.filter((t) => t.done).length
                const expanded = openPlan === p.id
                const phases = Array.from(new Set(p.tasks.map((t) => t.phase)))
                return (
                  <div key={p.id} style={{ borderBottom: '1px solid var(--line)', padding: '12px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', cursor: 'pointer' }}
                      onClick={() => setOpenPlan(expanded ? '' : p.id)}>
                      <b>{p.title}</b>
                      <span className="badge">{p.goal_type}</span>
                      {p.target && <span className="sub">→ {p.target}</span>}
                      <div className="mastery-track" style={{ minWidth: 90 }}>
                        <div className={`mastery-fill ${done / (total || 1) < 0.35 ? 'weak' : done / (total || 1) < 0.75 ? 'learning' : 'mastered'}`}
                          style={{ width: `${total ? Math.round((done / total) * 100) : 0}%` }} />
                        <span className="mastery-label">{done}/{total}</span>
                      </div>
                      <div style={{ flex: 1 }} />
                      <span className="sub">{expanded ? '收起 ▲' : '展开 ▼'}</span>
                    </div>
                    {expanded && (
                      <>
                        {p.summary && <p className="sub" style={{ margin: '8px 0' }}>总方针：{p.summary}</p>}
                        {phases.map((ph) => (
                          <div key={ph} style={{ margin: '10px 0 4px' }}>
                            <b className="sub">{ph}</b>
                            {p.tasks.filter((t) => t.phase === ph).map((t) => (
                              <label key={t.id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '6px 0', cursor: 'pointer' }}>
                                <input type="checkbox" checked={t.done} onChange={(e) => toggleTask(p.id, t.id, e.target.checked)} />
                                <span>
                                  <span style={{ textDecoration: t.done ? 'line-through' : undefined, opacity: t.done ? 0.55 : 1 }}>{t.content}</span>
                                  {t.accept && <span className="sub">　验收：{t.accept}</span>}
                                  {t.course && <span className="badge" style={{ marginLeft: 6 }}>{t.course}</span>}
                                </span>
                              </label>
                            ))}
                          </div>
                        ))}
                        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                          <button className="btn ghost small" onClick={() => pushPlan(p.id)}>同步到课程空间</button>
                          <button className="btn ghost small" onClick={() => downloadMd('career-plan', p.markdown)}>导出 Markdown</button>
                          <button className="btn danger ghost small" onClick={() => removePlan(p.id)}>删除</button>
                        </div>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* ⑤ 成长手册：档案来自「个人中心」，这里不再重复表单 */}
      {sub === 'handbook' && (
        <>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>成长手册 · 升学战略引擎</h3>
            <p className="sub">
              基于真实院校政策（学籍/重修/推免/招生要求，每条结论标注官方来源）× 你的处境 × StudyPilot 掌握度数据，
              生成直达目标的分阶段行动手册。政策每年可能调整，关键节点以官方最新文件为准。
            </p>
            {profile ? (
              <>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 4px' }}>
                  <span className="badge">本科：{[profile.current_school, profile.major, profile.year].filter(Boolean).join(' · ') || '（未填写）'}</span>
                  <span className="badge">目标：{[profile.goal_type, profile.target_school, profile.target_major].filter(Boolean).join(' · ') || '（未填写）'}</span>
                  {profile.timeline && <span className="badge">时间线：{profile.timeline}</span>}
                  {profile.flags.map((f) => <span key={f} className="badge expert">{f}</span>)}
                </div>
                <p className="sub" style={{ marginTop: 6 }}>
                  以上来自「个人中心」的档案。要修改学校、专业、目标或补充经历，<a href="#" onClick={(e) => { e.preventDefault(); onGoto('profile') }} style={{ textDecoration: 'underline' }}>去个人中心修改</a>，生成手册时会自动带入。
                </p>
              </>
            ) : profileErr ? (
              <p className="sub" style={{ marginTop: 8, color: 'var(--red)' }}>
                ⚠ 个人档案加载失败：{profileErr}。
                <button className="btn ghost small" onClick={() => window.location.reload()} style={{ marginLeft: 6 }}>刷新重试</button>
                或到「个人中心」手动检查。
              </p>
            ) : (
              <p className="sub" style={{ marginTop: 8 }}><span className="spin" /> 正在读取个人档案…</p>
            )}
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
              <button className="btn" disabled={busy === 'handbook' || !profile} onClick={generateHandbook}>
                {busy === 'handbook'
                  ? <><span className="spin" /> 正在结合政策库生成…（约1分钟）</>
                  : <><Icon name="compass" size={14} /> 生成成长手册</>}
              </button>
              {currentSid && profile && (
                <span className="sub">将结合当前空间「{spaces.find((s) => s.id === currentSid)?.name}」的掌握度数据</span>
              )}
            </div>
          </div>

          {currentHb && (
            <div className="card" style={{ marginBottom: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0 }}>{currentHb.title}</h3>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn ghost small" onClick={() => downloadMd('成长手册', currentHb.content)}>
                    <Icon name="book" size={12} /> 导出 Markdown
                  </button>
                  <button className="btn ghost small" onClick={() => setCurrentHb(null)}>收起</button>
                </div>
              </div>
              <Md>{currentHb.content}</Md>
            </div>
          )}

          {handbooks.length > 0 && (
            <div className="card">
              <h3>历史手册</h3>
              <table className="quiz" style={{ marginTop: 10 }}>
                <tbody>
                  {handbooks.map((h) => (
                    <tr key={h.id}>
                      <td style={{ cursor: 'pointer' }} onClick={() => openHandbook(h.id)}><b>{h.title}</b></td>
                      <td style={{ width: 150, color: 'var(--muted)', fontSize: 12 }}>
                        {new Date(h.created_at * 1000).toLocaleDateString()}</td>
                      <td style={{ width: 60 }}>
                        <button className="btn danger small" onClick={() => removeHandbook(h.id)} aria-label={`删除手册《${h.title}》`}><Icon name="trash" size={12} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {/* ⑥ 竞赛规划：目标导向的竞赛推荐与分析 */}
      {sub === 'compete' && <CompeteTab profile={profile} profileErr={profileErr} onGoto={onGoto} />}
    </div>
  )
}

// ---------- ⑥ 竞赛规划 ----------

const COMPETE_GOALS = ['考研', '推免/保研', '就业', '出国']

function CompeteTab({ profile, profileErr, onGoto }: { profile: StudentProfile | null; profileErr: string; onGoto: (t: string) => void }) {
  const { toast } = useUX()
  const [goal, setGoal] = useState('考研')
  const [useLlm, setUseLlm] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<CompetitionAnalysis | null>(null)
  const [catalog, setCatalog] = useState<CompetitionItem[] | null>(null)
  const [catalogOpen, setCatalogOpen] = useState(false)

  useEffect(() => {
    if (profile) setGoal(goalAlias(profile.goal_type) === '保研' ? '推免/保研' : goalAlias(profile.goal_type) === '考研' ? '考研' : '就业')
  }, [profile])

  useEffect(() => {
    if (catalogOpen && !catalog) api.competitionCatalog().then((r) => setCatalog(r.items)).catch(() => setCatalog([]))
  }, [catalogOpen, catalog])

  const analyze = async () => {
    if (!profile) { toast('warn', '个人档案还在加载中，稍后再试'); return }
    setBusy(true)
    try {
      setResult(await api.competitionAnalyze({ goal, use_llm: useLlm, ...profile }))
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const tierBlock = (title: string, tone: 'ok' | 'mid' | 'bad', items: CompetitionPick[]) => {
    if (!items.length) return null
    const color = tone === 'ok' ? 'var(--green)' : tone === 'mid' ? 'var(--orange)' : 'var(--red)'
    return (
      <div style={{ marginTop: 14 }}>
        <b style={{ color, fontSize: 13.5 }}>{title}（{items.length}）</b>
        <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
          {items.map((p) => (
            <div key={p.id} style={{ border: '1px solid var(--hairline)', borderRadius: 12, padding: '10px 14px', fontSize: 13 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <b>{p.name}</b>
                <span className="badge">{p.tier}</span>
                {p.specialist && <span className="badge expert">专业对口</span>}
                <span className="sub">{p.team}</span>
              </div>
              <div className="sub" style={{ marginTop: 4 }}>
                赛期：{p.window_label}
                {p.suggested_date && `　·　建议参加 ${p.suggested_date} 那届`}
                　·　备赛约 {p.prep_weeks} 周
              </div>
              <p style={{ margin: '6px 0 0', color: 'var(--muted)', lineHeight: 1.6 }}>{p.why}</p>
              {p.note && <p style={{ margin: '4px 0 0', color: 'var(--orange)' }}>◎ {p.note}</p>}
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>竞赛规划 · 目标倒推分析</h3>
        <p className="sub">
          从目标反推「至少要参加哪几个竞赛」：按目标路径（考研复试 / 推免综测 / 求职简历 / 留学背景）
          给各竞赛的价值打分，结合专业对口度与时间可行性（赛期、出成绩周期 vs 你的截止日）分级推荐。
          赛期为常见惯例，报名与赛制以当年官方通知为准。
        </p>
        {profile ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 4px' }}>
            <span className="badge">本科：{[profile.current_school, profile.major, profile.year].filter(Boolean).join(' · ') || '（未填写）'}</span>
            <span className="badge">目标：{[profile.target_school, profile.target_major].filter(Boolean).join(' ') || '（未填写）'}</span>
            {profile.timeline && <span className="badge">时间线：{profile.timeline}</span>}
            <span className="sub">
              档案在 <a href="#" onClick={(e) => { e.preventDefault(); onGoto('profile') }} style={{ textDecoration: 'underline' }}>个人中心</a> 维护，分析自动带入
            </span>
          </div>
        ) : profileErr ? (
          <p className="sub" style={{ marginTop: 8, color: 'var(--red)' }}>⚠ 个人档案加载失败：{profileErr}——分析依赖档案中的时间线与目标，请刷新页面重试。</p>
        ) : (
          <p className="sub" style={{ marginTop: 8 }}><span className="spin" /> 正在读取个人档案…</p>
        )}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
          <select value={goal} onChange={(e) => setGoal(e.target.value)} style={{ maxWidth: 180 }}>
            {COMPETE_GOALS.map((g) => <option key={g} value={g}>目标路径：{g}</option>)}
          </select>
          <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center', cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
            追加 AI 备赛策略
          </label>
          <button className="btn" disabled={busy || !profile} onClick={analyze} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> 分析中{useLlm ? '（含模型策略）' : ''}…</> : <><Icon name="quiz" size={14} /> 分析该参加哪些竞赛</>}
          </button>
          <button className="btn ghost" onClick={() => setCatalogOpen((o) => !o)} style={{ flex: 'none' }}>
            {catalogOpen ? '收起完整目录' : `浏览完整目录${catalog ? `（${catalog.length} 项）` : ''}`}
          </button>
        </div>
      </div>

      {catalogOpen && (
        <div className="card" style={{ marginBottom: 18 }}>
          <h3>内置竞赛目录</h3>
          <p className="sub">各竞赛在四条目标路径下的价值评分（1-5，越高越值得），专业标注表示强对口方向。</p>
          {!catalog ? <p className="sub"><span className="spin" /> 加载中…</p> : (
            <table className="quiz" style={{ marginTop: 8 }}>
              <thead><tr><th>竞赛</th><th>级别</th><th>赛期</th><th>备赛</th><th>对口专业</th><th>考研</th><th>推免</th><th>就业</th><th>出国</th></tr></thead>
              <tbody>
                {catalog.map((c) => (
                  <tr key={c.id}>
                    <td><b>{c.name}</b><div className="sub">{c.team}</div></td>
                    <td><span className="badge">{c.tier}</span></td>
                    <td className="sub">{c.window_label}</td>
                    <td>{c.prep_weeks} 周</td>
                    <td className="sub">{c.majors.join('、')}</td>
                    {['考研', '推免', '就业', '出国'].map((g) => (
                      <td key={g}>
                        <b style={{ color: (c.goals[g] || 0) >= 4 ? 'var(--green)' : undefined }}>{c.goals[g] || '—'}</b>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {result && (
        <div className="card">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>分析结果 · {result.goal_label}</h3>
            {result.months_left != null && (
              <span className="badge expert">距截止约 {result.months_left} 个月</span>
            )}
            {result.deadline && <span className="badge">截止 {result.deadline}</span>}
          </div>
          <p className="sub" style={{ marginTop: 6 }}>
            {result.target ? `目标去向：${result.target}。` : ''}
            {result.deadline_source}。目标院校的具体加分/复试政策每年可能调整，以官方最新文件为准。
          </p>

          {tierBlock('至少参加 · 强烈推荐', 'ok', result.tier1)}
          {tierBlock('有余力 · 值得考虑', 'mid', result.tier2)}
          {tierBlock('谨慎投入 · 时间或回报不匹配', 'bad', result.tier3)}

          {result.strategy_md && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--hairline)', paddingTop: 12 }}>
              <h3>AI 备赛策略</h3>
              <Md>{result.strategy_md}</Md>
            </div>
          )}
          {result.strategy_error && (
            <p className="sub" style={{ marginTop: 10, color: 'var(--orange)' }}>◎ {result.strategy_error}</p>
          )}
        </div>
      )}
    </>
  )
}

function PathList({ paths }: { paths: Record<string, unknown> }) {
  return (
    <div>
      {Object.entries(paths).map(([k, v]) => (
        <div key={k} style={{ marginBottom: 8 }}>
          <b>{k}</b>
          <PathValue v={v} />
        </div>
      ))}
    </div>
  )
}

function PathValue({ v }: { v: unknown }) {
  if (typeof v === 'string') return <div className="sub" style={{ whiteSpace: 'pre-wrap' }}>{v}</div>
  if (Array.isArray(v)) return <div className="sub">{v.map((x, i) => <span key={i} className="badge" style={{ margin: 2 }}>{String(x)}</span>)}</div>
  if (v && typeof v === 'object') {
    return (
      <div style={{ paddingLeft: 12 }}>
        {Object.entries(v as Record<string, unknown>).map(([k2, v2]) => (
          <div key={k2}><span className="sub">{k2}：</span><PathValue v={v2} /></div>
        ))}
      </div>
    )
  }
  return <span className="sub">{String(v)}</span>
}
