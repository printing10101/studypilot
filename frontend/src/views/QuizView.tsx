// 测验练习：练习/模拟考 + 错题本 + 费曼讲解检验（子页签）
import { useEffect, useState } from 'react'
import { api, QuizRecord, TeachResult, WrongQ } from '../api'
import { downloadMd, Icon, SubTabs } from '../ui'
import { useUX } from '../ux'

export function QuizView({ sid }: { sid: string }) {
  const { toast, prompt: uxPrompt } = useUX()
  const [quizzes, setQuizzes] = useState<QuizRecord[]>([])
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [userAnswers, setUserAnswers] = useState<Record<string, Record<string, string>>>({})
  const [sub, setSub] = useState('practice')
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
      // 记下本场考试的限时，供倒计时与自动交卷使用
      const made = Array.isArray(r) ? r[0] : r
      if (skill === 'exam.mock' && made?.quiz_id) {
        localStorage.setItem(`exam_minutes_${made.quiz_id}`, String(made.exam_minutes || 30))
      }
      await refresh(); setSub('practice')
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const submit = async (quiz: QuizRecord, auto = false) => {
    const answers = quiz.questions.map((q) => ({ qid: q.id, answer: userAnswers[quiz.id]?.[q.id] ?? '' }))
    setBusy(true)
    try {
      // 交卷前自评预测正确率（用于校准）；限时自动交卷时跳过
      if (!auto) {
        const raw = await uxPrompt({ title: '交卷前自评', label: '你预计本卷正确率是多少？（0-100，可留空跳过）', placeholder: '如 80' })
        if (raw != null && raw.trim() !== '') {
          const pct = Number(raw)
          if (!Number.isNaN(pct)) {
            try { await api.predictQuiz(sid, quiz.id, Math.max(0, Math.min(100, pct)) / 100) } catch { /* 预测失败不阻塞判分 */ }
          }
        }
      }
      await api.runSkill(sid, 'quiz.grade', { quiz_id: quiz.id, answers })
      localStorage.removeItem(`exam_start_${quiz.id}`)
      localStorage.removeItem(`exam_minutes_${quiz.id}`)
      await refresh()
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const examRemaining = (quiz: QuizRecord) => {
    const start = Number(localStorage.getItem(`exam_start_${quiz.id}`)) || Date.now()
    return examMinutes(quiz.id) * 60 - Math.floor((now - start) / 1000)
  }

  // 到时自动交卷
  useEffect(() => {
    if (busy) return
    for (const q of examLive) {
      if (examRemaining(q) <= 0) {
        const quiz = quizzes.find((x) => x.id === q.id)
        if (quiz) { submit(quiz, true); break }
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
      <SubTabs value={sub} onChange={setSub} tabs={[['practice', '练习 · 模拟考'], ['wrong', '错题本'], ['teach', '费曼讲解检验']]} />

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
  const { toast } = useUX()
  const [items, setItems] = useState<WrongQ[]>([])
  const [picked, setPicked] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => { api.wrongQuestions(sid).then((r) => { setItems(r); setLoaded(true) }).catch(() => setLoaded(true)) }, [sid])

  const redo = async (qids?: string[]) => {
    setBusy(true)
    try {
      const r = await api.redoWrong(sid, qids || [])
      toast('success', `已按 ${r.redo_count} 道错题重组测验，请到「练习」页作答`)
      onRedone()
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const variants = async (qids?: string[]) => {
    setBusy(true)
    try {
      const r: any = await api.runSkill(sid, 'wrong.variants', { qids: qids || [] })
      // 该技能返回数组（每卷一项），取第一项读 variant_count
      const made = Array.isArray(r) ? r[0] : r
      toast('success', `已生成 ${made?.variant_count ?? '?'} 道变式题（同知识点换数字/换情境/换问法），请到「练习」页作答`)
      onRedone()
    } catch (e: any) { toast('error', e.message) }
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
  const { toast } = useUX()
  const [topic, setTopic] = useState('')
  const [explanation, setExplanation] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<TeachResult | null>(null)

  const check = async () => {
    if (!topic.trim() || !explanation.trim()) { toast('warn', '请填写概念主题和你的讲解'); return }
    setBusy(true); setResult(null)
    try { setResult(await api.runSkill(sid, 'teach.check', { topic, explanation })) } catch (e: any) { toast('error', e.message) }
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
