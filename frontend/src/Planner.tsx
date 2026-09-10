// 学涯规划页：院校/专业选择 → 培养方案 → 本学期课表 → 目标导向学习计划
import { useEffect, useMemo, useState } from 'react'
import { api, CareerPlan, CourseEntry, Program, ScheduleData, Space, StudentProfile, SyllabusFulltext, SyllabusMajors, SyllabusOfficial, SyllabusSchool, SyllabusStats } from './api'
import { downloadMd } from './ui'

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

export function PlannerView({ spaces, onOpenSpace }: { spaces: Space[]; onOpenSpace: (id: string) => void }) {
  // 我的学籍
  const [profile, setProfile] = useState<StudentProfile | null>(null)
  const [school, setSchool] = useState('')
  const [major, setMajor] = useState('')
  const [schools, setSchools] = useState<SyllabusSchool[]>([])
  const [majorsInfo, setMajorsInfo] = useState<SyllabusMajors | null>(null)
  const [program, setProgram] = useState<Program | null>(null)
  const [fulltext, setFulltext] = useState<SyllabusFulltext | null>(null)
  const [stats, setStats] = useState<SyllabusStats | null>(null)
  const [official, setOfficial] = useState<SyllabusOfficial[]>([])

  // 课程表
  const [schedule, setSchedule] = useState<ScheduleData | null>(null)
  const [draft, setDraft] = useState<CourseEntry[]>([])
  const [pasteText, setPasteText] = useState('')
  const [scheduleMsg, setScheduleMsg] = useState('')

  // 目标计划
  const [goalType, setGoalType] = useState('考研')
  const [target, setTarget] = useState('')
  const [horizon, setHorizon] = useState('本学期')
  const [year, setYear] = useState('')
  const [plans, setPlans] = useState<CareerPlan[]>([])
  const [openPlan, setOpenPlan] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  // 培养手册文本导入：window.prompt 是单行输入框，多行手册文本放不进来，改用页内弹层
  const [hbPasteOpen, setHbPasteOpen] = useState(false)
  const [hbPasteText, setHbPasteText] = useState('')

  useEffect(() => {
    api.profile().then((p) => {
      setProfile(p)
      setSchool(p.current_school || '')
      setMajor(p.major || '')
      setYear(p.year || '')
      setGoalType(goalAlias(p.goal_type))
      setTarget([p.target_school, p.target_major].filter(Boolean).join(' '))
    }).catch(() => {})
    api.syllabusStats().then(setStats).catch(() => {})
    api.officialSources().then(setOfficial).catch(() => {})
    api.schools().then(setSchools).catch(() => {})
    loadPlans()
    api.schedule().then((s) => { setSchedule(s); setDraft(s.courses) }).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // 300ms 防抖：学校/专业每击键一个请求会造成响应竞态
    if (!school) { setMajorsInfo(null); return }
    const t = setTimeout(() => api.majorsForSchool(school).then(setMajorsInfo).catch(() => setMajorsInfo(null)), 300)
    return () => clearTimeout(t)
  }, [school])

  useEffect(() => {
    if (school && major) {
      const t = setTimeout(() =>
        api.program(school, major).then((p) => { setProgram(p); setFulltext(null) }).catch(() => setProgram(null)), 300)
      return () => clearTimeout(t)
    } else { setProgram(null); setFulltext(null) }
  }, [school, major])

  const loadFulltext = async () => {
    if (fulltext) { setFulltext(null); return }
    try { setFulltext(await api.syllabusFulltext(school, major)) } catch (e: any) { alert(e.message) }
  }

  const saveMySchool = async () => {
    if (!profile) return
    try {
      const p = await api.saveProfile({ ...profile, current_school: school, major, year })
      setProfile(p)
      setScheduleMsg('✓ 已写入个人档案')
      setTimeout(() => setScheduleMsg(''), 2000)
    } catch (e: any) { alert('保存档案失败：' + (e.message || '未知错误')) }
  }

  // ---------- 课程表操作 ----------
  const reloadSchedule = (term?: string) =>
    api.schedule(term).then((s) => { setSchedule(s); setDraft(s.courses) }).catch(() => {})

  const importText = async () => {
    if (!schedule?.term) { alert('请先填写学期名（如 2025-2026-1 或 大三上）'); return }
    setBusy('schedule')
    try {
      const r = await api.importScheduleText(pasteText)
      setDraft(r.courses)
      setScheduleMsg(`解析出 ${r.courses.length} 门课（${r.method}），检查无误后点「保存课程表」`)
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const importFile = async (f: File) => {
    if (!schedule?.term) { alert('请先填写学期名（如 2025-2026-1 或 大三上）'); return }
    setBusy('schedule')
    try {
      const r = await api.importScheduleFile(f)
      setDraft(r.courses)
      setScheduleMsg(`解析出 ${r.courses.length} 门课（${r.method}），检查无误后点「保存课程表」`)
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const saveSchedule = async () => {
    if (!schedule?.term) { alert('请先填写学期名'); return }
    setBusy('schedule')
    try {
      const r = await api.saveSchedule(schedule.term, draft)
      setDraft(r.courses)
      await reloadSchedule(schedule.term)
      setScheduleMsg(`✓ 已保存 ${r.saved} 门课`)
    } catch (e: any) { alert(e.message) }
    setBusy('')
    setTimeout(() => setScheduleMsg(''), 2500)
  }

  const setDraftAt = (i: number, patch: Partial<CourseEntry>) =>
    setDraft((d) => d.map((c, j) => (j === i ? { ...c, ...patch } : c)))

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
      setScheduleMsg(`✓ 培养方案已导入并校准（抽取到 ${r.fields_found.length} 类字段）`)
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const importHandbookText = async () => {
    const text = hbPasteText.trim()
    if (!text) { alert('请先粘贴培养手册/培养方案文本'); return }
    setBusy('syllabus')
    try {
      const r = await api.importSyllabusText(school, major, text)
      const p = await api.program(r.school, r.major)
      setProgram(p)
      setScheduleMsg(`✓ 培养方案已导入并校准（抽取到 ${r.fields_found.length} 类字段）`)
      setHbPasteOpen(false); setHbPasteText('')
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  // ---------- 目标计划 ----------
  const loadPlans = () =>
    api.careerPlans().then(async (metas) =>
      setPlans(await Promise.all(metas.map((m) => api.careerPlan(m.id))))).catch(() => {})

  const generate = async () => {
    setBusy('plan'); setErr('')
    try {
      const p = await api.generateCareerPlan({ school, major, year, goal_type: goalType, target, term: schedule?.term || '', horizon })
      await loadPlans()
      setOpenPlan(p.id)
    } catch (e: any) { setErr(e.message) }
    setBusy('')
  }

  const toggleTask = async (pid: string, taskId: string, done: boolean) => {
    try {
      await api.toggleCareerTask(pid, taskId, done)
      const full = await api.careerPlan(pid)
      setPlans((ps) => ps.map((p) => (p.id === pid ? full : p)))
    } catch (e: any) { alert('打卡失败：' + (e.message || '未知错误')) }
  }

  const pushPlan = async (pid: string) => {
    if (!spaces.length) { alert('还没有课程空间：先在左侧新建一个'); return }
    const sid = prompt(`同步到哪个课程空间？输入编号：\n${spaces.map((s, i) => `${i + 1}. ${s.name}`).join('\n')}\n（直接回车=1）`, '1')
    if (!sid) return
    const idx = parseInt(sid) - 1
    if (isNaN(idx) || !spaces[idx]) return
    try {
      const r = await api.pushCareerPlan(pid, spaces[idx].id)
      alert(`已同步 ${r.synced} 条任务到「${spaces[idx].name}」的学习计划\n（同一计划重复同步不会产生重复任务，已完成状态会保留）`)
      onOpenSpace(spaces[idx].id)
    } catch (e: any) { alert(e.message) }
  }

  const removePlan = async (pid: string) => {
    if (!confirm('删除该计划？\n已同步到课程空间的该计划任务会一并移除。')) return
    try {
      const r: any = await api.deleteCareerPlan(pid)
      setPlans((ps) => ps.filter((p) => p.id !== pid))
      if (r?.removed_pushed_tasks) alert(`已删除计划，并移除课程空间中来自该计划的 ${r.removed_pushed_tasks} 条任务`)
    } catch (e: any) { alert('删除失败：' + (e.message || '未知错误')) }
  }

  const planTotal = plans.reduce((a, p) => a + p.tasks.filter((t) => !t.done).length, 0)

  return (
    <div className="content">
      {/* ① 我的学籍 */}
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>① 我的学校与专业</h3>
        <p className="sub">收录全国 985/211 高校（可搜简称如「示例大学」「华科」）；专业覆盖 21 个主流培养方案框架，未覆盖的专业可导入本校培养手册校准。</p>
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
          <button className="btn ghost" onClick={saveMySchool}>写入个人档案</button>
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

      {/* ② 培养方案 */}
      {program && (
        <div className="card" style={{ marginBottom: 18 }}>
          <h3>② 培养方案{program.major ? ` · ${program.major}` : ''}
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
                  <thead><tr><th style={{ width: 90 }}>学期</th><th>关键课程</th><th>阶段要点</th></tr></thead>                  <tbody>
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
                        {fulltext ? '收起全文' : `查看官方培养方案全文${fulltext ? '' : ''}`}
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

      {/* ③ 本学期课程表 */}
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>③ 本学期课程表</h3>
        <p className="sub">上传教务系统截图（离线 OCR）、Excel 导出或直接粘贴文本，自动解析成课表；解析结果可逐格修正。计划生成会参考这份课表。</p>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
          <input type="text" list="sp-terms" placeholder="学期名（如 2025-2026-1 / 大三上）" style={{ width: 240 }}
            value={schedule?.term || ''} onChange={(e) => setSchedule((s) => (s ? { ...s, term: e.target.value } : s))} />
          <datalist id="sp-terms">{(schedule?.terms || []).map((t) => <option key={t.term} value={t.term} />)}</datalist>
          <button className="btn ghost small" disabled={busy === 'schedule'}
            onClick={() => document.getElementById('schedule-file')?.click()}>上传截图 / Excel / CSV</button>
          <input id="schedule-file" type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,.xlsx,.csv,.txt,.md" hidden
            onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); e.target.value = '' }} />
          {(schedule?.terms.length || 0) > 0 && (
            <select value="" onChange={(e) => e.target.value && reloadSchedule(e.target.value)}>
              <option value="">切换已有学期…</option>
              {schedule!.terms.map((t) => <option key={t.term} value={t.term}>{t.term}（{t.courses} 门）</option>)}
            </select>
          )}
          {schedule && schedule.term && (
            <button className="btn danger ghost small" onClick={async () => {
              if (!confirm(`清空「${schedule.term}」的课程表？`)) return
              try {
                await api.deleteSchedule(schedule.term); await reloadSchedule(schedule.term)
              } catch (e: any) { alert('清空失败：' + (e.message || '未知错误')) }
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
          {scheduleMsg && <span className="sub">{scheduleMsg}</span>}
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
                      <td><button className="btn danger ghost small" onClick={() => setDraft((d) => d.filter((_, j) => j !== i))}>✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        )}
      </div>

      {/* ④ 目标导向学习计划 */}
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>④ 目标导向学习计划</h3>
        <p className="sub">以你的目标为主线，结合培养方案先修链、本学期课表与各空间薄弱点，生成分阶段可打卡计划；可一键同步到课程空间执行。</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, marginTop: 12 }}>
          <select value={goalType} onChange={(e) => setGoalType(e.target.value)}>
            {GOALS.map((g) => <option key={g} value={g}>目标：{g}</option>)}
          </select>
          <input type="text" placeholder="目标去向（如 华中科技大学 计算机技术 / 大厂后端岗）"
            value={target} onChange={(e) => setTarget(e.target.value)} />
          <select value={horizon} onChange={(e) => setHorizon(e.target.value)}>
            {HORIZONS.map((h) => <option key={h} value={h}>跨度：{h}</option>)}
          </select>
          <button className="btn" disabled={busy === 'plan'} onClick={generate}>
            {busy === 'plan' ? <><span className="spin" /> 生成中…</> : '生成学习计划'}
          </button>
        </div>
        {err && <p className="sub" style={{ color: 'var(--red)', marginTop: 8 }}>{err}</p>}
        {!school || !major ? (
          <p className="sub" style={{ marginTop: 8 }}>提示：先在上方选择学校与专业，计划会更贴合培养方案。</p>
        ) : schedule && !schedule.courses.length ? (
          <p className="sub" style={{ marginTop: 8 }}>提示：导入本学期课表后，计划会按在读课程分配精力。</p>
        ) : null}
      </div>

      {/* 计划列表 */}
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
    </div>
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
