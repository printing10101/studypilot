// 子页签②：课程表（上传/粘贴解析 → 周视图预览 → 逐格修正 → 保存）。
// schedule 元数据（当前学期/学期列表）由编排层持有——学涯计划生成要参考学期名。
import { useEffect, useMemo, useState } from 'react'
import { api, CourseEntry, ScheduleData } from '../../api'
import { useUX } from '../../ux'
import { DAYS, PERIOD_ORDER, periodKey, periodLabel } from './common'

export function ScheduleTab({ schedule, onScheduleChange, flash, msg, onDismissMsg }: {
  schedule: ScheduleData | null
  onScheduleChange: (s: ScheduleData | null) => void
  flash: (text: string) => void
  msg: string
  onDismissMsg: () => void
}) {
  const { toast, confirm: uxConfirm } = useUX()
  const [draft, setDraft] = useState<CourseEntry[]>([])
  const [draftDirty, setDraftDirty] = useState(false)  // 草稿已改未保存：被覆盖前必须确认
  const [pasteText, setPasteText] = useState('')
  const [busy, setBusy] = useState('')

  // schedule 由编排层加载/切换：这里跟随同步草稿（脏标记一并复位）
  useEffect(() => {
    setDraft(schedule?.courses || [])
    setDraftDirty(false)
  }, [schedule])

  const reloadSchedule = async (term?: string) => {
    if (draftDirty) {
      const go = await uxConfirm({ title: '覆盖未保存的修改', message: '课程表有修改尚未保存，继续将丢失这些修改。', confirmText: '继续' })
      if (!go) return
    }
    api.schedule(term).then((s) => { onScheduleChange(s); setDraft(s.courses); setDraftDirty(false) }).catch(() => {
      // 读取失败也要给出可编辑的骨架：schedule 为 null 时学期名输入框永远无法输入
      // （onChange 直接丢弃），而导入/保存又都要求先填学期名 → 整个页签死锁
      onScheduleChange(schedule || { term: '', terms: [], courses: [] })
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

  return (
    <div className="card">
      <h3>本学期课程表</h3>
      <p className="sub">上传教务系统截图（离线 OCR）、Excel 导出或直接粘贴文本，自动解析成课表；解析结果可逐格修正。学涯计划生成会参考这份课表。</p>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
        <input type="text" list="sp-terms" placeholder="学期名（如 2025-2026-1 / 大三上）" style={{ width: 240 }}
          value={schedule?.term || ''}
          onChange={(e) => onScheduleChange(schedule ? { ...schedule, term: e.target.value } : { term: e.target.value, terms: [], courses: [] })} />
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
              onClick={onDismissMsg}>✕</button>
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
  )
}

const methodLabel = (m: string) => (m === 'llm' ? '智能解析' : m === 'rule' ? '规则解析' : m)
