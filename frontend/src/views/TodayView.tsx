// 今日学习：空间首页。到期复习/闪卡/任务/错题/讲义五块汇总 + 每日一题 + 讲义复习
import { useEffect, useRef, useState } from 'react'
import { api, DueDocReview, NavExtra, PlanTask, runSkillStream, TodayData } from '../api'
import { EmptyState, Icon, PlanTaskRow } from '../ui'
import { useUX } from '../ux'

// 乐观打卡：立即把任务移入/移出「已完成」，失败再回滚——否则点击后界面毫无反应，
// 慢时连点两次 = toggle 两次 = 状态还原，看起来像点坏了
function applyToggle(d: TodayData, tid: string, done: boolean): TodayData {
  const all = [...d.tasks_today, ...d.tasks_unscheduled, ...d.done_today]
  const t = all.find((x) => x.id === tid)
  if (!t) return d
  const rest = all.filter((x) => x.id !== tid)
  const moved: PlanTask = { ...t, done: done ? 1 : 0 }
  const tasks_today: PlanTask[] = []
  const unscheduled: PlanTask[] = []
  const doneToday: PlanTask[] = []
  for (const x of rest) {
    if (x.done) doneToday.push(x)
    else if (x.due_date === d.date || (x.due_date && x.due_date < d.date)) tasks_today.push(x)
    else unscheduled.push(x)
  }
  if (moved.done) doneToday.unshift(moved)
  else if (moved.due_date === d.date || (moved.due_date && moved.due_date < d.date)) tasks_today.unshift(moved)
  else unscheduled.unshift(moved)
  return { ...d, tasks_today, tasks_unscheduled: unscheduled, done_today: doneToday }
}

