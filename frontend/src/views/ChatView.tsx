// 学习对话：专家路由答疑（Ask/Plan/Craft）+ 苏格拉底引导 + 讲义总结 + 懂/没懂反馈
import { useEffect, useRef, useState } from 'react'
import { api, chatStream, Citation, Msg } from '../api'
import { Icon, Typing } from '../ui'
import { Md } from '../md'
import { useUX } from '../ux'

export function ChatView({ sid }: { sid: string }) {
  const { toast, prompt: uxPrompt, select: uxSelect } = useUX()
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
      toast('error', msg)
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
      confusion = await uxPrompt({ title: '哪里没懂？', label: '描述一下可以帮助助教更准地记住薄弱点', placeholder: '可留空', multiline: true }) || ''
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
