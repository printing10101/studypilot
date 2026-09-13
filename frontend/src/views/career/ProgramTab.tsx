// 子页签①：学籍与培养方案（学校/专业选择、培养方案展示、本校手册导入校准）。
import { useEffect, useRef, useState } from 'react'
import { api, Program, StudentProfile, SyllabusFulltext, SyllabusMajors, SyllabusOfficial, SyllabusSchool, SyllabusStats } from '../../api'
import { useUX } from '../../ux'

export function ProgramTab({ school, major, year, onSchoolChange, onMajorChange, onYearChange,
  profile, profileErr, reloadProfile, onProfileSaved, flash }: {
    school: string; major: string; year: string
    onSchoolChange: (v: string) => void
    onMajorChange: (v: string) => void
    onYearChange: (v: string) => void
    profile: StudentProfile | null
    profileErr: string
    reloadProfile: () => void
    onProfileSaved: (p: StudentProfile) => void
    flash: (text: string) => void
  }) {
  const { toast } = useUX()
  const [schools, setSchools] = useState<SyllabusSchool[]>([])
  const [majorsInfo, setMajorsInfo] = useState<SyllabusMajors | null>(null)
  const [program, setProgram] = useState<Program | null>(null)
  const [fulltext, setFulltext] = useState<SyllabusFulltext | null>(null)
  const [stats, setStats] = useState<SyllabusStats | null>(null)
  const [official, setOfficial] = useState<SyllabusOfficial[]>([])
  const [busy, setBusy] = useState('')
  // 培养手册文本导入：window.prompt 是单行输入框，多行手册文本放不进来，改用页内弹层
  const [hbPasteOpen, setHbPasteOpen] = useState(false)
  const [hbPasteText, setHbPasteText] = useState('')

  useEffect(() => {
    api.syllabusStats().then(setStats).catch(() => {})
    api.officialSources().then(setOfficial).catch(() => {})
    api.schools().then(setSchools).catch(() => {})
  }, [])

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

  const loadFulltext = async () => {
    if (fulltext) { setFulltext(null); return }
    try { setFulltext(await api.syllabusFulltext(school, major)) } catch (e: any) { toast('error', e.message) }
  }

  const saveMySchool = async () => {
    if (!profile) {
      // 档案未加载成功时静默 no-op 会让人以为已保存；必须给明确反馈
      toast('error', '个人档案尚未加载成功，无法写入。请刷新页面重试。')
      return
    }
    try {
      const p = await api.saveProfile({ ...profile, current_school: school, major, year })
      onProfileSaved(p)
      flash('✓ 已写入个人档案')
    } catch (e: any) { toast('error', '保存档案失败：' + (e.message || '未知错误')) }
  }

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

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>我的学校与专业</h3>
        <p className="sub">收录全国 985/211 高校（可搜简称如「川大」「华科」）；专业覆盖 21 个主流培养方案框架，未覆盖的专业可导入本校培养手册校准。档案在学校/专业/年级变动后可一键写回「个人中心」。</p>
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
            <button className="btn small" onClick={reloadProfile}>重试</button>
          </div>
        ) : null}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
          <div>
            <input type="text" list="sp-schools" placeholder="选择/输入学校（如 四川大学、华科）"
              value={school} onChange={(e) => onSchoolChange(e.target.value)} />
            <datalist id="sp-schools">
              {schools.map((s) => <option key={s.name} value={s.name}>{`${s.tier} · ${s.region} · ${s.strong.slice(0, 2).join('/')}`}</option>)}
            </datalist>
          </div>
          <div>
            <input type="text" list="sp-majors" placeholder="选择/输入专业（如 计算机科学与技术）"
              value={major} onChange={(e) => onMajorChange(e.target.value)} disabled={!school} />
            <datalist id="sp-majors">
              {[...(majorsInfo?.official_majors || []), ...(majorsInfo?.custom_majors || []),
                ...(majorsInfo?.template_majors || []), ...(majorsInfo?.strong || [])]
                .map((m) => <option key={m} value={m} />)}
            </datalist>
          </div>
          <input type="text" placeholder="当前年级（如 大三上）" value={year}
            onChange={(e) => onYearChange(e.target.value)} />
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
              <span key={s} className="badge" style={{ cursor: 'pointer' }} onClick={() => onMajorChange(s)}>{s}</span>
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