export function TodayView({ sid, onGoto }: { sid: string; onGoto: (t: string, extra?: NavExtra) => void }) {
  const { toast } = useUX()
  const [data, setData] = useState<TodayData | null>(null)
  const [docDue, setDocDue] = useState<DueDocReview[] | null>(null)
  const [docErr, setDocErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [reviewPhase, setReviewPhase] = useState('')
  const [loadErr, setLoadErr] = useState(false)
  // 切空间竞态防护：组件实例被复用，旧空间的慢响应不得覆盖新空间数据
  // （每个资源独立计数器：两个并发请求共用一个计数器会互相作废）
  const seqToday = useRef(0)
  const seqDocs = useRef(0)
  const reviewAbort = useRef<AbortController | null>(null)
  const refresh = () => {
    const id = ++seqToday.current
    return api.today(sid).then((d) => {
      if (id !== seqToday.current) return
      setData(d); setLoadErr(false)
    }).catch(() => { if (id === seqToday.current) setLoadErr(true) })
  }
  const refreshDocs = () => {
    const id = ++seqDocs.current
    setDocErr('')
    return api.dueDocReviews(sid).then((r) => { if (id === seqDocs.current) setDocDue(r) })
      .catch((e: any) => { if (id === seqDocs.current) { setDocDue([]); setDocErr(e?.message || '网络错误') } })
  }
  const reloadAll = () => { setLoadErr(false); refresh(); refreshDocs() }
  useEffect(() => {
    seqToday.current++; seqDocs.current++  // 使在途请求全部过期
    reviewAbort.current?.abort(); reviewAbort.current = null
    setBusy(false); setReviewPhase('')
    setData(null); setDocDue(null); setDocErr(''); reloadAll()
  }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => reviewAbort.current?.abort(), [])

  const toggleTask = async (t: PlanTask) => {
    const target = !t.done
    const prev = data
    setData((d) => (d ? applyToggle(d, t.id, target) : d))
    try {
      await api.togglePlanTask(sid, t.id, target)
    } catch (e: any) {
      if (prev) setData(prev)  // 失败回滚乐观更新
      // 与 PlanView 同一口径：打卡失败要有提示，静默回弹会让用户以为点坏了
      toast('error', '打卡失败：' + (e.message || '未知错误'))
    }
    refresh()
  }
  const setTaskDate = async (t: PlanTask, date: string) => {
    try { await api.setTaskDate(sid, t.id, date) } catch (e: any) { toast('error', e.message) }
    refresh()
  }
  const makeReview = () => {
    // 走流式端点：生成期间按钮显示阶段进度，且可中断（本地模型下这是分钟级长任务）
    const ctrl = new AbortController()
    reviewAbort.current = ctrl
    setBusy(true); setReviewPhase('准备中…')
    runSkillStream(sid, 'review.generate', { count: 5 }, {
      onPhase: setReviewPhase,
      onDone: (r: any) => {
        setBusy(false); setReviewPhase('')
        toast('info', '已按到期薄弱点生成复习测验，答对会自动推进复习间隔')
        const made = Array.isArray(r) ? r[0] : r
        onGoto('quiz', made?.quiz_id ? { quizId: made.quiz_id } : undefined)
      },
      onError: (m: string) => { setBusy(false); setReviewPhase(''); toast('error', m) },
      onAbort: () => { setBusy(false); setReviewPhase('') },
    }, ctrl.signal)
  }

  if (loadErr && !data) {
    return (
      <div className="content">
        <div className="card">
          <EmptyState icon="warn" title="今日数据加载失败" desc="后端服务可能没有启动或正在重启，稍等片刻后重试。"
            action="重新加载" onAction={reloadAll} />
        </div>
      </div>
    )
  }
  if (!data) return <div className="content"><div className="empty"><span className="spin" /> 加载中…</div></div>
  const d = new Date(data.date + 'T00:00:00')
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  const today = data.date
  const doneCount = data.done_today.length
  const openCount = data.tasks_today.length
  const totalToday = openCount + doneCount
  const pct = totalToday ? Math.round((doneCount / totalToday) * 100) : 0

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>今日学习 · {d.getMonth() + 1} 月 {d.getDate()} 日 周{week}</h3>
          <span className="sub">到期复习、闪卡与计划任务都汇总在这里，做完即走</span>
          <div style={{ flex: 1 }} />
          <button className="btn small" disabled={busy} onClick={makeReview}>
            {busy ? <><span className="spin" /> {reviewPhase || '生成中…'}</> : <><Icon name="quiz" size={12} /> 生成到期复习题</>}
          </button>
          {busy && (
            <button className="btn ghost small" onClick={() => { reviewAbort.current?.abort(); reviewAbort.current = null }}>停止</button>
          )}
        </div>
        <div className="today-grid" style={{ marginTop: 14 }}>
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('analytics')}>
            <span className="sub">到期复习</span>
            <b className="num" style={{ color: data.due_total ? 'var(--orange)' : 'var(--green)' }}>{data.due_total}</b>
            <span className="sub">个知识点 · 学习分析</span>
          </div>
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('cards')}>
            <span className="sub">待刷闪卡</span>
            <b className="num" style={{ color: data.flash_due ? 'var(--orange)' : 'var(--green)' }}>{data.flash_due}</b>
            <span className="sub">共 {data.flash_total} 张 · 去闪卡</span>
          </div>
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('plan')}>
            <span className="sub">今日任务</span>
            <b className="num">{openCount}</b>
            <span className="sub">已打卡 {doneCount} · 学习计划</span>
          </div>
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('quiz', { sub: 'wrong' })}>
            <span className="sub">错题</span>
            <b className="num" style={{ color: data.wrong_count ? 'var(--red)' : 'var(--green)' }}>{data.wrong_count}</b>
            <span className="sub">可变式训练 · 直达错题本</span>
          </div>
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('library')}>
            <span className="sub">讲义复习</span>
            <b className="num" style={{ color: docDue?.length ? 'var(--orange)' : 'var(--green)' }}>{docDue?.length ?? 0}</b>
            <span className="sub">份讲义到期 · 本页下方</span>
          </div>
        </div>
        <DailyQuestionCard sid={sid} onGoto={onGoto} />
        {/* 学习速度 + 完成预测 */}
        {data.velocity && data.velocity.concepts_total > 0 && (
          <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--bg)', borderRadius: 10, fontSize: 13, display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'center' }}>
            <span>
              <span className="sub">学习进度</span>{' '}
              <b>{data.velocity.concepts_mastered}/{data.velocity.concepts_total}</b> 个知识点已掌握
            </span>
            {data.velocity.concepts_per_day > 0 && (
              <span>
                <span className="sub">速度</span>{' '}
                <b>{data.velocity.concepts_per_day}</b> 个/天
                {data.velocity.velocity_trend === 'accelerating' && ' ↑ 加速中'}
                {data.velocity.velocity_trend === 'decelerating' && ' ↓ 放缓中'}
              </span>
            )}
            {data.forecast && !data.forecast.is_complete && data.forecast.expected_date && (
              <span>
                <span className="sub">预计完成</span>{' '}
                <b>{data.forecast.expected_date}</b>
                {data.forecast.confidence === 'high' && '（高置信）'}
                {data.forecast.optimistic_date && (
                  <span className="sub" style={{ marginLeft: 6 }}>
                    乐观 {data.forecast.optimistic_date} · 悲观 {data.forecast.pessimistic_date}
                  </span>
                )}
              </span>
            )}
            {data.question_bank && data.question_bank.total > 0 && (
              <span className="sub">题库 {data.question_bank.total} 题（已用 {data.question_bank.used}）</span>
            )}
          </div>
        )}
        {/* 证据导向方法 + 人格画像 + 综合度量 */}
        {data.methods && (data.methods.daily || data.methods.items?.length > 0) && (
          <div style={{ marginTop: 14, padding: '12px 14px', background: 'var(--bg)', borderRadius: 10, fontSize: 13 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
              <b>今日学习方法</b>
              {data.methods.focus && <span className="badge expert">主攻：{data.methods.focus}</span>}
              {data.methods.persona?.name && (
                <span className="badge" title={(data.methods.persona.evidence || []).join('；')}>
                  画像：{data.methods.persona.name}
                </span>
              )}
            </div>
            {data.methods.persona?.session && (
              <p style={{ margin: '8px 0 0' }}>会话建议：{data.methods.persona.session}</p>
            )}
            <p style={{ margin: '8px 0 10px', color: 'var(--muted)', lineHeight: 1.55 }}>{data.methods.daily}</p>
            {data.methods.items?.length > 0 && (
              <div style={{ display: 'grid', gap: 8 }}>
                {data.methods.items.map((m) => (
                  <div key={m.id} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
                    <span className="badge">{m.name}</span>
                    <span style={{ flex: 1, minWidth: 200 }}>{m.how}</span>
                    {m.why && <span className="sub">{m.why}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {data.metrics && (
          <div style={{ marginTop: 12, display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 13, padding: '10px 14px', background: 'var(--bg)', borderRadius: 10 }}>
            {data.metrics.consistency?.streak > 0 && (
              <span>连续学习 <b>{data.metrics.consistency.streak}</b> 天</span>
            )}
            {data.metrics.load && (
              <span title={data.metrics.load.advice}>
                今日负载 <b>{data.metrics.load.band === 'high' ? '高' : data.metrics.load.band === 'medium' ? '中' : '低'}</b>
                <span className="sub">（建议 {data.metrics.load.suggested_minutes} 分钟）</span>
              </span>
            )}
            {data.metrics.calibration?.n > 0 && (
              <span title={data.metrics.calibration.label || undefined}>
                校准偏差 <b>{Math.round(data.metrics.calibration.avg_bias * 100)}%</b>
                {data.metrics.calibration.label && <span className="sub">（{data.metrics.calibration.label}）</span>}
              </span>
            )}
            {data.metrics.countdown && data.metrics.countdown.days_left >= 0 && (
              <span>距目标日 <b>{data.metrics.countdown.days_left}</b> 天
                <span className="badge expert" style={{ marginLeft: 6 }}>{data.metrics.countdown.phase}</span>
              </span>
            )}
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <DocReviewSection sid={sid} due={docDue} err={docErr} onRetry={refreshDocs} onChanged={refreshDocs} onGoto={onGoto} />
      </div>

      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>任务清单</h3>
          {totalToday > 0 && (
            <div className="mastery-track" style={{ flex: 1, maxWidth: 260 }} title={`${pct}%`}>
              <div className="mastery-fill mastered" style={{ width: `${pct}%` }} />
              <span className="mastery-label">{doneCount}/{totalToday}</span>
            </div>
          )}
          <div style={{ flex: 1 }} />
          <button className="btn ghost small" onClick={() => onGoto('plan')}>管理学习计划</button>
        </div>
        {openCount + data.tasks_unscheduled.length + doneCount > 0 ? (
          <>
            <div style={{ marginTop: 8 }}>
              {data.tasks_today.map((t) => <PlanTaskRow key={t.id} t={t} overdue={t.due_date < today} onToggle={toggleTask} onDate={setTaskDate} />)}
            </div>
            {data.tasks_unscheduled.length > 0 && (
              <>
                <p className="sub" style={{ margin: '14px 0 2px', fontWeight: 700, color: 'var(--text)' }}>◈ 未排期（设个日期就会进今日清单）</p>
                {data.tasks_unscheduled.map((t) => <PlanTaskRow key={t.id} t={t} onToggle={toggleTask} onDate={setTaskDate} />)}
              </>
            )}
            {doneCount > 0 && (
              <>
                <p className="sub" style={{ margin: '14px 0 2px', fontWeight: 700, color: 'var(--text)' }}>◈ 今日已完成</p>
                {data.done_today.map((t) => <PlanTaskRow key={t.id} t={t} onToggle={toggleTask} onDate={setTaskDate} />)}
              </>
            )}
          </>
        ) : (
          <p className="status-ok" style={{ marginTop: 12 }}>
            ✓ 今天没有排期任务。给学习计划里的任务设个截止日期，或主动做一组「到期复习题」。
          </p>
        )}
      </div>
    </div>
  )
}

// 每日一题：ZPD 最优难度推荐，每天一道最值得做的题
function DailyQuestionCard({ sid, onGoto }: { sid: string; onGoto: (t: string, extra?: NavExtra) => void }) {
  const [q, setQ] = useState<{ source: string; point: string; note?: string; p_correct: number | null; quiz_id?: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')  // 失败与「今日无推荐」不可再混为一谈：静默下线让人以为功能时有时无
  const load = () => {
    setLoading(true); setErr('')
    api.dailyQuestion(sid)
      .then((r) => setQ({ source: r.source, point: r.point, note: r.note, p_correct: r.p_correct, quiz_id: r.quiz_id }))
      .catch((e: any) => { setQ(null); setErr(e?.message || '网络错误') })
      .finally(() => setLoading(false))
  }
  useEffect(() => { setQ(null); load() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  if (loading || (!q && !err)) return null
  if (!q && err) {
    return (
      <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--bg)', borderRadius: 10, fontSize: 13, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="badge expert">每日一题</span>
        <span className="sub">获取失败（{err}）</span>
        <div style={{ flex: 1 }} />
        <button className="btn ghost small" onClick={load}>重试</button>
      </div>
    )
  }
  return (
    <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--bg)', borderRadius: 10, fontSize: 13, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
      <span className="badge expert">每日一题</span>
      {q!.point && <b>{q!.point}</b>}
      <span className="sub">{q!.note}</span>
      <div style={{ flex: 1 }} />
      <button className="btn ghost small" onClick={() => onGoto('quiz', q!.quiz_id ? { quizId: q!.quiz_id } : undefined)}>
        去作答<Icon name="arrow" size={12} />
      </button>
    </div>
  )
}

// 讲义级 FSRS 复习：像复习闪卡一样复习整份讲义
function DocReviewSection({ sid, due, err, onRetry, onChanged, onGoto }: {
  sid: string; due: DueDocReview[] | null; err: string; onRetry: () => void
  onChanged: () => void; onGoto: (t: string) => void
}) {
  const { toast } = useUX()
  const gradingId = useRef('')  // 防重入：连点「忘了」会对同一份讲义重复推进 FSRS 间隔
  const grade = async (doc: DueDocReview, rating: number) => {
    if (gradingId.current) return
    gradingId.current = doc.id
    try {
      const r = await api.gradeDocReview(sid, doc.id, rating)
      toast('success', `《${doc.filename}》下次复习：${r.interval_human}`)
      onChanged()
    } catch (e: any) { toast('error', e.message) }
    gradingId.current = ''
  }

  if (!due) return <div className="empty" style={{ margin: 0 }}><span className="spin" /> 加载讲义复习…</div>
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>讲义复习</h3>
        <span className="badge">整份讲义按记忆曲线回顾</span>
        {due.length > 0 && <span className="badge expert">{due.length} 份到期</span>}
        <div style={{ flex: 1 }} />
        <button className="btn ghost small" onClick={() => onGoto('library')}>去资料中心管理</button>
      </div>
      {err ? (
        <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span className="sub" style={{ color: 'var(--red)' }}>⚠ 讲义复习列表加载失败：{err}</span>
          <button className="btn small" onClick={onRetry}>重试</button>
        </div>
      ) : due.length === 0 ? (
        <p className="sub" style={{ marginTop: 10 }}>✓ 暂无到期讲义。上传讲义并复习后，会按记忆曲线安排回顾。</p>
      ) : (
        <div style={{ marginTop: 8 }}>
          {due.map((doc) => (
            <div key={doc.id} style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', padding: '8px 0', borderBottom: '1px solid var(--hairline)' }}>
              <Icon name="book" size={14} />
              <span style={{ fontSize: 13, flex: 1, minWidth: 160 }}>
                <b>{doc.filename}</b>
                <span className="sub">{doc.never_reviewed ? ' · 还没回顾过' : ` · 已复习 ${doc.reps} 次`}</span>
              </span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button className="btn danger small" disabled={!!gradingId.current} onClick={() => grade(doc, 1)}>😰 忘了</button>
                <button className="btn ghost small" disabled={!!gradingId.current} onClick={() => grade(doc, 2)}>😖 困难</button>
                <button className="btn small" disabled={!!gradingId.current} onClick={() => grade(doc, 3)}>🙂 良好</button>
                <button className="btn small" disabled={!!gradingId.current} onClick={() => grade(doc, 4)}>😎 轻松</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
