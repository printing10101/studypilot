// 学习计划：空间级任务全量管理（阶段分组、打卡、导出）；今日切片在「今日学习」页
import { useEffect, useRef, useState } from 'react'
import { api, PlanTask, runSkillStream } from '../api'
import { downloadMd, EmptyState, Icon, PlanTaskRow } from '../ui'
import { useUX } from '../ux'

export function PlanView({ sid }: { sid: string }) {
  const { toast, confirm: uxConfirm } = useUX()
  const [plan, setPlan] = useState<{ tasks: PlanTask[]; done: number; total: number } | null>(null)
  const [loadErr, setLoadErr] = useState(false)
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const [genPhase, setGenPhase] = useState('')
  // 切空间竞态防护：不重置旧 plan 会让上一空间的任务滞留可交互（打卡 404）
  const seq = useRef(0)
  const genAbort = useRef<AbortController | null>(null)

  const refresh = () => {
    const id = ++seq.current
    return api.plan(sid).then((p) => {
      if (id !== seq.current) return
      setPlan(p); setLoadErr(false)
    }).catch(() => { if (id === seq.current) setLoadErr(true) })
  }
  useEffect(() => {
    seq.current++
    genAbort.current?.abort(); genAbort.current = null
    setPlan(null); setLoadErr(false); setGoal(''); setBusy(false); setGenPhase('')
    refresh()
  }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => genAbort.current?.abort(), [])

  const generate = async () => {
    // 重新生成会整体替换现有计划（含已完成记录），属于破坏性操作，先确认
    if (plan && plan.total > 0) {
      const go = await uxConfirm({ title: '重新生成计划',
        message: `将整体替换当前计划（共 ${plan.total} 项任务，已完成 ${plan.done} 项）。继续？`,
        confirmText: '重新生成' })
      if (!go) return
    }
    // SSE 流式：按钮实时显示拆解/入库阶段，可中途停止
    const ctrl = new AbortController()
    genAbort.current = ctrl
    setBusy(true)
    setGenPhase('准备中…')
    runSkillStream(sid, 'plan.study', { goal }, {
      onPhase: setGenPhase,
      onDone: () => { setBusy(false); setGenPhase(''); refresh() },
      onError: (m) => { setBusy(false); setGenPhase(''); toast('error', m) },
      onAbort: () => { setBusy(false); setGenPhase('') },
    }, ctrl.signal)
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

  const exportPlan = async () => {
    try {
      downloadMd('plan', await api.exportMd(sid, 'plan'))
    } catch (e: any) {
      // 此前无 catch：导出失败 unhandled rejection，按钮看起来像坏的
      toast('error', '导出失败：' + (e.message || '未知错误'))
    }
  }

  if (loadErr && !plan) {
    return (
      <div className="content">
        <div className="card">
          <EmptyState icon="warn" title="学习计划加载失败" desc="后端服务可能没有启动或正在重启，稍等片刻后重试。"
            action="重新加载" onAction={() => { setLoadErr(false); refresh() }} />
        </div>
      </div>
    )
  }
  if (!plan) return <div className="empty"><span className="spin" /> 加载中…</div>
  const pct = plan.total ? Math.round((plan.done / plan.total) * 100) : 0
  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>学习计划</h3>
        <p className="sub">规划师结合你的薄弱点档案，把目标拆成分阶段任务；完成打卡，重新生成会整体替换当前计划。今日到期的任务会同时出现在「今日学习」清单里。</p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
          <input type="text" placeholder="学习目标（如：一个月内吃透电磁学，或留空系统掌握本课程）"
            value={goal} onChange={(e) => setGoal(e.target.value)} disabled={busy} />
          <button className="btn" disabled={busy} onClick={generate} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> {genPhase || '规划中…'}</> : <><Icon name="plan" size={14} /> {plan.total ? '重新生成计划' : '生成学习计划'}</>}
          </button>
          {busy && (
            <button className="btn ghost" onClick={() => { genAbort.current?.abort(); genAbort.current = null }} style={{ flex: 'none' }}>
              停止
            </button>
          )}
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
            {plan.tasks.map((t, i) => {
              // 阶段分组头：与前一任务的 phase 比较（等价于旧写法且不在渲染期改写外层变量）
              const showPhase = i === 0 || t.phase !== plan.tasks[i - 1].phase
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
