// 学习对话：专家路由答疑（Ask/Plan/Craft）+ 苏格拉底引导 + 讲义总结 + 懂/没懂反馈
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api, chatStream, Citation, Msg } from '../api'
import { Icon, Typing } from '../ui'
import { Md } from '../md'
import { useUX } from '../ux'

export function ChatView({ sid, llmOk = true, onOpenSettings }: {
  sid: string; llmOk?: boolean; onOpenSettings?: () => void
}) {
  const { toast, prompt: uxPrompt, select: uxSelect } = useUX()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [histErr, setHistErr] = useState('')  // 历史加载失败 ≠ 没有历史：空态会让用户以为记录全丢了
  const [mode, setMode] = useState('ask')
  const [guide, setGuide] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [viz, setViz] = useState<{ title: string; html: string } | null>(null)
  const [fbGiven, setFbGiven] = useState<Record<string, string>>({})
  const bottom = useRef<HTMLDivElement>(null)
  const nearBottom = useRef(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const sidRef = useRef(sid)
  useEffect(() => { sidRef.current = sid }, [sid])
  const prependAnchor = useRef<{ prevHeight: number; prevTop: number } | null>(null)
  const PAGE = 50
  const [hasMore, setHasMore] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)

  const loadHistory = (sid: string) => {
    setHasMore(false); setLoadingOlder(false); setHistErr('')
    api.listMessages(sid, { limit: PAGE })
      .then((r) => { setMsgs(r.messages); setHasMore(r.has_more) })
      .catch((e: any) => setHistErr(e?.message || '网络错误'))
  }

  // 「加载更早」prepend 提交后恢复阅读位置（DOM 已更新，此处调整 scrollTop 不会闪跳）
  useLayoutEffect(() => {
    const a = prependAnchor.current
    if (!a) return
    prependAnchor.current = null
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight - a.prevHeight + a.prevTop
  })

  // 历史分页加载：首次只取最近 50 条，更早的按需「加载更早」
  useEffect(() => { loadHistory(sid) }, [sid])
  // 输入草稿按空间持久化：切页/切空间回来不丢（切页会卸载组件，纯 state 无痕丢失）
  useEffect(() => { setInput(sessionStorage.getItem(`sp-chat-draft-${sid}`) || '') }, [sid])
  useEffect(() => {
    if (input) sessionStorage.setItem(`sp-chat-draft-${sid}`, input)
    else sessionStorage.removeItem(`sp-chat-draft-${sid}`)
  }, [sid, input])
  useEffect(() => { nearBottom.current = true; abortRef.current?.abort(); setNote('') }, [sid])
  // 组件卸载（切到其他页）时中断进行中的流式请求：否则切回来时生成中的回答凭空消失
  useEffect(() => () => abortRef.current?.abort(), [])
  // 仅当用户本来就停在底部时才自动跟随，否则流式输出期间无法往上翻历史
  useEffect(() => { if (nearBottom.current) bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, note])

  const loadOlder = async () => {
    const firstTs = msgs[0]?.created_at
    if (!firstTs || !hasMore || loadingOlder) return
    const sidAtStart = sid
    setLoadingOlder(true)
    // 记录插入前的滚动状态：prepend 提交后由 useLayoutEffect 锚回原内容，避免阅读位置跳动
    const el = scrollRef.current
    prependAnchor.current = { prevHeight: el?.scrollHeight ?? 0, prevTop: el?.scrollTop ?? 0 }
    try {
      const r = await api.listMessages(sid, { limit: PAGE, before: firstTs })
      // 切空间后旧请求返回：旧空间消息不能 prepend 进新会话
      if (sidRef.current === sidAtStart) {
        setMsgs((m) => [...r.messages, ...m])
        setHasMore(r.has_more)
      }
    } catch (e: any) { toast('error', '加载更早消息失败：' + (e.message || '未知错误')) }
    setLoadingOlder(false)
  }

  const send = () => {
    const text = input.trim()
    if (!text || busy) return
    const sidAtStart = sid
    setInput(''); setNote(''); setBusy(true)
    nearBottom.current = true
    setMsgs((m) => [...m, { role: 'user', mode, content: text }, { role: 'assistant', mode, content: '' }])
    // 失败/中止时移除空的助手占位气泡（有部分内容则保留），用户提问始终留在会话里
    const dropEmptyAssistant = () => setMsgs((m) => {
      const copy = [...m]
      if (copy.length && copy[copy.length - 1].role === 'assistant' && !copy[copy.length - 1].content) copy.pop()
      return copy
    })
    const fail = (msg: string) => {
      setBusy(false)
      abortRef.current = null
      dropEmptyAssistant()
      toast('error', msg)
      // 原文放回输入框，可直接重发；若用户已开始输入新内容则不打断
      setInput((cur) => (cur.trim() ? cur : text))
    }
    const controller = new AbortController()
    abortRef.current = controller
    chatStream(sid, mode, text, {
      onDelta: (t) => setMsgs((m) => {
        const copy = [...m]; copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + t }
        return copy
      }),
      onDone: ({ expert, citations, assistant_message_id }) => {
        abortRef.current = null
        setBusy(false)
        setMsgs((m) => {
          const copy = [...m]; copy[copy.length - 1] = { ...copy[copy.length - 1], expert, citations, id: assistant_message_id }
          return copy
        })
      },
      onError: fail,
      onAbort: () => {
        abortRef.current = null
        setBusy(false)
        dropEmptyAssistant()
        // 切空间时的自动 abort 不弹提示（用户并没有点停止）
        if (sidRef.current === sidAtStart) toast('info', '已停止生成')
      },
    }, { guide, signal: controller.signal })
  }

  const stopGenerate = () => abortRef.current?.abort()

  const copyMsg = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast('success', '已复制到剪贴板')
    } catch { toast('error', '复制失败：当前环境不允许访问剪贴板') }
  }

  const give = async (mid: string, rating: string, understood: number) => {
    let confusion = ''
    if (understood === 0) {
      const t = await uxPrompt({ title: '哪里没懂？', label: '描述一下可以帮助助教更准地记住薄弱点', placeholder: '可留空', multiline: true })
      if (t === null) return  // 用户点了取消/按了 Esc：中止整条负反馈，而不是当空描述提交
      confusion = t
    }
    try {
      await api.sendFeedback(sid, mid, rating, understood, confusion)
      setFbGiven((f) => ({ ...f, [mid]: understood === 1 ? 'helpful' : 'unhelpful' }))
    } catch (e: any) {
      // 提交失败必须让用户知道：负反馈驱动掌握度更新，静默丢反馈=数据丢失
      toast('error', '反馈提交失败：' + (e.message || '未知错误'))
    }
  }

  const makeNote = async () => {
    const docs = await api.listDocs(sid)
    const ready = docs.filter((d) => d.status === 'ready')
    if (!ready.length) { toast('warn', '请先在资料中心上传并索引讲义'); return }
    const docId = await uxSelect({ title: '选择要总结的讲义', options: ready.map((d) => ({ value: d.id, label: d.filename })) })
    const doc = ready.find((d) => d.id === docId)
    if (!doc) return
    setBusy(true); setNote('正在生成总结…')
    try {
      const r = await api.runSkill(sid, 'note.summarize', { document_id: doc.id })
      setNote(r.note)
    } catch (e: any) { setNote('失败：' + e.message) }
    setBusy(false)
  }

  // 概念可视化：抽象知识点 → 交互式讲解页（后端模板渲染，sandbox iframe 展示）
  const makeViz = async () => {
    const topic = await uxPrompt({
      title: '概念可视化', label: '输入想「看见」的知识点',
      placeholder: '如：傅里叶变换 / 高斯定理 / 弯矩图',
    })
    if (topic === null || !topic.trim()) return
    setBusy(true); setViz(null)
    try {
      const r = await api.runSkill(sid, 'concept.visualize', { topic: topic.trim() })
      setViz({ title: r.title || topic, html: r.html })
    } catch (e: any) { toast('error', '可视化失败：' + (e.message || '未知错误')) }
    setBusy(false)
  }

  return (
    <>
      <div className="content" ref={scrollRef} onScroll={(e) => {
        const el = e.currentTarget
        nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
      }}>
        {hasMore && (
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
            <button className="btn ghost small" disabled={loadingOlder} onClick={loadOlder}>
              {loadingOlder ? <><span className="spin" /> 加载中…</> : '加载更早消息'}
            </button>
          </div>
        )}
        {histErr && (
          <div className="card" style={{ margin: '0 auto 16px', padding: '12px 16px', borderColor: 'var(--red)', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', maxWidth: 560 }}>
            <span>⚠ 历史消息加载失败：{histErr}</span>
            <div style={{ flex: 1 }} />
            <button className="btn small" onClick={() => loadHistory(sid)}>重新加载</button>
          </div>
        )}
        {!histErr && !msgs.length && !busy && (
          // 新空间的空态引导：此前只有模式页签和一个输入框，新用户不知道能问什么
          <div className="card" style={{ margin: '0 auto 20px', padding: '20px 22px', maxWidth: 560 }}>
            <b>可以把作业、讲义里没看懂的地方直接贴上来问，例如：</b>
            <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
              {[
                '用大白话解释一下「傅里叶变换」的直觉，再给一个例子',
                '出 5 道关于「牛顿第二定律」的选择题考我',
                '帮我制定两周复习《高数上》的计划',
              ].map((q) => (
                <button key={q} className="btn ghost small" style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                  onClick={() => setInput(q)}>
                  {q}
                </button>
              ))}
            </div>
            <p className="sub" style={{ margin: '12px 0 0' }}>
              回答带讲义引用；答完可以点 👍/✗ 告诉助教有没有讲懂，没懂的地方会进入你的薄弱点记忆。
            </p>
          </div>
        )}
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
          <button className="btn ghost small" disabled={busy} onClick={makeViz}
            title="把抽象知识点变成可交互的分步讲解图（DeepTutor Visualize 式）">
            <Icon name="spark" size={13} /> 概念可视化
          </button>
          <button className="btn ghost small" disabled={busy} onClick={makeNote}><Icon name="spark" size={13} /> 讲义总结技能</button>
        </div>

        {msgs.map((m, i) => {
          const typing = busy && i === msgs.length - 1 && m.role === 'assistant' && !m.content
          return (
            <div key={m.id || `idx-${i}`} className={`msg ${m.role}`}>
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
                    // 原始检索分数（0.8134）对学生没有意义：只展示来源，分数收进悬浮提示
                    <span key={c.index} className="citation" title={`${c.source}（相关度 ${(c.score * 100).toFixed(0)}%）：${c.snippet}`}>
                      <Icon name="book" size={10} /> [{c.index}] {c.source}
                    </span>
                  ))}
                </div>
              )}
              {m.role === 'assistant' && m.id && !typing && (
                <div className="fb-row">
                  <button className="fb-btn" onClick={() => copyMsg(m.content)}>复制</button>
                  {fbGiven[m.id] ? (
                    <span className="fb-done">反馈已记录，助教记住了 ✓</span>
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
        {viz && (
          <div className="msg assistant">
            <div className="who">
              <span className="avatar ai"><Icon name="spark" size={13} /></span>
              <span>概念可视化 · {viz.title}</span><span className="badge">CRAFT</span>
              <div style={{ flex: 1 }} />
              <button className="fb-btn" onClick={() => setViz(null)}>关闭</button>
            </div>
            {/* sandbox（无 allow-same-origin）：讲解页脚本在透明源运行，无法触碰应用与会话数据 */}
            <iframe className="bubble" title={viz.title} sandbox="allow-scripts"
              srcDoc={viz.html}
              style={{ width: '100%', minHeight: 420, border: 'none', borderRadius: 12, padding: 0, background: '#fafafa' }} />
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="chat-footer">
        {!llmOk && (
          <div className="llm-hint">
            <span>模型未连接——答疑需要本地模型或云端 API，现在发送会失败。</span>
            <div style={{ flex: 1 }} />
            {onOpenSettings && <button className="btn ghost small" onClick={onOpenSettings}>去模型设置</button>}
          </div>
        )}
        <div className="input-shell">
          <textarea value={input}
            placeholder={guide
              ? '向助教提问…（引导模式：会先提示思路，而不是直接给答案）'
              : '向助教提问…（包含「出题」「计划」等关键词会自动路由到对应专家）'}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} />
          {busy && abortRef.current ? (
            <button className="send-btn stop" onClick={stopGenerate} title="停止生成" aria-label="停止生成"><Icon name="close" /></button>
          ) : (
            <button className="send-btn" disabled={busy || !input.trim()} onClick={send} title="发送（Enter）"><Icon name="send" /></button>
          )}
        </div>
      </div>
    </>
  )
}
