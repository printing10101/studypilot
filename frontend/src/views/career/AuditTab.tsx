// 子页签③：成绩审核（已修课程录入/成绩单批量导入 → 对照培养方案三态核对）。
import { useEffect, useState } from 'react'
import { api, AuditResult, TakenCourse } from '../../api'
import { useUX } from '../../ux'

export function AuditTab({ school, major }: { school: string; major: string }) {
  const { toast, confirm: uxConfirm } = useUX()
  const [taken, setTaken] = useState<TakenCourse[]>([])
  const [auditRes, setAuditRes] = useState<AuditResult | null>(null)
  const [newCourse, setNewCourse] = useState({ name: '', credit: '', grade: '', semester: '', status: 'done' })
  const [transcriptText, setTranscriptText] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api.auditCourses().then((r) => setTaken(r.courses)).catch(() => {})
  }, [])

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

  return (
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
  )
}
