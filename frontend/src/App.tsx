import { useEffect, useMemo, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { api, chatStream, Book, Citation, DefectDiag, Doc, Flashcard, GraphData, GraphEdge, GraphNode, Handbook, HandbookMeta, LlmStatus, MasteryData, MasteryHistoryPoint, MemoryData, Msg, PlanTask, QuizRecord, Space, SpaceOverview, StudentProfile, SyllabusSchool, TeachResult, TodayData, WrongQ } from './api'
import { downloadMd, Icon, Typing } from './ui'
import { PlannerView } from './Planner'

type Tab = 'profile' | 'library' | 'handbook' | 'planner' | 'chat' | 'docs' | 'quiz' | 'cards' | 'plan' | 'memory' | 'today' | 'settings'

// PDF/模型输出的 \(..\) \[..\] 定界符转成 $..$ / $$..$$，让 remark-math 识别
function normalizeMath(src: string): string {
  return src
    .replace(/\\\((.+?)\\\)/gs, (_, m) => `$${m}$`)
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`)
}

function Md({ children }: { children: string }) {
  return (
    <div className="md">
      <Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizeMath(children)}
      </Markdown>
    </div>
  )
}

function App() {
  const [spaces, setSpaces] = useState<Space[]>([])
  const [sid, setSid] = useState<string>('')
  const [tab, setTab] = useState<Tab>('chat')
  const [health, setHealth] = useState<{ llm: boolean; model: string } | null>(null)
  const [dueCount, setDueCount] = useState(0)

  const refreshSpaces = () => api.listSpaces().then(setSpaces).catch(() => {})
  const refreshHealth = () => api.health().then(setHealth).catch(() => setHealth({ llm: false, model: '未连接' }))
  useEffect(() => {
    refreshSpaces()
    refreshHealth()
    // 先开应用后启动 llama-server 是常见顺序：健康状态定期复查，不再只在启动时查一次
    const t = setInterval(refreshHealth, 60 * 1000)
    const onVis = () => { if (document.visibilityState === 'visible') refreshHealth() }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVis) }
  }, [])

  // 到期复习提醒：切空间/每 5 分钟检查一次，到期数变化时尝试系统通知
  useEffect(() => {
    if (!sid) { setDueCount(0); return }
    let stop = false
    const last = { n: -1 }
    const check = () => api.reviewDue(sid).then((r) => {
      if (stop) return
      setDueCount(r.due.length)
      if (r.due.length > 0 && last.n !== r.due.length && 'Notification' in window
        && Notification.permission === 'granted') {
        try { new Notification('StudyPilot 复习提醒', { body: `有 ${r.due.length} 个知识点到了间隔复习时间` }) } catch { /* 通知失败静默 */ }
      }
      last.n = r.due.length
    }).catch(() => {})
    check()
    const t = setInterval(check, 5 * 60 * 1000)
    return () => { stop = true; clearInterval(t) }
  }, [sid])

  const enableNotifications = async () => {
    if (!('Notification' in window)) { alert('当前环境不支持系统通知'); return }
    const p = await Notification.requestPermission()
    if (p === 'granted') {
      try { new Notification('StudyPilot 复习提醒已开启', { body: '知识点到期时会在这里提醒你' }) } catch { /* 忽略 */ }
    }
  }

  const newSpace = async () => {
    const name = prompt('课程空间名称（如：清华普通物理）')
    if (!name) return
    const s = await api.createSpace(name, '')
    await refreshSpaces()
    setSid(s.id)
  }

  return (
    <>
      <div className="aurora" />
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark"><Icon name="compass" size={17} /></div>
          <div>
            <div className="brand-name">Study<em>Pilot</em></div>
            <div className="brand-sub">本地 AI 助教 · 完全离线运行</div>
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {health && (
          <span className={`chip ${health.llm ? '' : 'off'}`}>
            <span className="pulse" />{health.llm ? health.model : '模型未连接'}
          </span>
        )}
        <span className="chip">Ask · Plan · Craft ｜ 技能 · 专家团 · 连接器 · 项目空间</span>
      </div>

      <div className="layout">
        <div className="sidebar">
          <div className="nav-section">资源</div>
          <div className={`nav-item ${tab === 'profile' ? 'active' : ''}`} onClick={() => setTab('profile')}>
            <Icon name="user" />个人档案
          </div>
          <div className={`nav-item ${tab === 'library' ? 'active' : ''}`} onClick={() => setTab('library')}>
            <Icon name="book" />教材书库
          </div>
          <div className={`nav-item ${tab === 'handbook' ? 'active' : ''}`} onClick={() => setTab('handbook')}>
            <Icon name="compass" />成长手册
          </div>
          <div className={`nav-item ${tab === 'planner' ? 'active' : ''}`} onClick={() => setTab('planner')}>
            <Icon name="plan" />学涯规划
          </div>
          <div className={`nav-item ${tab === 'settings' ? 'active' : ''}`} onClick={() => setTab('settings')}>
            <Icon name="spark" />模型设置
          </div>
          <div className="nav-section">项目空间</div>
          {spaces.map((s) => (
            <div key={s.id} className={`nav-item ${sid === s.id ? 'active' : ''}`}
              onClick={() => { setSid(s.id); setTab('today') }}>
              <Icon name="layers" />{s.name}
            </div>
          ))}
          <button className="side-btn" onClick={newSpace}><Icon name="plus" size={14} /> 新建课程空间</button>

          {sid && (
            <>
              <div className="nav-section">功能</div>
              {([['today', '今日学习', 'sun'], ['chat', '学习对话', 'chat'], ['docs', '知识库', 'book'],
                 ['quiz', '测验', 'quiz'], ['cards', '闪卡', 'cards'], ['plan', '学习计划', 'plan'],
                 ['memory', '记忆图谱', 'brain']] as [Tab, string, string][]).map(([t, label, ic]) => (
                <div key={t} className={`nav-item ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                  <Icon name={ic} />{label}
                  {t === 'today' && dueCount > 0 && <span className="badge expert" style={{ marginLeft: 'auto' }}>{dueCount} 到期</span>}
                </div>
              ))}
              <div className="nav-section">管理</div>
              <button className="btn danger small" style={{ width: '100%', justifyContent: 'center' }}
                onClick={async () => {
                  if (confirm('删除该空间及其全部数据？')) {
                    await api.deleteSpace(sid); setSid(''); refreshSpaces()
                  }
                }}><Icon name="trash" size={13} /> 删除当前空间</button>
            </>
          )}
        </div>

        <div className="main">
          {sid && dueCount > 0 && (
            <div className="card" style={{ margin: '14px 18px 0', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, borderColor: 'var(--orange)' }}>
              <span className="badge expert">⏰ 间隔复习</span>
              <b>{dueCount} 个知识点到了复习时间</b>
              <span className="sub">按 FSRS 记忆曲线，现在复习留存率最高</span>
              <div style={{ flex: 1 }} />
              {'Notification' in window && Notification.permission === 'default' && (
                <button className="btn small" onClick={enableNotifications} title="授权系统通知后，到期提醒可在应用外弹出">
                  🔔 开启系统通知
                </button>
              )}
              <button className="btn small" onClick={() => setTab('today')}>去看今日清单</button>
            </div>
          )}
          {tab === 'profile' ? <ProfileView spaces={spaces} onOpenSpace={(id) => { setSid(id); setTab('chat') }} /> : tab === 'settings' ? <SettingsView /> : tab === 'handbook' ? (
            <HandbookView spaces={spaces} currentSid={sid} />
          ) : tab === 'planner' ? (
            <PlannerView spaces={spaces} onOpenSpace={(id) => { setSid(id); setTab('today') }} />
          ) : tab === 'library' ? (
            <LibraryView spaces={spaces} currentSid={sid} />
          ) : !sid ? (
            <div className="content">
              <div className="hero">
                <div className="hero-badge"><Icon name="spark" size={13} /> WorkBuddy 架构 · DeepPilot 记忆 · 全本地推理</div>
                <h1 className="hero-title">把你的电脑变成<br /><em>一位懂你的私人助教</em></h1>
                <p className="hero-sub">
                  上传讲义，构建私有知识库；答疑带引用、出题判卷、错题沉淀成长期记忆。<br />
                  所有数据与推理都在本机完成，无需联网，不计 token。
                </p>
                <div className="hero-steps">
                  {[
                    ['STEP 1', '建空间', '左侧新建一门课程空间'],
                    ['STEP 2', '传讲义', 'PDF / Markdown 自动向量化入库'],
                    ['STEP 3', '对话练习', '答疑 · 出题 · 判卷 · 总结'],
                    ['STEP 4', '记忆生长', '错题薄弱点进入长期记忆档案'],
                  ].map(([no, t, d]) => (
                    <div key={no} className="hero-step">
                      <span className="no">{no}</span><b>{t}</b><span>{d}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : tab === 'today' ? <TodayView sid={sid} onGoto={setTab} /> : tab === 'chat' ? <ChatView sid={sid} /> : tab === 'docs' ? <DocsView sid={sid} /> : tab === 'quiz' ? <QuizView sid={sid} /> : tab === 'cards' ? <CardsView sid={sid} /> : tab === 'plan' ? <PlanView sid={sid} /> : <MemoryView sid={sid} onGoto={setTab} />}
        </div>
      </div>
    </>
  )
}

function TodayView({ sid, onGoto }: { sid: string; onGoto: (t: Tab) => void }) {
  const [data, setData] = useState<TodayData | null>(null)
  const [busy, setBusy] = useState(false)
  const refresh = () => api.today(sid).then(setData).catch(() => {})
  useEffect(() => { setData(null); refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleTask = async (t: PlanTask) => {
    try { await api.togglePlanTask(sid, t.id, !t.done) } catch { /* 打卡失败不打断 */ }
    refresh()
  }
  const setTaskDate = async (t: PlanTask, date: string) => {
    try { await api.setTaskDate(sid, t.id, date) } catch (e: any) { alert(e.message) }
    refresh()
  }
  const makeReview = async () => {
    setBusy(true)
    try {
      await api.runSkill(sid, 'review.generate', { count: 5 })
      alert('已按到期薄弱点生成复习测验，答对会自动推进复习间隔')
      onGoto('quiz')
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  if (!data) return <div className="content"><div className="empty"><span className="spin" /> 加载中…</div></div>
  const d = new Date(data.date + 'T00:00:00')
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  const today = data.date
  const doneCount = data.done_today.length
  const openCount = data.tasks_today.length
  const totalToday = openCount + doneCount
  const pct = totalToday ? Math.round((doneCount / totalToday) * 100) : 0

  const taskRow = (t: PlanTask, overdue = false) => (
    <div key={t.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '9px 0', borderBottom: '1px solid var(--hairline)' }}>
      <input type="checkbox" checked={!!t.done} onChange={() => toggleTask(t)} style={{ marginTop: 4 }} />
      <div style={{ flex: 1, fontSize: 13 }}>
        <div>{t.content}</div>
        {t.accept && <div style={{ color: 'var(--muted)', marginTop: 3 }}>验收：{t.accept}</div>}
        {t.points.length > 0 && (
          <div style={{ marginTop: 4 }}>{t.points.map((p, i) => <span key={i} className="badge" style={{ margin: 1 }}>{p}</span>)}</div>
        )}
      </div>
      {overdue && !t.done && (
        <span className="badge expert" style={{ color: 'var(--red)', borderColor: 'rgba(238,154,169,.4)', flex: 'none' }}>逾期</span>
      )}
      <input type="date" style={{ maxWidth: 148, flex: 'none' }} value={t.due_date || ''} title="调整截止日期"
        onChange={(e) => setTaskDate(t, e.target.value)} />
    </div>
  )

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>今日学习 · {d.getMonth() + 1} 月 {d.getDate()} 日 周{week}</h3>
          <span className="sub">到期复习、闪卡与计划任务都汇总在这里，做完即走</span>
          <div style={{ flex: 1 }} />
          <button className="btn small" disabled={busy} onClick={makeReview}>
            <Icon name="quiz" size={12} /> 生成到期复习题
          </button>
        </div>
        <div className="today-grid" style={{ marginTop: 14 }}>
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('memory')}>
            <span className="sub">到期复习</span>
            <b className="num" style={{ color: data.due_total ? 'var(--orange)' : 'var(--green)' }}>{data.due_total}</b>
            <span className="sub">个知识点 · 记忆图谱</span>
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
          <div className="today-tile" style={{ cursor: 'pointer' }} onClick={() => onGoto('quiz')}>
            <span className="sub">错题</span>
            <b className="num" style={{ color: data.wrong_count ? 'var(--red)' : 'var(--green)' }}>{data.wrong_count}</b>
            <span className="sub">可变式训练 · 测验页</span>
          </div>
        </div>
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
              {data.tasks_today.map((t) => taskRow(t, t.due_date < today))}
            </div>
            {data.tasks_unscheduled.length > 0 && (
              <>
                <p className="sub" style={{ margin: '14px 0 2px', fontWeight: 700, color: 'var(--text)' }}>◈ 未排期（设个日期就会进今日清单）</p>
                {data.tasks_unscheduled.map((t) => taskRow(t))}
              </>
            )}
            {doneCount > 0 && (
              <>
                <p className="sub" style={{ margin: '14px 0 2px', fontWeight: 700, color: 'var(--text)' }}>◈ 今日已完成</p>
                {data.done_today.map((t) => taskRow(t))}
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

function ChatView({ sid }: { sid: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [mode, setMode] = useState('ask')
  const [guide, setGuide] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [fbGiven, setFbGiven] = useState<Record<string, string>>({})
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => { api.listMessages(sid).then(setMsgs).catch(() => {}) }, [sid])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, note])

  const send = () => {
    const text = input.trim()
    if (!text || busy) return
    setInput(''); setNote(''); setBusy(true)
    setMsgs((m) => [...m, { role: 'user', mode, content: text }, { role: 'assistant', mode, content: '' }])
    const fail = (msg: string) => {
      setBusy(false)
      setMsgs((m) => {
        const copy = [...m]
        // 失败时移除空的助手占位气泡，保留用户提问（服务端已先落库）
        if (copy.length && copy[copy.length - 1].role === 'assistant' && !copy[copy.length - 1].content) copy.pop()
        return copy
      })
      alert(msg)
    }
    chatStream(sid, mode, text,
      (t) => setMsgs((m) => {
        const copy = [...m]; copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + t }
        return copy
      }),
      ({ expert, citations, assistant_message_id }) => {
        setBusy(false)
        setMsgs((m) => {
          const copy = [...m]; copy[copy.length - 1] = { ...copy[copy.length - 1], expert, citations, id: assistant_message_id }
          return copy
        })
      },
      guide,
      fail,
    )
  }

  const give = async (mid: string, rating: string, understood: number) => {
    let confusion = ''
    if (understood === 0) {
      confusion = prompt('哪里没懂？描述一下可以帮助教更准地记住薄弱点（可留空）') || ''
    }
    try {
      await api.sendFeedback(sid, mid, rating, understood, confusion)
      setFbGiven((f) => ({ ...f, [mid]: understood === 1 ? 'helpful' : 'unhelpful' }))
    } catch (e: any) {
      // 提交失败必须让用户知道：负反馈驱动掌握度更新，静默丢反馈=数据丢失
      alert('反馈提交失败：' + (e.message || '未知错误'))
    }
  }

  const makeNote = async () => {
    const docs = await api.listDocs(sid)
    const ready = docs.filter((d) => d.status === 'ready')
    if (!ready.length) { alert('请先在知识库中上传并索引讲义'); return }
    const names = ready.map((d, i) => `${i + 1}. ${d.filename}`).join('\n')
    const idx = Number(prompt(`选择要总结的讲义编号：\n${names}`, '1'))
    const doc = ready[idx - 1]
    if (!doc) return
    setBusy(true); setNote('正在生成总结…')
    try {
      const r = await api.runSkill(sid, 'note.summarize', { document_id: doc.id })
      setNote(r.note)
    } catch (e: any) { setNote('失败：' + e.message) }
    setBusy(false)
  }

  return (
    <>
      <div className="content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div className="mode-tabs">
            {[['ask', 'Ask 答疑'], ['plan', 'Plan 规划'], ['craft', 'Craft 产出']].map(([m, l]) => (
              <button key={m} className={`mode-tab ${mode === m ? 'active' : ''}`} onClick={() => setMode(m)}>{l}</button>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          {mode === 'ask' && (
            <button className={`fb-btn ${guide ? 'fb-on' : ''}`} style={{ padding: '6px 14px' }}
              title="苏格拉底式引导：助教先确认卡点、逐层提示思路，不直接给答案"
              onClick={() => setGuide((g) => !g)}>
              💡 引导模式 {guide ? '已开启' : '已关闭'}
            </button>
          )}
          <button className="btn ghost small" disabled={busy} onClick={makeNote}><Icon name="spark" size={13} /> 讲义总结技能</button>
        </div>

        {msgs.map((m, i) => {
          const typing = busy && i === msgs.length - 1 && m.role === 'assistant' && !m.content
          return (
            <div key={i} className={`msg ${m.role}`}>
              <div className="who">
                <span className={`avatar ${m.role === 'user' ? 'user' : 'ai'}`}>
                  {m.role === 'user' ? <Icon name="user" size={13} /> : <Icon name="compass" size={13} />}
                </span>
                {m.role === 'user' ? '我' : (
                  <>
                    <span>{m.expert || '助教'}</span>
                    <span className="badge expert">专家团</span>
                    <span className="badge">{m.mode.toUpperCase()}</span>
                  </>
                )}
              </div>
              <div className="bubble">
                {typing ? <Typing /> : m.role === 'assistant' ? <Md>{m.content}</Md> : m.content}
              </div>
              {m.citations && m.citations.length > 0 && (
                <div className="citations">
                  {m.citations.map((c: Citation) => (
                    <span key={c.index} className="citation" title={c.snippet}>
                      <Icon name="book" size={10} /> [{c.index}] {c.source} · {c.score}
                    </span>
                  ))}
                </div>
              )}
              {m.role === 'assistant' && m.id && !typing && (
                <div className="fb-row">
                  {fbGiven[m.id] ? (
                    <span className="fb-done">反馈已记录，教记住了 ✓</span>
                  ) : (
                    <>
                      <button className="fb-btn" onClick={() => give(m.id!, 'helpful', 1)}>👍 懂了</button>
                      <button className="fb-btn" onClick={() => give(m.id!, 'unhelpful', 0)}>✗ 没听懂</button>
                    </>
                  )}
                </div>
              )}
            </div>
          )
        })}
        {note && (
          <div className="msg assistant">
            <div className="who">
              <span className="avatar ai"><Icon name="spark" size={13} /></span>
              <span>讲义总结</span><span className="badge">CRAFT</span>
            </div>
            <div className="bubble"><Md>{note}</Md></div>
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="chat-footer">
        <div className="input-shell">
          <textarea value={input}
            placeholder={guide
              ? '向助教提问…（引导模式：会先提示思路，而不是直接给答案）'
              : '向助教提问…（包含「出题」「计划」等关键词会自动路由到对应专家）'}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <button className="send-btn" disabled={busy} onClick={send}><Icon name="send" /></button>
        </div>
      </div>
    </>
  )
}

// 间隔秒数 → 人话（FSRS 刷卡按钮的间隔预告用）
function fmtInterval(sec?: number): string {
  if (!sec || sec <= 0) return ''
  const m = sec / 60
  if (m < 60) return `${Math.max(1, Math.round(m))}分钟`
  const h = m / 60
  if (h < 24) return `${Math.round(h)}小时`
  const d = h / 24
  if (d < 31) return `${Math.round(d)}天`
  if (d < 365) return `${(d / 30.4).toFixed(1)}个月`
  return `${(d / 365).toFixed(1)}年`
}

function CardsView({ sid }: { sid: string }) {
  const [cards, setCards] = useState<Flashcard[]>([])
  const [stats, setStats] = useState<{ total: number; due: number }>({ total: 0, due: 0 })
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [cur, setCur] = useState<Flashcard | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // 复习流只取到期卡；新卡 due_at=入库时刻，天然立即到期
  const refresh = () => Promise.all([
    api.flashcards(sid, true), api.flashcards(sid),
  ]).then(([dueRes, all]) => {
    setCards(dueRes.cards); setStats(all.stats)
    setCur(dueRes.cards[0] || null); setRevealed(false)
  }).catch(() => alert('闪卡加载失败，请检查服务是否正常'))
    .finally(() => setLoaded(true))
  useEffect(() => { refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async () => {
    setBusy(true)
    try {
      const made = await api.runSkill(sid, 'flashcard.generate', { topic, count: 10 })
      alert(`已生成 ${made.length} 张闪卡`)
      await refresh()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const clearAll = async () => {
    if (!stats.total) return
    if (!confirm(`清空全部 ${stats.total} 张闪卡？此操作不可恢复。`)) return
    try {
      await api.clearFlashcards(sid)
      await refresh()
    } catch (e: any) { alert('清空失败：' + (e.message || '未知错误')) }
  }

  const grade = async (rating: number) => {
    if (!cur) return
    try { await api.gradeFlashcard(sid, cur.id, rating) } catch { /* 单卡评分失败不阻塞 */ }
    refresh()
  }

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>闪卡 · 间隔记忆</h3>
        <p className="sub">
          从讲义生成问答卡，按 FSRS 记忆算法调度间隔（目标记住率 90%，随你的评分历史自适应）：
          新卡先经分钟级学习步进，答对毕业进入天级间隔，答错很快重现。
          不填主题时自动优先覆盖薄弱知识点。
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <input type="text" placeholder="主题（留空=优先薄弱知识点）" value={topic} onChange={(e) => setTopic(e.target.value)} />
          <button className="btn" disabled={busy} onClick={generate} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> 生成中</> : <><Icon name="cards" size={14} /> 生成 10 张闪卡</>}
          </button>
          <span className="badge">共 {stats.total} 张</span>
          <span className={`badge ${stats.due > 0 ? 'expert' : ''}`}>待复习 {stats.due}</span>
          {stats.total > 0 && (
            <button className="btn danger small" onClick={clearAll} style={{ flex: 'none' }}>
              <Icon name="trash" size={12} /> 清空闪卡
            </button>
          )}
        </div>
      </div>

      {cur ? (
        <div className="card" style={{ textAlign: 'center', padding: '36px 24px' }}>
          <span className="badge">{cur.point || '知识点'}</span>
          <div style={{ fontSize: 19, margin: '22px 0', minHeight: 60, display: 'grid', alignItems: 'center' }}>
            <b>{cur.front}</b>
          </div>
          {revealed ? (
            <>
              <div className="md" style={{ fontSize: 15, margin: '0 auto 22px', maxWidth: 560, color: 'var(--green)' }}><Md>{cur.back}</Md></div>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button className="btn danger small" onClick={() => grade(1)}>😰 忘了 · {fmtInterval(cur.preview?.['1'])}</button>
                <button className="btn ghost small" onClick={() => grade(2)}>😖 困难 · {fmtInterval(cur.preview?.['2'])}</button>
                <button className="btn small" onClick={() => grade(3)}>🙂 良好 · {fmtInterval(cur.preview?.['3'])}</button>
                <button className="btn small" onClick={() => grade(4)}>😎 轻松 · {fmtInterval(cur.preview?.['4'])}</button>
              </div>
            </>
          ) : (
            <button className="btn" onClick={() => setRevealed(true)}>
              <Icon name="spark" size={14} /> 显示答案
            </button>
          )}
          <p className="sub" style={{ marginTop: 18 }}>本批还剩 {cards.length - 1} 张</p>
        </div>
      ) : loaded && (
        <div className="empty" style={{ padding: 30 }}>
          {stats.total ? '当前没有到期待复习的卡片 ✓' : '还没有闪卡——用上方按钮从讲义生成'}
        </div>
      )}
    </div>
  )
}

function PlanView({ sid }: { sid: string }) {
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
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const toggle = async (t: PlanTask) => {
    try {
      await api.togglePlanTask(sid, t.id, !t.done)
    } catch (e: any) { alert('打卡失败：' + (e.message || '未知错误')) }
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
        <p className="sub">规划师结合你的薄弱点档案，把目标拆成分阶段任务；完成打卡，重新生成会整体替换当前计划。</p>
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
          {plan.tasks.map((t) => {
            const showPhase = t.phase !== phase
            phase = t.phase
            return (
              <div key={t.id}>
                {showPhase && <p className="sub" style={{ margin: '16px 0 6px', fontWeight: 700, color: 'var(--text)' }}>◈ {t.phase || '任务'}</p>}
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '7px 0', borderBottom: '1px solid var(--hairline)' }}>
                  <input type="checkbox" checked={!!t.done} onChange={() => toggle(t)} style={{ marginTop: 4 }} />
                  <div style={{ fontSize: 13 }}>
                    <div style={{ textDecoration: t.done ? 'line-through' : 'none', color: t.done ? 'var(--muted)' : 'var(--text)' }}>
                      {t.content}
                    </div>
                    {t.accept && <div style={{ color: 'var(--muted)', marginTop: 3 }}>验收：{t.accept}</div>}
                    {t.due_date && <div style={{ marginTop: 4 }}><span className="badge expert">⏱ {t.due_date} 前完成</span></div>}
                    {t.points.length > 0 && (
                      <div style={{ marginTop: 4 }}>{t.points.map((p, i) => <span key={i} className="badge" style={{ margin: 1 }}>{p}</span>)}</div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function DocsView({ sid }: { sid: string }) {
  const [docs, setDocs] = useState<Doc[]>([])
  const [busy, setBusy] = useState(false)
  const refresh = () => api.listDocs(sid).then(setDocs).catch(() => setDocs([]))
  useEffect(() => { refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    const errors: string[] = []
    let ok = 0
    for (const f of Array.from(files)) {
      try {
        const r: any = await api.uploadDoc(sid, f)
        if (r.batch) {
          const bad = r.batch.filter((b: any) => b.status === 'error')
          ok += r.batch.length - bad.length
          bad.forEach((b: any) => errors.push(`${b.filename}: ${b.error}`))
        } else ok++
      } catch (e: any) { errors.push(`${f.name}: ${e.message}`) }
    }
    await refresh(); setBusy(false)
    if (errors.length) alert(`导入完成：成功 ${ok} 个\n失败：\n${errors.join('\n')}`)
  }

  const removeDoc = async (d: Doc) => {
    if (!confirm(`删除文档《${d.filename}》？\n向量与其上传文件会一并清理；若是挂载的教材，将解除该空间的挂载（书库条目保留）。`)) return
    try {
      await api.deleteDoc(sid, d.id)
      refresh()
    } catch (e: any) { alert('删除失败：' + (e.message || '未知错误')) }
  }

  return (
    <div className="content">
      <div className="card">
        <h3>知识库</h3>
        <p className="sub">
          RAG 管线：解析 → 语义分块 → BGE 向量化 → 检索引用。支持 PDF / PPTX 课件（含讲者备注）/
          TXT / Markdown / 图片（离线 OCR 提取文字）/ zip 压缩包（自动展开导入其中全部可识别文件，
          跳过嵌套压缩包）。
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '16px 0 4px' }}>
          <label className="btn" style={{ cursor: 'pointer' }}>
            <Icon name="plus" size={14} /> 选择讲义文件
            <input type="file" multiple accept=".pdf,.pptx,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp,.zip" style={{ display: 'none' }}
              onChange={(e) => upload(e.target.files)} disabled={busy} />
          </label>
          {busy && <span className="sub"><span className="spin" /> 正在解析并向量化…（首次运行会下载嵌入模型）</span>}
        </div>
        <table className="quiz" style={{ marginTop: 12 }}>
          <thead><tr><th>文件</th><th>状态</th><th>分块</th><th>错误</th><th></th></tr></thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td>{d.status === 'ready' ? <span className="status-ok">✓ 已索引</span> : d.status === 'error' ? <span className="status-err">✗ 失败</span> : <span className="status-wait"><span className="spin" /> 处理中</span>}</td>
                <td>{d.chunks}</td>
                <td style={{ color: 'var(--red)' }}>{d.error}</td>
                <td>
                  <button className="btn danger small" onClick={() => removeDoc(d)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function QuizView({ sid }: { sid: string }) {
  const [quizzes, setQuizzes] = useState<QuizRecord[]>([])
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [userAnswers, setUserAnswers] = useState<Record<string, Record<string, string>>>({})
  const [sub, setSub] = useState<'practice' | 'wrong' | 'teach'>('practice')
  const [now, setNow] = useState(Date.now())
  const refresh = () => api.quizzes(sid).then(setQuizzes)
  useEffect(() => { refresh(); setSub('practice') }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  const examLive = quizzes.filter((q) => q.topic === '模拟考试' && !q.answers.length)
  // 限时起点/时长持久化到 localStorage：切页/刷新不再重置倒计时；时间到自动交卷
  useEffect(() => {
    examLive.forEach((q) => {
      if (!localStorage.getItem(`exam_start_${q.id}`)) {
        localStorage.setItem(`exam_start_${q.id}`, String(Date.now()))
      }
    })
    if (!examLive.length) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [quizzes]) // eslint-disable-line react-hooks/exhaustive-deps

  const examMinutes = (quizId: string) => Number(localStorage.getItem(`exam_minutes_${quizId}`)) || 30

  const generate = async (skill: string, params: object) => {
    setBusy(true)
    try {
      const r: any = await api.runSkill(sid, skill, params)
      // 记下本场考试的限时，供倒计时与自动交卷使用（后端 exam_minutes 字段此前被忽略）
      const made = Array.isArray(r) ? r[0] : r
      if (skill === 'exam.mock' && made?.quiz_id) {
        localStorage.setItem(`exam_minutes_${made.quiz_id}`, String(made.exam_minutes || 30))
      }
      await refresh(); setSub('practice')
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const submit = async (quiz: QuizRecord) => {
    const answers = quiz.questions.map((q) => ({ qid: q.id, answer: userAnswers[quiz.id]?.[q.id] ?? '' }))
    setBusy(true)
    try {
      await api.runSkill(sid, 'quiz.grade', { quiz_id: quiz.id, answers })
      localStorage.removeItem(`exam_start_${quiz.id}`)
      localStorage.removeItem(`exam_minutes_${quiz.id}`)
      await refresh()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const examRemaining = (quiz: QuizRecord) => {
    const start = Number(localStorage.getItem(`exam_start_${quiz.id}`)) || Date.now()
    return examMinutes(quiz.id) * 60 - Math.floor((now - start) / 1000)
  }

  // 到时自动交卷（此前只提示不禁用，可以无限续时作答）
  useEffect(() => {
    if (busy) return
    for (const q of examLive) {
      if (examRemaining(q) <= 0) {
        const quiz = quizzes.find((x) => x.id === q.id)
        if (quiz) { submit(quiz); break }
      }
    }
  }, [now]) // eslint-disable-line react-hooks/exhaustive-deps

  // 已判卷测验的知识点小结：每点对几题
  const pointSummary = (quiz: QuizRecord) => {
    const byQid: Record<string, any> = {}
    quiz.answers.forEach((a) => { byQid[a.qid] = a })
    const acc: Record<string, { good: number; total: number }> = {}
    quiz.questions.forEach((q) => {
      const p = q.knowledge_point || '未标注'
      acc[p] = acc[p] || { good: 0, total: 0 }
      acc[p].total++
      if (byQid[q.id]?.verdict === '对') acc[p].good++
    })
    return acc
  }

  return (
    <div className="content">
      <div className="mode-tabs" style={{ marginBottom: 16 }}>
        <button className={`mode-tab ${sub === 'practice' ? 'active' : ''}`} onClick={() => setSub('practice')}>练习 · 模拟考</button>
        <button className={`mode-tab ${sub === 'wrong' ? 'active' : ''}`} onClick={() => setSub('wrong')}>错题本</button>
        <button className={`mode-tab ${sub === 'teach' ? 'active' : ''}`} onClick={() => setSub('teach')}>费曼讲解检验</button>
      </div>

      {sub === 'practice' && (
        <>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>出题测验</h3>
            <p className="sub">出题官依据讲义出题 → 判卷助教逐题分析 → 错题自动写入 L3 长期记忆与错题本。</p>
            <div style={{ display: 'flex', gap: 12, marginTop: 14, flexWrap: 'wrap' }}>
              <input type="text" placeholder="主题（如：高斯定理），留空覆盖全课程"
                value={topic} onChange={(e) => setTopic(e.target.value)} />
              <button className="btn" disabled={busy} onClick={() => generate('quiz.generate', { topic, count: 5 })} style={{ flex: 'none' }}>
                {busy ? <><span className="spin" /> 生成中</> : <><Icon name="quiz" size={14} /> 生成 5 道题</>}
              </button>
              <button className="btn ghost" disabled={busy} onClick={() => generate('exam.mock', { count: 10, minutes: 30 })} style={{ flex: 'none' }}>
                <Icon name="plan" size={14} /> 模拟考试（10 题 · 限时 30 分钟）
              </button>
            </div>
          </div>
          {quizzes.map((quiz) => {
            const graded = quiz.answers.length > 0
            const byQid: Record<string, any> = {}
            quiz.answers.forEach((a) => { byQid[a.qid] = a })
            const isExam = quiz.topic === '模拟考试'
            const remain = isExam && !graded ? examRemaining(quiz) : 0
            const summary = graded ? pointSummary(quiz) : {}
            return (
              <div key={quiz.id} className="card" style={{ marginBottom: 18 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <b>{isExam ? '📘 模拟考试' : `测验：${quiz.topic || '综合'}`}</b>
                  {isExam && !graded && (
                    <span className={`badge ${remain <= 60 ? 'expert' : ''}`}
                      style={remain <= 0 ? { color: 'var(--red)' } : {}}>
                      {remain > 0 ? `剩余 ${String(Math.floor(remain / 60)).padStart(2, '0')}:${String(remain % 60).padStart(2, '0')}` : '⏰ 时间到，请交卷'}
                    </span>
                  )}
                  {graded && <span className="badge expert">得分 {quiz.answers.filter((a) => a.verdict === '对').length}/{quiz.questions.length}</span>}
                </div>
                {graded && Object.keys(summary).length > 1 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0 10px' }}>
                    {Object.entries(summary).map(([p, v]: any) => (
                      <span key={p} className="badge" title={`共 ${v.total} 题`}>
                        {p} {v.good}/{v.total}{v.good < v.total ? ' ⚠' : ' ✓'}
                      </span>
                    ))}
                  </div>
                )}
                <table className="quiz">
                  <tbody>
                    {quiz.questions.map((q, i) => (
                      <tr key={q.id}>
                        <td style={{ width: 36, color: 'var(--faint)' }}>{i + 1}</td>
                        <td>
                          <div><span className="badge">{q.type}</span> <b>{q.question}</b></div>
                          {q.options.length > 0 && (
                            <div style={{ color: 'var(--muted)', margin: '7px 0' }}>{q.options.join('　')}</div>
                          )}
                          {!graded ? (
                            <input type="text" style={{ maxWidth: 420 }} placeholder="输入你的答案"
                              value={userAnswers[quiz.id]?.[q.id] ?? ''}
                              onChange={(e) => setUserAnswers((u) => ({
                                ...u, [quiz.id]: { ...u[quiz.id], [q.id]: e.target.value },
                              }))} />
                          ) : (
                            <div style={{ fontSize: 13, marginTop: 7, display: 'grid', gap: 4 }}>
                              <span>
                                判定：<span className={`verdict-${byQid[q.id]?.verdict ?? ''}`}>{byQid[q.id]?.verdict}</span>
                                　<span style={{ color: 'var(--muted)' }}>参考答案：{q.answer}</span>
                              </span>
                              <span style={{ color: 'var(--muted)' }}>知识点：{q.knowledge_point}</span>
                              <span style={{ color: 'var(--orange)' }}>◎ {byQid[q.id]?.analysis}</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!graded && <button className="btn" style={{ marginTop: 14 }} disabled={busy} onClick={() => submit(quiz)}>交卷判分</button>}
              </div>
            )
          })}
        </>
      )}

      {sub === 'wrong' && <WrongBook sid={sid} onRedone={() => { refresh(); setSub('practice') }} />}
      {sub === 'teach' && <TeachView sid={sid} />}
    </div>
  )
}

function WrongBook({ sid, onRedone }: { sid: string; onRedone: () => void }) {
  const [items, setItems] = useState<WrongQ[]>([])
  const [picked, setPicked] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => { api.wrongQuestions(sid).then((r) => { setItems(r); setLoaded(true) }).catch(() => setLoaded(true)) }, [sid])

  const redo = async (qids?: string[]) => {
    setBusy(true)
    try {
      const r = await api.redoWrong(sid, qids || [])
      alert(`已按 ${r.redo_count} 道错题重组测验，请到「练习」页作答`)
      onRedone()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const variants = async (qids?: string[]) => {
    setBusy(true)
    try {
      const r: any = await api.runSkill(sid, 'wrong.variants', { qids: qids || [] })
      // 该技能返回数组（每卷一项），取第一项读 variant_count
      const made = Array.isArray(r) ? r[0] : r
      alert(`已生成 ${made?.variant_count ?? '?'} 道变式题（同知识点换数字/换情境/换问法），请到「练习」页作答`)
      onRedone()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const exportWrong = async () => downloadMd('wrong', await api.exportMd(sid, 'wrong'))

  let group = ''
  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>错题本</h3>
        <p className="sub">跨测验聚合全部错题；重做答对自动推进间隔复习进度；变式训练换角度再考一次，检验真理解而非背答案。</p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <button className="btn" disabled={busy || !items.length} onClick={() => redo()}>
            <Icon name="quiz" size={13} /> 重做全部错题（{items.length}）
          </button>
          <button className="btn ghost" disabled={busy || !items.some((i) => picked[i.id])}
            onClick={() => redo(items.filter((i) => picked[i.id]).map((i) => i.id))}>
            重做选中
          </button>
          <button className="btn ghost" disabled={busy || !items.length}
            onClick={() => variants(items.some((i) => picked[i.id])
              ? items.filter((i) => picked[i.id]).map((i) => i.id)
              : undefined)}>
            <Icon name="spark" size={13} /> 变式训练{items.some((i) => picked[i.id])
              ? `（选中 ${items.filter((i) => picked[i.id]).length}）` : '（防背答案）'}
          </button>
          <button className="btn ghost" disabled={!items.length} onClick={exportWrong}>
            <Icon name="book" size={13} /> 导出错题本
          </button>
        </div>
      </div>
      {items.map((q) => {
        const showTopic = q.quiz_topic !== group
        group = q.quiz_topic
        return (
          <div key={q.id}>
            {showTopic && <p className="sub" style={{ margin: '14px 0 6px' }}>来自：{q.quiz_topic || '综合练习'}</p>}
            <div className="card" style={{ marginBottom: 10, padding: '12px 16px' }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <input type="checkbox" checked={!!picked[q.id]}
                  onChange={(e) => setPicked((p) => ({ ...p, [q.id]: e.target.checked }))} style={{ marginTop: 4 }} />
                <div style={{ fontSize: 13, display: 'grid', gap: 4 }}>
                  <span><span className="badge">{q.type}</span> <b>{q.question}</b></span>
                  <span>我的答案：<span style={{ color: 'var(--red)' }}>{q.user_answer || '（未记录）'}</span>
                  　参考答案：<span style={{ color: 'var(--green)' }}>{q.answer}</span></span>
                  <span style={{ color: 'var(--orange)' }}>◎ {q.analysis}</span>
                  <span style={{ color: 'var(--muted)' }}>知识点：{q.knowledge_point}</span>
                </div>
              </div>
            </div>
          </div>
        )
      })}
      {loaded && !items.length && <div className="empty" style={{ padding: 30 }}>没有错题——去「练习」页生成一次测验吧</div>}
    </>
  )
}

function TeachView({ sid }: { sid: string }) {
  const [topic, setTopic] = useState('')
  const [explanation, setExplanation] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<TeachResult | null>(null)

  const check = async () => {
    if (!topic.trim() || !explanation.trim()) { alert('请填写概念主题和你的讲解'); return }
    setBusy(true); setResult(null)
    try { setResult(await api.runSkill(sid, 'teach.check', { topic, explanation })) } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const vColor = result?.verdict === '准确' ? 'var(--green)' : result?.verdict === '基本正确' ? 'var(--orange)' : 'var(--red)'
  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>费曼讲解检验</h3>
        <p className="sub">用自己的话讲一遍概念——能讲清楚才是真的懂。助教会对照讲义评估准确性、遗漏与误解，并更新掌握度。</p>
        <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
          <input type="text" placeholder="概念主题（如：高斯定理）" value={topic} onChange={(e) => setTopic(e.target.value)} />
          <textarea placeholder="用你自己的话讲解这个概念，假设听的人是完全不懂的外行…"
            style={{ minHeight: 120 }} value={explanation} onChange={(e) => setExplanation(e.target.value)} />
          <button className="btn" disabled={busy} onClick={check} style={{ justifySelf: 'start' }}>
            {busy ? <><span className="spin" /> 判定中</> : <><Icon name="spark" size={14} /> 提交讲解</>}
          </button>
        </div>
      </div>
      {result && (
        <div className="card">
          <h3>检验结果：<span style={{ color: vColor }}>{result.verdict}</span></h3>
          {result.missed?.length > 0 && (
            <p style={{ marginTop: 8 }}><b>遗漏的关键点：</b>{result.missed.map((m, i) => <span key={i} className="badge" style={{ margin: 2 }}>{m}</span>)}</p>
          )}
          {result.wrong?.length > 0 && (
            <p><b>理解错误：</b>{result.wrong.map((m, i) => <span key={i} className="badge expert" style={{ margin: 2 }}>{m}</span>)}</p>
          )}
          <p style={{ marginTop: 8, color: 'var(--orange)' }}>◎ {result.analysis}</p>
          <p className="sub">已按结果更新知识点「{result.knowledge_point}」的掌握度</p>
        </div>
      )}
    </>
  )
}

function DefectPanel({ sid }: { sid: string }) {
  const [diag, setDiag] = useState<DefectDiag | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState('')
  const load = () => api.defects(sid).then(setDiag).catch(() => {})
  useEffect(() => { setDiag(null); load() }, [sid])

  const buildGraph = async () => {
    setBusy(true)
    try {
      const r = await api.runSkill(sid, 'graph.build', {})
      alert(`知识图谱已构建：${r.total} 条依赖边（讲义抽取 ${r.llm_edges} + 内置课程图谱匹配 ${r.curriculum_edges}）`)
      await load()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  if (!diag) return <div className="card" style={{ marginBottom: 18 }}><span className="spin" /> 缺陷诊断计算中…</div>
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>知识缺陷诊断</h3>
        <span className="badge expert">缺陷 {diag.points.length} 处</span>
        {diag.has_graph
          ? <span className="badge">依赖图 {diag.edge_count} 边</span>
          : <span className="badge">未建依赖图</span>}
        <div style={{ flex: 1 }} />
        <button className="btn small" disabled={busy} onClick={buildGraph}>
          <Icon name="brain" size={12} /> {diag.has_graph ? '重建知识图谱' : '构建知识图谱'}
        </button>
      </div>
      <p className="sub">
        掌握度由贝叶斯知识追踪（BKT）随每次测验/反馈更新，叠加遗忘曲线估算"此刻留存"，
        再沿知识点依赖图把前置缺陷向下游传播——排序按综合风险，而非只看单点得分。
        {!diag.has_graph && ' 构建依赖图后可发现"前置拖累"与根因链。'}
      </p>

      {diag.repair_order.length > 1 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', margin: '10px 0 4px' }}>
          <b style={{ fontSize: 13 }}>建议修复顺序</b>
          {diag.repair_order.map((p, i) => (
            <span key={p} className="badge expert">{i + 1}. {p}</span>
          ))}
          <span className="sub">（先补根因，再回到被拖累的后继）</span>
        </div>
      )}
      {diag.chains.map((chain, i) => (
        <p key={i} className="sub" style={{ margin: '4px 0' }}>⛓ 根因链：{chain.join(' → ')}</p>
      ))}

      <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
        {diag.points.map((d, i) => {
          const pct = (v: number) => `${Math.round(v * 100)}%`
          const ets = Object.entries(d.evidence.error_types)
          const mainErr = ets.sort((a, b) => b[1] - a[1])[0]
          return (
            <div key={d.point} style={{ border: '1px solid var(--hairline)', borderRadius: 12, padding: '10px 14px' }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="badge expert">#{i + 1}</span>
                <b style={{ fontSize: 14 }}>{d.point}</b>
                <div className="mastery-track" style={{ minWidth: 120 }} title={`综合风险 ${pct(d.risk)}`}>
                  <div className="mastery-fill weak" style={{ width: pct(d.risk) }} />
                  <span className="mastery-label">风险 {pct(d.risk)}</span>
                </div>
                <span className="sub">掌握 {pct(d.p_known)} · 此刻留存 {pct(d.retention)}</span>
                {d.inherited_risk > 0.2 && <span className="badge expert">前置拖累 {pct(d.inherited_risk)}</span>}
                {d.evidence.wrong > 0 && <span className="badge">错 {d.evidence.wrong}/对 {d.evidence.correct}</span>}
                {mainErr && <span className="badge expert">主要错因：{mainErr[0]} ×{mainErr[1]}</span>}
                {d.downstream.length > 0 && <span className="badge">下游 {d.downstream.length} 个受累</span>}
                <div style={{ flex: 1 }} />
                {open === d.point
                  ? <button className="btn ghost small" onClick={() => setOpen('')}>收起</button>
                  : <button className="btn ghost small" onClick={() => setOpen(d.point)}>证据</button>}
              </div>
              {d.note && <p className="sub" style={{ margin: '6px 0 0', color: 'var(--orange)' }}>◎ {d.note}</p>}
              {open === d.point && (
                <div style={{ fontSize: 13, marginTop: 8, display: 'grid', gap: 5 }}>
                  {d.prereqs.length > 0 && (
                    <span>薄弱前置：{d.prereqs.map((u) => `${u.point}（${pct(u.p_known)}）`).join('、')}</span>
                  )}
                  {d.downstream.length > 0 && <span>受累后继：{d.downstream.join('、')}</span>}
                  <span>
                    复习盒第 {d.evidence.box} 盒 · {d.evidence.due_in_hours <= 0 ? '已到复习时间'
                      : `${Math.round(d.evidence.due_in_hours)} 小时后复习`} · 有效掌握 {pct(d.eff_known)}（含前置修正）
                  </span>
                  {!d.prereqs.length && <span className="sub">无薄弱前置——这个缺陷是本点自身的问题，直接安排复习/重练即可。</span>}
                </div>
              )}
            </div>
          )
        })}
        {!diag.points.length && <p className="status-ok" style={{ marginTop: 8 }}>✓ 当前没有明显知识缺陷，保持节奏！</p>}
      </div>
    </div>
  )
}

// 简易力导向布局：斥力 + 弹簧 + 向心，迭代收敛后静态渲染（节点量级 ≤ 数百，足够快）
function forceLayout(nodes: GraphNode[], edges: GraphEdge[]) {
  const W = 820, H = 500
  const n = nodes.length
  const pos = nodes.map((_, i) => ({
    x: W / 2 + Math.cos((i / n) * Math.PI * 2) * (W / 3),
    y: H / 2 + Math.sin((i / n) * Math.PI * 2) * (H / 3),
  }))
  const idx = new Map(nodes.map((nd, i) => [nd.point, i]))
  const es: [number, number][] = []
  edges.forEach((e) => {
    const a = idx.get(e.from_point), b = idx.get(e.to_point)
    if (a !== undefined && b !== undefined && a !== b) es.push([a, b])
  })
  const k = Math.sqrt((W * H) / Math.max(n, 1)) * 0.85
  for (let iter = 0; iter < 300; iter++) {
    const temp = 1 - iter / 320
    const fx = new Array(n).fill(0)
    const fy = new Array(n).fill(0)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y
        let d2 = dx * dx + dy * dy
        if (d2 < 4) { dx = ((i * 7 + j * 13) % 10) - 5; dy = ((i * 3 + j * 11) % 10) - 5; d2 = dx * dx + dy * dy || 4 }
        const d = Math.sqrt(d2)
        const f = (k * k) / d2
        fx[i] += (dx / d) * f; fy[i] += (dy / d) * f
        fx[j] -= (dx / d) * f; fy[j] -= (dy / d) * f
      }
    }
    for (const [a, b] of es) {
      const dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y
      const d = Math.sqrt(dx * dx + dy * dy) || 1
      const f = (d - k) * 0.09
      fx[a] -= (dx / d) * f; fy[a] -= (dy / d) * f
      fx[b] += (dx / d) * f; fy[b] += (dy / d) * f
    }
    for (let i = 0; i < n; i++) {
      fx[i] += (W / 2 - pos[i].x) * 0.012
      fy[i] += (H / 2 - pos[i].y) * 0.012
      const lim = 26 * temp + 2
      pos[i].x = Math.max(46, Math.min(W - 46, pos[i].x + Math.max(-lim, Math.min(lim, fx[i] * 0.02))))
      pos[i].y = Math.max(28, Math.min(H - 40, pos[i].y + Math.max(-lim, Math.min(lim, fy[i] * 0.02))))
    }
  }
  return { pos, es, W, H }
}

function GraphCard({ sid, onGoto }: { sid: string; onGoto: (t: Tab) => void }) {
  const [data, setData] = useState<GraphData | null>(null)
  const [sel, setSel] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => api.graph(sid).then(setData).catch(() => {})
  useEffect(() => { setData(null); setSel(''); load() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const build = async () => {
    setBusy(true)
    try {
      const r = await api.runSkill(sid, 'graph.build', {})
      alert(`知识图谱已构建：${r.total} 条依赖边（讲义抽取 ${r.llm_edges} + 内置课程图谱匹配 ${r.curriculum_edges}）`)
      await load()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const layout = useMemo(() => {
    if (!data || !data.edges.length || !data.nodes.length) return null
    return forceLayout(data.nodes, data.edges)
  }, [data])

  const colorOf = (nd: GraphNode) =>
    nd.status === 'mastered' ? '#82cf9f' : nd.status === 'learning' ? '#eec488'
      : nd.status === 'weak' ? '#ee9aa9' : '#59617a'
  const statusCn = (nd: GraphNode) =>
    nd.status === 'mastered' ? '已掌握' : nd.status === 'learning' ? '学习中' : nd.status === 'weak' ? '薄弱' : '未测验过'
  const selIdx = data?.nodes.findIndex((nd) => nd.point === sel) ?? -1

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>知识依赖图谱</h3>
        {data && <span className="badge">{data.nodes.length} 节点 · {data.edges.length} 边</span>}
        <span className="sub">箭头指向后继（掌握 A 是学会 B 的前提）；点节点看详情</span>
        <div style={{ flex: 1 }} />
        <button className="btn ghost small" disabled={busy} onClick={build}>
          <Icon name="brain" size={12} /> {busy ? '构建中…' : data?.edges.length ? '重建图谱' : '构建图谱'}
        </button>
      </div>
      {layout && data && (
        <div className="graph-wrap" style={{ marginTop: 12 }}>
          <svg viewBox={`0 0 ${layout.W} ${layout.H}`} style={{ width: '100%', display: 'block' }}>
            <defs>
              <marker id="g-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 1 L 9 5 L 0 9 z" fill="rgba(255,255,255,.4)" />
              </marker>
            </defs>
            {layout.es.map(([a, b], i) => {
              const pa = layout.pos[a], pb = layout.pos[b]
              const active = selIdx >= 0 && (a === selIdx || b === selIdx)
              return (
                <line key={i} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                  stroke={active ? 'rgba(154,143,240,.9)' : 'rgba(255,255,255,.15)'}
                  strokeWidth={active ? 1.8 : 1} markerEnd="url(#g-arrow)"
                  strokeDasharray={data.edges[i]?.source === 'curriculum' ? '4 3' : undefined} />
              )
            })}
            {data.nodes.map((nd, i) => {
              const p = layout.pos[i]
              const r = nd.status === 'unknown' ? 5 : nd.status === 'weak' ? 8 : 7
              return (
                <g key={nd.point} className="g-node" opacity={sel && sel !== nd.point ? 0.35 : 1}
                  onClick={() => setSel(sel === nd.point ? '' : nd.point)}>
                  <circle cx={p.x} cy={p.y} r={sel === nd.point ? r + 3 : r} fill={colorOf(nd)}
                    stroke={sel === nd.point ? '#fff' : 'rgba(0,0,0,.35)'} strokeWidth={sel === nd.point ? 1.6 : 1} />
                  <text x={p.x} y={p.y + r + 12} textAnchor="middle" fontSize="9.5"
                    fill={sel === nd.point ? '#e8eaf2' : 'var(--muted)'}>
                    {nd.point.length > 9 ? nd.point.slice(0, 9) + '…' : nd.point}
                  </text>
                  <title>{`${nd.point}（${statusCn(nd)}${nd.status !== 'unknown' ? ` ${Math.round((nd.p_known || 0) * 100)}%` : ''}）`}</title>
                </g>
              )
            })}
          </svg>
          <div style={{ display: 'flex', gap: 14, padding: '8px 14px', borderTop: '1px solid var(--hairline)', flexWrap: 'wrap' }}>
            {[['#ee9aa9', '薄弱'], ['#eec488', '学习中'], ['#82cf9f', '已掌握'], ['#59617a', '未测']].map(([c, l]) => (
              <span key={l} className="sub" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <i style={{ width: 9, height: 9, borderRadius: '50%', background: c, display: 'inline-block' }} />{l}
              </span>
            ))}
            <span className="sub" style={{ marginLeft: 'auto' }}>虚线边 = 内置课程图谱匹配 · 实线边 = 讲义抽取</span>
          </div>
        </div>
      )}
      {!layout && data && (
        <p className="sub" style={{ marginTop: 10 }}>
          {data.nodes.length < 2
            ? '空间知识点还太少（至少 2 个）——先做几次测验或对话反馈。'
            : '还没有依赖边——点右上角「构建图谱」，LLM 会从讲义抽取前置关系并与内置课程图谱合并。'}
        </p>
      )}
      {data && selIdx >= 0 && (() => {
        const nd = data.nodes[selIdx]
        const ups = data.edges.filter((e) => e.to_point === nd.point).map((e) => e.from_point)
        const downs = data.edges.filter((e) => e.from_point === nd.point).map((e) => e.to_point)
        return (
          <div style={{ marginTop: 12, border: '1px solid var(--hairline)', borderRadius: 12, padding: '10px 14px', fontSize: 13, display: 'grid', gap: 5 }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <b>{nd.point}</b>
              <span className={`badge ${nd.status === 'weak' ? 'expert' : ''}`}>
                {statusCn(nd)}{nd.status !== 'unknown' && ` ${Math.round((nd.p_known || 0) * 100)}%`}
              </span>
              {nd.attempts > 0 && <span className="sub">练 {nd.attempts} 次 · 对 {nd.correct} / 错 {nd.wrong}</span>}
              <div style={{ flex: 1 }} />
              <button className="btn small" onClick={async () => {
                try {
                  await api.runSkill(sid, 'quiz.generate', { topic: nd.point, count: 3 })
                  onGoto('quiz')
                } catch (e: any) { alert(e.message) }
              }}>出 3 题练它</button>
            </div>
            <span className="sub">
              前置：{ups.join('、') || '（无）'}　→　后继：{downs.join('、') || '（无）'}
            </span>
          </div>
        )
      })()}
    </div>
  )
}

function MemoryView({ sid, onGoto }: { sid: string; onGoto: (t: Tab) => void }) {
  const [mem, setMem] = useState<MemoryData | null>(null)
  const [mastery, setMastery] = useState<MasteryData | null>(null)
  const [history, setHistory] = useState<MasteryHistoryPoint[]>([])
  const [busy, setBusy] = useState(false)
  const refresh = () => {
    api.memory(sid).then(setMem).catch(() => setMem({ l1_count: 0, l2: [], l3: [] }))
    api.mastery(sid).then(setMastery).catch(() => {})
    api.masteryHistory(sid).then(setHistory).catch(() => {})
  }
  useEffect(() => { refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!mem) return <div className="empty"><span className="spin" /> 加载中…</div>

  const makeReview = async () => {
    setBusy(true)
    try {
      await api.runSkill(sid, 'review.generate', { count: 5 })
      alert('已按薄弱点生成复习测验，请切到「测验」页作答；答对会自动推进复习间隔')
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const exportReport = async () => downloadMd('report', await api.exportMd(sid, 'report'))

  // 掌握度趋势：每次调整都会记录，按天取平均分画折线
  const trend = (() => {
    const byDay: Record<string, { sum: number; n: number }> = {}
    for (const h of history) {
      const d = new Date(h.created_at * 1000).toISOString().slice(0, 10)
      byDay[d] = byDay[d] || { sum: 0, n: 0 }
      byDay[d].sum += h.score; byDay[d].n++
    }
    return Object.entries(byDay).map(([d, v]) => ({ day: d, avg: v.sum / v.n }))
  })()

  const R = [118, 168, 212]
  const l3 = mem.l3.slice(-12)
  const kindLabel: Record<string, string> = { weakness: '⚠ 薄弱', error: '✗ 错题', mastery: '✓ 掌握' }
  return (
    <div className="content">
      <DefectPanel sid={sid} />
      <GraphCard sid={sid} onGoto={onGoto} />
      <div className="card">
        <h3>记忆图谱 · 三层记忆</h3>
        <p className="sub">L1 工作区镜像保留原始对话，L2 由模型压缩为摘要，L3 沉淀知识点掌握状态 —— 答疑时自动注入。</p>
        {mastery && mastery.points.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <b>知识点掌握度</b>
              <span className="badge">共 {mastery.points.length} 个</span>
              {mastery.weak_count > 0 && <span className="badge expert">薄弱 {mastery.weak_count}</span>}
              {mastery.mastered_count > 0 && <span className="status-ok">✓ 已掌握 {mastery.mastered_count}</span>}
              {mastery.due.length > 0 && <span className="badge expert">{mastery.due.length} 个到复习时间</span>}
              <div style={{ flex: 1 }} />
              <button className="btn small" disabled={busy} onClick={makeReview}>
                <Icon name="quiz" size={12} /> 生成薄弱点复习题
              </button>
              <button className="btn ghost small" onClick={exportReport}>
                <Icon name="book" size={12} /> 导出学习报告
              </button>
            </div>
            <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
              {mastery.points.slice(0, 12).map((p) => {
                const pct = Math.round(p.score * 100)
                const statusCn = p.status === 'weak' ? '薄弱' : p.status === 'mastered' ? '已掌握' : '学习中'
                const dueIn = p.due_at - Date.now()
                const dueCn = p.status === 'mastered' ? '' : dueIn <= 0 ? ' · 应复习' : ` · ${Math.ceil(dueIn / 3600000)}小时后复习`
                return (
                  <div key={p.id} style={{ display: 'grid', gridTemplateColumns: '1fr 160px', gap: 14, alignItems: 'center' }}>
                    <div style={{ fontSize: 13 }}>
                      <b>{p.point}</b>
                      <span style={{ color: 'var(--muted)' }}>　对 {p.correct} / 错 {p.wrong}{dueCn}</span>
                    </div>
                    <div className="mastery-track" title={`${statusCn} ${pct}%`}>
                      <div className={`mastery-fill ${p.status}`} style={{ width: `${pct}%` }} />
                      <span className="mastery-label">{statusCn} {pct}%</span>
                    </div>
                  </div>
                )
              })}
            </div>
            {trend.length >= 2 && (
              <div style={{ marginTop: 16 }}>
                <b style={{ fontSize: 13 }}>掌握度趋势（按日平均）</b>
                <svg viewBox="0 0 300 90" style={{ width: '100%', maxWidth: 560, display: 'block', marginTop: 6 }}>
                  <line x1="0" y1="12" x2="300" y2="12" stroke="var(--hairline)" strokeDasharray="3 3" strokeWidth="1" />
                  <line x1="0" y1="62" x2="300" y2="62" stroke="var(--hairline)" strokeDasharray="3 3" strokeWidth="1" />
                  <text x="302" y="15" fontSize="7" fill="var(--muted)">100%</text>
                  <text x="302" y="65" fontSize="7" fill="var(--muted)">35%</text>
                  <polyline fill="none" stroke="var(--accent, #7aa2f7)" strokeWidth="2"
                    points={trend.map((t, i) => {
                      const x = trend.length === 1 ? 150 : (i / (trend.length - 1)) * 296 + 2
                      const y = 84 - t.avg * 72
                      return `${x},${y}`
                    }).join(' ')} />
                  {trend.map((t, i) => {
                    const x = trend.length === 1 ? 150 : (i / (trend.length - 1)) * 296 + 2
                    const y = 84 - t.avg * 72
                    return <circle key={t.day} cx={x} cy={y} r="2.5" fill="var(--accent, #7aa2f7)"><title>{`${t.day} ${Math.round(t.avg * 100)}%`}</title></circle>
                  })}
                </svg>
              </div>
            )}
          </div>
        )}
        <div className="grid2" style={{ marginTop: 14 }}>
          <div>
            <p><span className="badge expert">L1 工作区镜像</span>　最近 <b>{mem.l1_count}</b> 条对话原文</p>
            <p style={{ marginTop: 18 }}><span className="badge expert">L2 模块摘要</span></p>
            {mem.l2.length ? mem.l2.map((m) => (
              <div key={m.id} className="card" style={{ margin: '8px 0', fontSize: 13, padding: '12px 14px' }}><Md>{m.content}</Md></div>
            )) : <p className="sub">对话累计到 8 条后自动生成摘要</p>}
            <p style={{ marginTop: 18 }}><span className="badge expert">L3 长期档案</span>　{l3.length} 条记录</p>
            <div style={{ display: 'grid', gap: 7, marginTop: 8 }}>
              {l3.slice().reverse().map((m) => (
                <div key={m.id} className={`mem-node ${m.kind}`} style={{ position: 'static', transform: 'none', whiteSpace: 'normal' }}>
                  {kindLabel[m.kind] ?? '•'}　{m.content}
                </div>
              ))}
            </div>
            <button className="btn ghost small" style={{ marginTop: 14 }} onClick={async () => {
              // 一键永久删除全部长期学习档案（错题沉淀/薄弱点），必须有二次确认
              if (!confirm('清空 L3 长期档案？错题沉淀与薄弱点记录将永久删除，且不可恢复。')) return
              try {
                await api.clearMemory(sid, 3); refresh()
              } catch (e: any) { alert('清空失败：' + (e.message || '未知错误')) }
            }}>
              <Icon name="trash" size={12} /> 清空 L3 档案
            </button>
          </div>
          <div className="memory-map">
            {R.map((r) => <div key={r} className="mem-ring" style={{ width: r * 2, height: r * 2, left: '50%', top: '50%', transform: 'translate(-50%,-50%)' }} />)}
            <div className="mem-core" style={{ left: '50%', top: '50%' }}><b>{l3.length}</b>长期记忆</div>
            {l3.map((m, i) => {
              const ring = i % 3
              const angle = (i / Math.max(l3.length, 1)) * Math.PI * 2 - Math.PI / 2
              const x = 50 + (Math.cos(angle) * R[ring] * 100) / 460
              const y = 50 + (Math.sin(angle) * R[ring] * 100) / 460
              return (
                <div key={m.id} className={`mem-node ${m.kind}`} style={{ left: `${x}%`, top: `${y}%` }} title={m.content}>
                  {kindLabel[m.kind] ?? '•'} {m.content.slice(0, 20)}…
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function LibraryView({ spaces, currentSid }: { spaces: Space[]; currentSid: string }) {
  const [books, setBooks] = useState<Book[]>([])
  const [subjects, setSubjects] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [subject, setSubject] = useState('')
  const [busy, setBusy] = useState('')
  const [done, setDone] = useState(0)
  const [pageUrl, setPageUrl] = useState('')
  const [mounted, setMounted] = useState<Record<string, string[]>>({})
  const refresh = () => {
    api.library(query, subject).then(async (bs) => {
      setBooks(bs)
      // 每本书已挂载到哪些课程空间：本地书目可能有挂载，外部/仅书目必然为空
      const entries = await Promise.all(bs.map(async (b) => {
        try { return [b.id, (await api.bookSpaces(b.id)).map((s) => s.name)] as const } catch { return [b.id, []] as const }
      }))
      setMounted(Object.fromEntries(entries))
    }).catch(() => setBooks([]))
    api.librarySubjects().then(setSubjects).catch(() => {})
  }
  useEffect(() => { refresh() }, [query, subject]) // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (files: FileList | null, tag: string) => {
    if (!files?.length) return
    setBusy(tag); setDone(0)
    let ok = 0
    let skipped = 0
    for (const f of Array.from(files)) {
      const low = f.name.toLowerCase()
      if (!['.pdf', '.pptx', '.txt', '.md', '.markdown', '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.zip'].some((ext) => low.endsWith(ext))) { skipped++; continue }
      try {
        const r: any = await api.uploadBook(f)
        if (r.batch) ok += r.batch.length
        else ok++
      } catch (e: any) { alert(`${f.name}: ${e.message}`) }
      setDone((d) => d + 1)
    }
    setBusy(''); refresh()
    if (ok) alert(`已入库 ${ok} 本教材，可在「挂载到空间」后用于答疑引用`)
    else if (skipped) alert(`没有可导入的文件（跳过了 ${skipped} 个不支持的文件）\n支持：PDF / PPTX / TXT / Markdown / 图片 / zip`)
  }

  const fetchPdf = async (b: Book) => {
    setBusy(b.id)
    try { await api.fetchBook(b.id); alert(`《${b.title}》已下载入库`) }
    catch (e: any) { alert(e.message) }
    setBusy(''); refresh()
  }

  const importFromUrl = async () => {
    if (!pageUrl.trim()) return
    setBusy('url')
    try {
      const r = await api.importUrl(pageUrl.trim(), '')
      alert(`已剪藏入库：《${r.title}》（${r.chars} 字），挂载到空间后即可参与答疑检索`)
      setPageUrl(''); refresh()
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const attach = async (b: Book) => {
    if (!spaces.length) { alert('请先在左侧新建一个课程空间'); return }
    let sid = currentSid
    if (!sid) {
      const names = spaces.map((s, i) => `${i + 1}. ${s.name}`).join('\n')
      const idx = Number(prompt(`挂载到哪个课程空间？\n${names}`, '1'))
      if (!idx) return
      sid = spaces[idx - 1]?.id
    }
    if (!sid) return
    // 明确告知挂到哪个空间，避免"随手点挂载、书进了自己遗忘的旧空间"
    const target = spaces.find((s) => s.id === sid)
    if (!confirm(`将《${b.title}》挂载到课程空间「${target?.name || sid}」？`)) return
    setBusy(b.id)
    try {
      const r = await api.attachBook(b.id, sid)
      alert(r.status === 'already' ? '该书已在此空间（无需重复挂载）' : `已挂载并索引 ${r.chunks} 个分块，答疑将引用书内内容`)
    } catch (e: any) { alert(e.message) }
    setBusy(''); refresh()
  }

  const remove = async (b: Book) => {
    if (!confirm(`从书库移除《${b.title}》？\n各空间中该书的挂载索引与已下载文件会一并清理（预置书目删除后不会再自动恢复）。`)) return
    try {
      await api.deleteBook(b.id); refresh()
    } catch (e: any) { alert('删除失败：' + (e.message || '未知错误')) }
  }

  const statusBadge = (b: Book) => b.status === 'local'
    ? <span className="status-ok">✓ 已入库</span>
    : b.status === 'external'
      ? <span className="badge expert">官方免费</span>
      : <span className="badge">仅书目</span>

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>教材书库</h3>
        <p className="sub">
          像词库一样管理的教材库：官方免费开放教材可一键获取；自有正版 PDF / PPTX 课件 / 图片 /
          zip 压缩包批量上传入库（压缩包自动展开，包内每个文件各成一册）；
          挂载到课程空间后，答疑 / 出题自动引用书内内容并标注来源。
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '14px 0 4px', flexWrap: 'wrap' }}>
          <input type="text" style={{ maxWidth: 260 }} placeholder="搜索书名 / 作者…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          <label className="btn" style={{ cursor: 'pointer' }}>
            <Icon name="plus" size={14} /> 上传教材文件
            <input type="file" multiple accept=".pdf,.pptx,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp,.zip" style={{ display: 'none' }}
              onChange={(e) => upload(e.target.files, 'files')} disabled={!!busy} />
          </label>
          <label className="btn ghost" style={{ cursor: 'pointer' }}>
            <Icon name="layers" size={14} /> 整个文件夹批量导入
            <input type="file" multiple style={{ display: 'none' }}
              {...({ webkitdirectory: '' } as any)}
              onChange={(e) => upload(e.target.files, 'folder')} disabled={!!busy} />
          </label>
          {busy === 'files' || busy === 'folder' ? (
            <span className="sub"><span className="spin" /> 正在上传入库… 已处理 {done} 个文件</span>
          ) : busy ? (
            <span className="sub"><span className="spin" /> 处理中…</span>
          ) : null}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
          <input type="text" style={{ maxWidth: 340 }} placeholder="网页剪藏：粘贴讲义 / 博客文章链接（仅公网 http/https）"
            value={pageUrl} onChange={(e) => setPageUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') importFromUrl() }} />
          <button className="btn ghost" disabled={!!busy} onClick={importFromUrl} style={{ flex: 'none' }}>
            <Icon name="book" size={13} /> 剪藏入库
          </button>
        </div>
        <div className="mode-tabs" style={{ marginTop: 12 }}>
          <button className={`mode-tab ${subject === '' ? 'active' : ''}`} onClick={() => setSubject('')}>全部</button>
          {subjects.map((s) => (
            <button key={s} className={`mode-tab ${subject === s ? 'active' : ''}`} onClick={() => setSubject(s)}>{s}</button>
          ))}
        </div>
      </div>

      <table className="quiz">
        <thead><tr><th style={{ width: '34%' }}>书名</th><th>学科</th><th>状态</th><th style={{ width: '30%' }}>说明 / 操作</th></tr></thead>
        <tbody>
          {books.map((b) => (
            <tr key={b.id}>
              <td>
                <b>{b.title}</b>
                <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 3 }}>
                  {b.author}{b.publisher && b.publisher !== '—' ? ` · ${b.publisher}` : ''}
                </div>
                {mounted[b.id]?.length ? (
                  <div className="sub" style={{ fontSize: 12, marginTop: 3, color: 'var(--green)' }}>
                    已挂载：{mounted[b.id].join('、')}
                  </div>
                ) : null}
              </td>
              <td><span className="badge">{b.subject}</span></td>
              <td>{statusBadge(b)}{b.error && <div style={{ color: 'var(--red)', fontSize: 11 }}>{b.error}</div>}</td>
              <td>
                <div style={{ color: 'var(--muted)', fontSize: 12 }}>{b.note}</div>
                <div style={{ display: 'flex', gap: 8, marginTop: 7, flexWrap: 'wrap' }}>
                  {b.status === 'external' && b.pdf_url && (
                    <button className="btn small" disabled={!!busy} onClick={() => fetchPdf(b)}>
                      <Icon name="book" size={12} /> {b.pdf_url.startsWith('http://') ? '获取 PDF（约 70MB）' : '获取 PDF'}
                    </button>
                  )}
                  {b.status === 'local' && (
                    <button className="btn small" disabled={!!busy} onClick={() => attach(b)}>
                      <Icon name="layers" size={12} /> 挂载到空间
                    </button>
                  )}
                  {b.source_url && (
                    <a className="btn ghost small" href={b.source_url} target="_blank" rel="noreferrer">官网来源 ↗</a>
                  )}
                  <button className="btn danger small" disabled={!!busy} onClick={() => remove(b)}>
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!books.length && <div className="empty" style={{ padding: 30 }}>书库为空——点击上方按钮导入你的教材</div>}
    </div>
  )
}

function ProfileView({ spaces, onOpenSpace }: { spaces: Space[]; onOpenSpace: (id: string) => void }) {
  const [form, setForm] = useState<StudentProfile>({
    current_school: '', major: '', year: '', rank_hint: '', flags: [], goal_type: '考研',
    target_school: '', target_major: '', timeline: '', notes: '',
  })
  const [savedAt, setSavedAt] = useState(0)
  const [overview, setOverview] = useState<SpaceOverview[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [schoolList, setSchoolList] = useState<SyllabusSchool[]>([])
  const [majorList, setMajorList] = useState<string[]>([])

  useEffect(() => {
    api.profile().then((p) => { setForm(p); setSavedAt(p.updated_at || 0) }).catch(() => {})
    api.profileOverview().then((o) => setOverview(o.spaces)).catch(() => {})
    api.schools().then(setSchoolList).catch(() => {})
  }, [])

  // 选中 985/211 学校后，专业输入给到培养方案候选（300ms 防抖，避免每击键一个请求竞态）
  useEffect(() => {
    if (!form.current_school) { setMajorList([]); return }
    const t = setTimeout(() => {
      api.majorsForSchool(form.current_school).then((m) =>
        setMajorList([...m.custom_majors, ...m.template_majors, ...m.strong])).catch(() => setMajorList([]))
    }, 300)
    return () => clearTimeout(t)
  }, [form.current_school])

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))
  const FLAGS = ['重修', '挂科', '跨考', '无科研经历', '无竞赛奖项', '英语未过级']
  const RANKS = ['', '前10%', '前20%', '前30%', '前50%', '50%以后']

  const save = async () => {
    setBusy(true)
    try {
      const p = await api.saveProfile(form)
      setForm(p); setSavedAt(p.updated_at || Date.now() / 1000)
      alert('档案已保存，生成「成长手册」时会自动带入')
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const totals = overview?.reduce((a, s) => ({
    points: a.points + s.points, weak: a.weak + s.weak, due: a.due + s.due, flash: a.flash + s.flash_due,
  }), { points: 0, weak: 0, due: 0, flash: 0 }) || { points: 0, weak: 0, due: 0, flash: 0 }

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>个人档案</h3>
        <p className="sub">
          你的学生名片：保存一次，生成「成长手册」时自动带入，复习提醒与薄弱点分析也会参考目标方向。
          所有信息只存在本机。
          {savedAt > 0 && <span>　上次更新：{new Date(savedAt * 1000).toLocaleString()}</span>}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 14 }}>
          <input type="text" list="pf-schools" placeholder="本科院校（如：示例大学，可搜简称）"
            value={form.current_school} onChange={(e) => set('current_school', e.target.value)} />
          <datalist id="pf-schools">
            {schoolList.map((s) => <option key={s.name} value={s.name}>{`${s.tier} · ${s.region}`}</option>)}
          </datalist>
          <input type="text" list="pf-majors" placeholder="专业" value={form.major} onChange={(e) => set('major', e.target.value)} />
          <datalist id="pf-majors">{majorList.map((m) => <option key={m} value={m} />)}</datalist>
          <input type="text" placeholder="年级（如：大二上）" value={form.year} onChange={(e) => set('year', e.target.value)} />
          <select value={form.rank_hint} onChange={(e) => set('rank_hint', e.target.value)}>
            {RANKS.map((r) => <option key={r} value={r}>{r || '成绩排名（选填）'}</option>)}
          </select>
          <input type="text" placeholder="目标院校（如：清华大学）"
            value={form.target_school} onChange={(e) => set('target_school', e.target.value)} />
          <input type="text" placeholder="目标专业（如：机械 085500）"
            value={form.target_major} onChange={(e) => set('target_major', e.target.value)} />
          <input type="text" placeholder="关键时间线（如：2028.12 初试）"
            value={form.timeline} onChange={(e) => set('timeline', e.target.value)} />
          <select value={form.goal_type} onChange={(e) => set('goal_type', e.target.value)}>
            {['考研', '推免/保研', '考研为主+推免兜底'].map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          {FLAGS.map((f) => (
            <button key={f} className={`fb-btn ${form.flags.includes(f) ? 'fb-on' : ''}`}
              onClick={() => set('flags', form.flags.includes(f) ? form.flags.filter((x) => x !== f) : [...form.flags, f])}>
              {form.flags.includes(f) ? '✓ ' : ''}{f}
            </button>
          ))}
        </div>
        <textarea placeholder="补充说明（重修科目、绩点、已有竞赛/项目、与目标方向的相关经历…）"
          style={{ width: '100%', marginTop: 10, minHeight: 56 }}
          value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        <div style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={save}>
            {busy ? <><span className="spin" /> 保存中</> : '保存档案'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3>学习总览</h3>
        <p className="sub">跨课程空间汇总你的知识点掌握情况。</p>
        {overview && overview.length > 0 ? (
          <>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 14px' }}>
              <span className="badge">课程空间 {spaces.length}</span>
              <span className="badge">知识点 {totals.points}</span>
              {totals.weak > 0 && <span className="badge expert">薄弱 {totals.weak}</span>}
              {totals.due > 0 && <span className="badge expert">到期复习 {totals.due}</span>}
              {totals.flash > 0 && <span className="badge expert">待刷闪卡 {totals.flash}</span>}
            </div>
            <table className="quiz">
              <thead><tr><th>空间</th><th>知识点</th><th>薄弱</th><th>已掌握</th><th>平均掌握度</th><th>到期</th><th>测验</th><th style={{ width: 90 }}></th></tr></thead>
              <tbody>
                {overview.map((s) => (
                  <tr key={s.id}>
                    <td><b>{s.name}</b></td>
                    <td>{s.points}</td>
                    <td style={{ color: s.weak ? 'var(--red)' : undefined }}>{s.weak}</td>
                    <td style={{ color: s.mastered ? 'var(--green)' : undefined }}>{s.mastered}</td>
                    <td>
                      {s.points ? (
                        <div className="mastery-track" style={{ minWidth: 110 }} title={`${Math.round(s.avg * 100)}%`}>
                          <div className={`mastery-fill ${s.avg < 0.35 ? 'weak' : s.avg < 0.75 ? 'learning' : 'mastered'}`}
                            style={{ width: `${Math.round(s.avg * 100)}%` }} />
                          <span className="mastery-label">{Math.round(s.avg * 100)}%</span>
                        </div>
                      ) : '—'}
                    </td>
                    <td>{s.due || '—'}</td>
                    <td>{s.quizzes}</td>
                    <td><button className="btn ghost small" onClick={() => onOpenSpace(s.id)}>进入空间</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="sub" style={{ marginTop: 10 }}>还没有课程空间——左侧新建一个，或先把教材挂载进来。</p>
        )}
      </div>
    </div>
  )
}

function SettingsView() {
  const [status, setStatus] = useState<LlmStatus | null>(null)
  const [routing, setRouting] = useState('local')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState('')
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; latency_ms?: number; error?: string }> | null>(null)
  const [mcps, setMcps] = useState<{ name: string; command: string[] }[]>([])
  const [mcpName, setMcpName] = useState('')
  const [mcpCmd, setMcpCmd] = useState('')
  const [experts, setExperts] = useState<{ id: string; name: string; description: string }[]>([])
  const [skills, setSkills] = useState<{ id: string; name: string }[]>([])
  const [curricula, setCurricula] = useState<{ file: string; course: string; concepts: number }[]>([])

  const refreshMcp = () => api.connectors().then((c) => setMcps(c.mcp)).catch(() => {})
  useEffect(() => {
    api.llmConfig().then((s) => {
      setStatus(s); setRouting(s.routing); setBaseUrl(s.cloud.base_url); setModel(s.cloud.model)
    }).catch(() => {})
    refreshMcp()
    api.listExperts().then(setExperts).catch(() => {})
    api.listSkills().then(setSkills).catch(() => {})
    api.curriculums().then(setCurricula).catch(() => {})
  }, [])

  const addMcp = async () => {
    const cmd = mcpCmd.trim().split(/\s+/).filter(Boolean)
    if (!mcpName.trim() || !cmd.length) { alert('请填写名称与启动命令'); return }
    setBusy('mcp')
    try {
      await api.registerMcp(mcpName.trim(), cmd)
      setMcpName(''); setMcpCmd(''); refreshMcp()
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const delMcp = async (name: string) => {
    try {
      await api.removeMcp(name); refreshMcp()
    } catch (e: any) { alert('删除失败：' + (e.message || '未知错误')) }
  }

  const save = async () => {
    setBusy('save')
    try {
      const s = await api.updateLlmConfig({
        routing,
        cloud_base_url: baseUrl,
        cloud_model: model,
        ...(apiKey ? { cloud_api_key: apiKey } : {}),
      })
      setStatus(s); setApiKey(''); alert('模型配置已保存')
    } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const test = async () => {
    setBusy('test')
    try { setTestResult(await api.testLlm()) } catch (e: any) { alert(e.message) }
    setBusy('')
  }

  const ROUTES: [string, string, string][] = [
    ['local', '全本地', '所有任务走本机模型，完全离线'],
    ['auto', '自动路由', '出题 / 判卷 / 分析 / 规划走云端，日常问答走本地'],
    ['cloud', '全云端', '全部走云端 API，云端失败自动回退本地'],
  ]
  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>模型设置 · 本地 / 云端双通道</h3>
        <p className="sub">
          本地通道始终可用（{status?.local.model || '…'}）；配置云端 OpenAI 兼容 API 后，
          可按任务把重推理交给云端，日常答疑保持本地低延迟。云端密钥仅保存在本机 data 目录。
        </p>
        <div style={{ display: 'grid', gap: 10, margin: '16px 0', maxWidth: 640 }}>
          {ROUTES.map(([v, t, d]) => (
            <label key={v} className="route-opt" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
              <input type="radio" name="routing" checked={routing === v} onChange={() => setRouting(v)} style={{ marginTop: 3 }} />
              <span><b>{t}</b><span style={{ color: 'var(--muted)' }}>　{d}</span></span>
            </label>
          ))}
        </div>
        <div style={{ display: 'grid', gap: 10, maxWidth: 640 }}>
          <input type="text" placeholder="云端 API 地址（如 https://api.openai.com/v1 或国内兼容端点）"
            value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          <input type="text" placeholder="云端模型名（如 gpt-4o-mini / deepseek-chat）"
            value={model} onChange={(e) => setModel(e.target.value)} />
          <input type="password" placeholder={status?.cloud.api_key_masked || '云端 API Key（留空则不修改）'}
            value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 16, alignItems: 'center' }}>
          <button className="btn" disabled={!!busy} onClick={save}>
            {busy === 'save' ? <><span className="spin" /> 保存中</> : '保存配置'}
          </button>
          <button className="btn ghost" disabled={!!busy} onClick={test}>
            {busy === 'test' ? <><span className="spin" /> 测试中</> : '测试连通'}
          </button>
        </div>
        {testResult && (
          <table className="quiz" style={{ marginTop: 16, maxWidth: 640 }}>
            <thead><tr><th>通道</th><th>状态</th><th>延迟</th><th>错误</th></tr></thead>
            <tbody>
              {(['local', 'cloud'] as const).map((p) => (
                <tr key={p}>
                  <td>{p === 'local' ? '本地模型' : '云端 API'}</td>
                  <td>{testResult[p]?.ok ? <span className="status-ok">✓ 连通</span> : <span className="status-err">✗ 不通</span>}</td>
                  <td>{testResult[p]?.latency_ms ? `${testResult[p].latency_ms} ms` : '—'}</td>
                  <td style={{ color: 'var(--red)', fontSize: 12 }}>{testResult[p]?.error || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>MCP 连接器</h3>
        <p className="sub">
          注册本机 MCP server（stdio 命令），答疑专家在需要时会自动调用其工具（如读本地文件）。
          注册持久化保存，重启后自动恢复。命令以空格分隔，如：
          <code> npx -y @modelcontextprotocol/server-filesystem C:/path</code>
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <input type="text" style={{ maxWidth: 160 }} placeholder="名称（如 fs）"
            value={mcpName} onChange={(e) => setMcpName(e.target.value)} />
          <input type="text" style={{ flex: 1, minWidth: 280 }} placeholder="启动命令（空格分隔）"
            value={mcpCmd} onChange={(e) => setMcpCmd(e.target.value)} />
          <button className="btn" disabled={!!busy} onClick={addMcp} style={{ flex: 'none' }}>
            {busy === 'mcp' ? <><span className="spin" /> 注册中</> : '注册'}
          </button>
        </div>
        {mcps.length > 0 && (
          <table className="quiz" style={{ marginTop: 14, maxWidth: 720 }}>
            <thead><tr><th>名称</th><th>命令</th><th style={{ width: 60 }}></th></tr></thead>
            <tbody>
              {mcps.map((m) => (
                <tr key={m.name}>
                  <td><b>{m.name}</b></td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{m.command.join(' ')}</td>
                  <td><button className="btn danger small" onClick={() => delMcp(m.name)}><Icon name="trash" size={12} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>专家团 · 技能 · 内置课程图谱</h3>
        <p className="sub">
          答疑按问题内容自动路由到对应专家；技能由各功能页的按钮触发（出题、判卷、闪卡、讲义总结…）；
          构建知识图谱时，讲义抽取的前置关系会与内置课程图谱合并。
        </p>
        <b style={{ fontSize: 13 }}>专家团（{experts.length} 位）</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 14px' }}>
          {experts.map((e) => (
            <span key={e.id} className="badge" title={e.description}>{e.name}</span>
          ))}
        </div>
        <b style={{ fontSize: 13 }}>技能（{skills.length} 项）</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 14px' }}>
          {skills.map((s) => (
            <span key={s.id} className="badge" title={s.id}>{s.name}</span>
          ))}
        </div>
        <b style={{ fontSize: 13 }}>内置课程图谱（{curricula.length} 门）</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 0' }}>
          {curricula.map((c) => (
            <span key={c.file} className="badge">{c.course} · {c.concepts} 个知识点</span>
          ))}
          {!curricula.length && <span className="sub">暂无内置课程图谱数据</span>}
        </div>
      </div>
    </div>
  )
}

function HandbookView({ spaces, currentSid }: { spaces: Space[]; currentSid: string }) {
  const [hist, setHist] = useState<HandbookMeta[]>([])
  const [current, setCurrent] = useState<Handbook | null>(null)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    current_school: '', major: '', year: '', rank_hint: '',
    flags: [] as string[], goal_type: '考研',
    target_school: '', target_major: '', timeline: '', notes: '',
  })
  const spaceId = currentSid || ''
  const refresh = () => api.handbooks().then(setHist).catch(() => {})
  useEffect(() => { refresh() }, [])
  // 已保存的个人档案自动带入表单，无需重复填写
  useEffect(() => {
    api.profile().then((p) => {
      setForm((f) => ({
        ...f,
        current_school: p.current_school || f.current_school,
        major: p.major || f.major,
        year: p.year || f.year,
        rank_hint: p.rank_hint || f.rank_hint,
        flags: p.flags?.length ? p.flags : f.flags,
        goal_type: p.goal_type || f.goal_type,
        target_school: p.target_school || f.target_school,
        target_major: p.target_major || f.target_major,
        timeline: p.timeline || f.timeline,
        notes: p.notes || f.notes,
      }))
    }).catch(() => {})
  }, [])

  const FLAGS = ['重修', '挂科', '跨考', '无科研经历', '无竞赛奖项', '英语未过级']
  const RANKS = ['', '前10%', '前20%', '前30%', '前50%', '50%以后']
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  const generate = async () => {
    if (!form.target_school) { alert('请填写目标院校'); return }
    setBusy(true)
    try {
      const h = await api.generateHandbook({ ...form, space_id: spaceId })
      setCurrent(h); refresh()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const open = async (id: string) => {
    try { setCurrent(await api.handbook(id)) } catch (e: any) { alert('打开失败：' + (e.message || '未知错误')) }
  }
  const remove = async (id: string) => {
    if (!confirm('删除该手册？')) return
    try {
      await api.deleteHandbook(id)
      if (current?.id === id) setCurrent(null)
      refresh()
    } catch (e: any) { alert('删除失败：' + (e.message || '未知错误')) }
  }
  const exportHandbook = () => downloadMd('成长手册', current?.content || '')

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>成长手册 · 升学战略引擎</h3>
        <p className="sub">
          基于真实院校政策（学籍/重修/推免/招生要求，每条结论标注官方来源）× 你的处境
          （如：大一重修、跨考）× StudyPilot 掌握度数据，生成直达目标的分阶段行动手册。
          政策每年可能调整，关键节点以官方最新文件为准。
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 14 }}>
          <input type="text" placeholder="本科院校（如：示例大学 / 中国人民大学）"
            value={form.current_school} onChange={(e) => set('current_school', e.target.value)} />
          <input type="text" placeholder="专业" value={form.major} onChange={(e) => set('major', e.target.value)} />
          <input type="text" placeholder="年级（如：大二上）" value={form.year} onChange={(e) => set('year', e.target.value)} />
          <select value={form.rank_hint} onChange={(e) => set('rank_hint', e.target.value)}>
            {RANKS.map((r) => <option key={r} value={r}>{r || '成绩排名（选填）'}</option>)}
          </select>
          <input type="text" placeholder="目标院校（如：清华大学）"
            value={form.target_school} onChange={(e) => set('target_school', e.target.value)} />
          <input type="text" placeholder="目标专业（如：机械 085500 智能制造与机器人）"
            value={form.target_major} onChange={(e) => set('target_major', e.target.value)} />
          <input type="text" placeholder="关键时间线（如：2028.12 初试）"
            value={form.timeline} onChange={(e) => set('timeline', e.target.value)} />
          <select value={form.goal_type} onChange={(e) => set('goal_type', e.target.value)}>
            {['考研', '推免/保研', '考研为主+推免兜底'].map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          {FLAGS.map((f) => (
            <button key={f} className={`fb-btn ${form.flags.includes(f) ? 'fb-on' : ''}`}
              onClick={() => set('flags', form.flags.includes(f) ? form.flags.filter((x) => x !== f) : [...form.flags, f])}>
              {form.flags.includes(f) ? '✓ ' : ''}{f}
            </button>
          ))}
        </div>
        <textarea placeholder="补充说明（重修科目、绩点、已有竞赛/项目、与目标方向的相关经历…）"
          style={{ width: '100%', marginTop: 10, minHeight: 56 }}
          value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={generate}>
            {busy ? <><span className="spin" /> 正在结合政策库生成…（约1分钟）</> : <><Icon name="compass" size={14} /> 生成成长手册</>}
          </button>
          {spaceId && <span className="sub">将结合当前空间「{spaces.find((s) => s.id === spaceId)?.name}」的掌握度数据</span>}
        </div>
      </div>

      {current && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>{current.title}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn ghost small" onClick={exportHandbook}>
                <Icon name="book" size={12} /> 导出 Markdown
              </button>
              <button className="btn ghost small" onClick={() => setCurrent(null)}>收起</button>
            </div>
          </div>
          <Md>{current.content}</Md>
        </div>
      )}

      {hist.length > 0 && (
        <div className="card">
          <h3>历史手册</h3>
          <table className="quiz" style={{ marginTop: 10 }}>
            <tbody>
              {hist.map((h) => (
                <tr key={h.id}>
                  <td style={{ cursor: 'pointer' }} onClick={() => open(h.id)}><b>{h.title}</b></td>
                  <td style={{ width: 150, color: 'var(--muted)', fontSize: 12 }}>
                    {new Date(h.created_at * 1000).toLocaleDateString()}</td>
                  <td style={{ width: 60 }}>
                    <button className="btn danger small" onClick={() => remove(h.id)}><Icon name="trash" size={12} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default App
