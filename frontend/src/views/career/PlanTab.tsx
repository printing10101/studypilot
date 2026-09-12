// 子页签④：学涯计划（目标导向生成分阶段计划、打卡、同步到课程空间）。
import { useEffect, useRef, useState } from 'react'
import { api, CareerPlan, Space, StudentProfile } from '../../api'
import { downloadMd } from '../../ui'
import { useUX } from '../../ux'
import { GOALS, HORIZONS, goalAlias } from './common'

export function PlanTab({ plans, setPlans, loadPlans, school, major, year, scheduleTerm, scheduleEmpty, profile, spaces, onGoto }: {
  plans: CareerPlan[]
  setPlans: React.Dispatch<React.SetStateAction<CareerPlan[]>>
  loadPlans: () => void
  school: string; major: string; year: string
  scheduleTerm: string
  scheduleEmpty: boolean
  profile: StudentProfile | null
  spaces: Space[]
  onGoto: (t: string) => void
}) {
  const { toast, confirm: uxConfirm, select: uxSelect } = useUX()
  // 首次拿到档案时初始化目标（与原行为一致：只在档案首次到达时装载一次）
  const [goalType, setGoalType] = useState('考研')
  const [target, setTarget] = useState('')
  const [horizon, setHorizon] = useState('本学期')
  const [openPlan, setOpenPlan] = useState('')
  const [busy, setBusy] = useState('')
  const profileApplied = useRef(false)
  useEffect(() => {
    if (profile && !profileApplied.current) {
      profileApplied.current = true
      setGoalType(goalAlias(profile.goal_type))
      setTarget([profile.target_school, profile.target_major].filter(Boolean).join(' '))
    }
  }, [profile])

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
    api.generateCareerPlan({ school, major, year, goal_type: goalType, target, term: scheduleTerm, horizon }, signal)

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

  return (
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
        ) : scheduleEmpty ? (
          <p className="sub" style={{ marginTop: 8 }}>提示：导入本学期课表后，计划会按在读课程分配精力。</p>
        ) : null}
      </div>

      {plans.length > 0 && (
        <div className="card">
          <h3>我的学涯计划</h3>
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
  )
}
