// 学习计划：空间级任务全量管理（阶段分组、打卡、导出）；今日切片在「今日学习」页
import { useEffect, useState } from 'react'
import { api, PlanTask } from '../api'
import { downloadMd, Icon, PlanTaskRow } from '../ui'
import { useUX } from '../ux'

export function PlanView({ sid }: { sid: string }) {
  const { toast } = useUX()
  const [plan, setPlan] = useState<{ tasks: PlanTask[]; done: number; total: number } | null>(null)
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = () => api.plan(sid).then(setPlan).catch(() => {})
  useEffect(() => { refresh() }, [sid])

  const generate = async () => {
    setBusy(true)
    try {
      await api.runSkill(sid, 'plan.study', { goal })
      await refresh()
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const toggle = async (t: PlanTask) => {
    try {
      await api.togglePlanTask(sid, t.id, !t.done)
    } catch (e: any) { toast('error', '打卡失败：' + (e.message || '未知错误')) }
    refresh()
  }

  const setTaskDate = async (t: PlanTask, date: string) => {
    try { await api.setTaskDate(sid, t.id, date) } catch (e: any) { toast('error', e.message) }
    refresh()
  }

  const exportPlan = async () => downloadMd('plan', await api.exportMd(sid, 'plan'))

  if (!plan) return <div className="empty"><span className="spin" /> 加载中…</div>
  const pct = plan.total ? Math.round((plan.done / plan.total) * 100) : 0
  let phase = ''
  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>学习计划</h3>
        <p className="sub">规划师结合你的薄弱点档案，把目标拆成分阶段任务；完成打卡，重新生成会整体替换当前计划。今日到期的任务会同时出现在「今日学习」清单里。</p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
          <input type="text" placeholder="学习目标（如：一个月内吃透电磁学，或留空系统掌握本课程）"
            value={goal} onChange={(e) => setGoal(e.target.value)} />
          <button className="btn" disabled={busy} onClick={generate} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> 规划中</> : <><Icon name="plan" size={14} /> {plan.total ? '重新生成计划' : '生成学习计划'}</>}
          </button>
          {plan.total > 0 && (
            <button className="btn ghost" onClick={exportPlan} style={{ flex: 'none' }}>
              <Icon name="book" size={13} /> 导出
            </button>
          )}
        </div>
      </div>

      {plan.total > 0 && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <b>进度 {plan.done}/{plan.total}</b>
            <div className="mastery-track" style={{ flex: 1 }} title={`${pct}%`}>
              <div className="mastery-fill mastered" style={{ width: `${pct}%` }} />
              <span className="mastery-label">{pct}%</span>
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            {plan.tasks.map((t) => {
              const showPhase = t.phase !== phase
              phase = t.phase
              return (
                <div key={t.id}>
                  {showPhase && <p className="sub" style={{ margin: '16px 0 6px', fontWeight: 700, color: 'var(--text)' }}>◈ {t.phase || '任务'}</p>}
                  <PlanTaskRow t={t} onToggle={toggle} onDate={setTaskDate} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
