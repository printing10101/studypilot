import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, chatStream, Citation, Doc, MemoryData, Msg, QuizRecord, Space } from './api'
import { Icon, Typing } from './ui'

type Tab = 'chat' | 'docs' | 'quiz' | 'memory'

function Md({ children }: { children: string }) {
  return (
    <div className="md">
      <Markdown remarkPlugins={[remarkGfm]}>{children}</Markdown>
    </div>
  )
}

function App() {
  const [spaces, setSpaces] = useState<Space[]>([])
  const [sid, setSid] = useState<string>('')
  const [tab, setTab] = useState<Tab>('chat')
  const [health, setHealth] = useState<{ llm: boolean; model: string } | null>(null)

  const refreshSpaces = () => api.listSpaces().then(setSpaces).catch(() => {})
  useEffect(() => {
    refreshSpaces()
    api.health().then(setHealth).catch(() => setHealth({ llm: false, model: '未连接' }))
  }, [])

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
          <div className="nav-section">项目空间</div>
          {spaces.map((s) => (
            <div key={s.id} className={`nav-item ${sid === s.id ? 'active' : ''}`}
              onClick={() => { setSid(s.id); setTab('chat') }}>
              <Icon name="layers" />{s.name}
            </div>
          ))}
          <button className="side-btn" onClick={newSpace}><Icon name="plus" size={14} /> 新建课程空间</button>

          {sid && (
            <>
              <div className="nav-section">功能</div>
              {([['chat', '学习对话', 'chat'], ['docs', '知识库', 'book'], ['quiz', '测验', 'quiz'], ['memory', '记忆图谱', 'brain']] as [Tab, string, string][]).map(([t, label, ic]) => (
                <div key={t} className={`nav-item ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                  <Icon name={ic} />{label}
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
          {!sid ? (
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
          ) : tab === 'chat' ? <ChatView sid={sid} /> : tab === 'docs' ? <DocsView sid={sid} /> : tab === 'quiz' ? <QuizView sid={sid} /> : <MemoryView sid={sid} />}
        </div>
      </div>
    </>
  )
}

function ChatView({ sid }: { sid: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [mode, setMode] = useState('ask')
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => { api.listMessages(sid).then(setMsgs).catch(() => {}) }, [sid])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, note])

  const send = () => {
    const text = input.trim()
    if (!text || busy) return
    setInput(''); setNote(''); setBusy(true)
    setMsgs((m) => [...m, { role: 'user', mode, content: text }, { role: 'assistant', mode, content: '' }])
    chatStream(sid, mode, text,
      (t) => setMsgs((m) => {
        const copy = [...m]; copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + t }
        return copy
      }),
      ({ expert, citations }) => {
        setBusy(false)
        setMsgs((m) => {
          const copy = [...m]; copy[copy.length - 1] = { ...copy[copy.length - 1], expert, citations }
          return copy
        })
      },
    )
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
          <textarea value={input} placeholder="向助教提问…（包含「出题」「计划」等关键词会自动路由到对应专家）"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <button className="send-btn" disabled={busy} onClick={send}><Icon name="send" /></button>
        </div>
      </div>
    </>
  )
}

function DocsView({ sid }: { sid: string }) {
  const [docs, setDocs] = useState<Doc[]>([])
  const [busy, setBusy] = useState(false)
  const refresh = () => api.listDocs(sid).then(setDocs)
  useEffect(() => { refresh() }, [sid])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    for (const f of Array.from(files)) {
      try { await api.uploadDoc(sid, f) } catch (e: any) { alert(`${f.name}: ${e.message}`) }
    }
    await refresh(); setBusy(false)
  }

  return (
    <div className="content">
      <div className="card">
        <h3>知识库</h3>
        <p className="sub">RAG 管线：讲义解析 → 语义分块 → BGE 向量化 → 检索引用。支持 PDF / TXT / Markdown。</p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '16px 0 4px' }}>
          <label className="btn" style={{ cursor: 'pointer' }}>
            <Icon name="plus" size={14} /> 选择讲义文件
            <input type="file" multiple accept=".pdf,.txt,.md,.markdown" style={{ display: 'none' }}
              onChange={(e) => upload(e.target.files)} disabled={busy} />
          </label>
          {busy && <span className="sub"><span className="spin" /> 正在解析并向量化…（首次运行会下载嵌入模型）</span>}
        </div>
        <table className="quiz" style={{ marginTop: 12 }}>
          <thead><tr><th>文件</th><th>状态</th><th>分块</th><th>错误</th></tr></thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td>{d.status === 'ready' ? <span className="status-ok">✓ 已索引</span> : d.status === 'error' ? <span className="status-err">✗ 失败</span> : <span className="status-wait"><span className="spin" /> 处理中</span>}</td>
                <td>{d.chunks}</td>
                <td style={{ color: 'var(--red)' }}>{d.error}</td>
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
  const refresh = () => api.quizzes(sid).then(setQuizzes)
  useEffect(() => { refresh() }, [sid])

  const generate = async () => {
    setBusy(true)
    try {
      await api.runSkill(sid, 'quiz.generate', { topic, count: 5 })
      await refresh()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  const submit = async (quiz: QuizRecord) => {
    const answers = quiz.questions.map((q) => ({ qid: q.id, answer: userAnswers[quiz.id]?.[q.id] ?? '' }))
    setBusy(true)
    try {
      await api.runSkill(sid, 'quiz.grade', { quiz_id: quiz.id, answers })
      await refresh()
    } catch (e: any) { alert(e.message) }
    setBusy(false)
  }

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>出题测验</h3>
        <p className="sub">出题官依据讲义出题 → 判卷助教逐题分析 → 错题自动写入 L3 长期记忆。</p>
        <div style={{ display: 'flex', gap: 12, marginTop: 14 }}>
          <input type="text" placeholder="主题（如：高斯定理），留空覆盖全课程"
            value={topic} onChange={(e) => setTopic(e.target.value)} />
          <button className="btn" disabled={busy} onClick={generate} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> 生成中</> : <><Icon name="quiz" size={14} /> 生成 5 道题</>}
          </button>
        </div>
      </div>
      {quizzes.map((quiz) => {
        const graded = quiz.answers.length > 0
        const byQid: Record<string, any> = {}
        quiz.answers.forEach((a) => { byQid[a.qid] = a })
        return (
          <div key={quiz.id} className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <b>测验：{quiz.topic || '综合'}</b>
              {graded && <span className="badge expert">得分 {quiz.answers.filter((a) => a.verdict === '对').length}/{quiz.questions.length}</span>}
            </div>
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
    </div>
  )
}

function MemoryView({ sid }: { sid: string }) {
  const [mem, setMem] = useState<MemoryData | null>(null)
  const refresh = () => api.memory(sid).then(setMem)
  useEffect(() => { refresh() }, [sid])
  if (!mem) return <div className="empty"><span className="spin" /> 加载中…</div>

  const R = [118, 168, 212]
  const l3 = mem.l3.slice(-12)
  const kindLabel: Record<string, string> = { weakness: '⚠ 薄弱', error: '✗ 错题', mastery: '✓ 掌握' }
  return (
    <div className="content">
      <div className="card">
        <h3>记忆图谱 · 三层记忆</h3>
        <p className="sub">L1 工作区镜像保留原始对话，L2 由模型压缩为摘要，L3 沉淀知识点掌握状态 —— 答疑时自动注入。</p>
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
            <button className="btn ghost small" style={{ marginTop: 14 }} onClick={async () => { await api.clearMemory(sid, 3); refresh() }}>
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

export default App
