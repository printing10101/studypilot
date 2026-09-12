// 测验练习：练习/模拟考 + 错题本 + 费曼讲解检验（子页签）
// 作答草稿实时存 localStorage（key 按 quiz id），刷新/切空间不再丢已答内容
import { useEffect, useRef, useState } from 'react'
import { api, NavExtra, QuizRecord, runSkillStream, TeachResult, WrongQ } from '../api'
import { downloadMd, Icon, SubTabs } from '../ui'
import { useUX } from '../ux'

export function QuizView({ sid, navExtra }: { sid: string; navExtra?: NavExtra }) {
  const { toast, prompt: uxPrompt, confirm: uxConfirm } = useUX()
  const [quizzes, setQuizzes] = useState<QuizRecord[]>([])
  const [quizErr, setQuizErr] = useState('')  // 加载失败 ≠ 没有卷子：静默空态会让人以为记录丢了
  const [quizLoading, setQuizLoading] = useState(true)
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [userAnswers, setUserAnswers] = useState<Record<string, Record<string, string>>>({})
  const [sub, setSub] = useState('practice')
  const [now, setNow] = useState(Date.now())
  const [hl, setHl] = useState('')
  const [phase, setPhase] = useState('')
  const [gradingId, setGradingId] = useState('')  // 正在判卷的卷子：按钮就近转圈，而不是只有顶部按钮变化
  const focusRef = useRef('')
  const draftKey = (quizId: string) => `quiz_draft_${quizId}`
  // localStorage 配额满/隐私模式禁用时抛 QuotaExceededError：裸写会打穿渲染
  const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* 草稿存不下不影响作答 */ } }
  const lsRemove = (k: string) => { try { localStorage.removeItem(k) } catch { /* ignore */ } }
  // 「阻止所有 Cookie」下读 localStorage 同样会抛 SecurityError：读也要走 try 包装
  const lsGet = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }
  // 切空间竞态防护：组件实例被复用（仅 props 变化），旧空间的响应/回调不得写入新视图
  const sidRef = useRef(sid)
  const loadSeq = useRef(0)
  const genAbort = useRef<AbortController | null>(null)
  const autoTried = useRef<Set<string>>(new Set())  // 自动交卷失败后不再每秒重试

  const refresh = () => {
    const seq = ++loadSeq.current
    setQuizLoading(true)
    return api.quizzes(sid).then((qs) => {
      if (seq !== loadSeq.current) return  // 已切换空间，丢弃过期响应
      setQuizzes(qs); setQuizErr('')
      // 恢复未交卷的作答草稿；已判卷的卷子顺手清掉残留草稿
      setUserAnswers((u) => {
        const next = { ...u }
        for (const q of qs) {
          if (q.answers.length > 0) { delete next[q.id]; lsRemove(draftKey(q.id)); continue }
          if (!next[q.id]) {
            try {
              const raw = localStorage.getItem(draftKey(q.id))
              if (raw) next[q.id] = JSON.parse(raw)
            } catch { /* 草稿损坏则当没有 */ }
          }
        }
        return next
      })
    }).catch((e: any) => {
      if (seq !== loadSeq.current) return
      setQuizErr(e?.message || '网络错误')
    }).finally(() => { if (seq === loadSeq.current) setQuizLoading(false) })
  }
  useEffect(() => {
    sidRef.current = sid
    genAbort.current?.abort()  // 旧空间进行中的生成任务：中断回调，避免污染新视图
    genAbort.current = null
    setQuizzes([]); setQuizErr(''); setQuizLoading(true); setBusy(false); setPhase('')
    refresh(); setSub('practice'); setUserAnswers({}); setHl('')
  }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  // 作答草稿持久化：统一在 effect 里写（updater 内做副作用会在 StrictMode 下双调用，
  // 且 localStorage 配额满时异常会从 setState 内部打穿渲染）
  useEffect(() => {
    for (const [quizId, answers] of Object.entries(userAnswers)) {
      lsSet(draftKey(quizId), JSON.stringify(answers))
    }
  }, [userAnswers])  

  // 深链：外部带 sub / quizId 跳入（今日页磁贴、每日一题、图谱「出 N 题练它」…）
  useEffect(() => {
    if (!navExtra) return
    if (navExtra.sub) setSub(navExtra.sub)
    if (navExtra.quizId) {
      focusRef.current = navExtra.quizId
      if (!navExtra.sub) setSub('practice')
    }
  }, [navExtra])
  // 卷子列表就绪后执行定位：滚动到目标卷并短暂高亮
  useEffect(() => {
    const target = focusRef.current
    if (!target || !quizzes.some((q) => q.id === target)) return
    focusRef.current = ''
    setHl(target)
    const t = setTimeout(() => {
      document.getElementById(`quiz-${target}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 80)
    const clear = setTimeout(() => setHl(''), 2600)
    return () => { clearTimeout(t); clearTimeout(clear) }
  }, [quizzes])

  const setAnswer = (quizId: string, qid: string, value: string) => {
    setUserAnswers((u) => ({ ...u, [quizId]: { ...u[quizId], [qid]: value } }))
  }
  const examLive = quizzes.filter((q) => q.topic === '模拟考试' && !q.answers.length)
  // 限时起点/时长持久化到 localStorage：切页/刷新不再重置倒计时；时间到自动交卷
  useEffect(() => {
    examLive.forEach((q) => {
      if (!lsGet(`exam_start_${q.id}`)) {
        lsSet(`exam_start_${q.id}`, String(Date.now()))
      }
    })
    if (!examLive.length) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [quizzes]) // eslint-disable-line react-hooks/exhaustive-deps

  const examMinutes = (quizId: string) => Number(lsGet(`exam_minutes_${quizId}`)) || 30

  const generate = (skill: string, params: object) => {
    // 走 SSE 流式端点：按钮实时显示「检索讲义/生成/入库」阶段，而不是黑盒转圈
    const ctrl = new AbortController()
    genAbort.current = ctrl
    const sidAtStart = sid
    setBusy(true)
    setPhase('准备中…')
    runSkillStream(sid, skill, params, {
      onPhase: setPhase,
      onDone: (r: any) => {
        if (sidRef.current !== sidAtStart) return  // 生成期间切了空间：结果归旧视图，不写入
        // 记下本场考试的限时，供倒计时与自动交卷使用
        const made = Array.isArray(r) ? r[0] : r
        if (skill === 'exam.mock' && made?.quiz_id) {
          lsSet(`exam_minutes_${made.quiz_id}`, String(made.exam_minutes || 30))
        }
        // 新卷定位：生成完直接滚到刚出的这张卷
        if (made?.quiz_id) focusRef.current = made.quiz_id
        setBusy(false); setPhase('')
        refresh(); setSub('practice')
      },
      onError: (m) => {
        if (sidRef.current !== sidAtStart) return
        setBusy(false); setPhase(''); toast('error', m)
      },
      onAbort: () => { if (sidRef.current === sidAtStart) { setBusy(false); setPhase('') } },
    }, ctrl.signal)
  }

  const submit = async (quiz: QuizRecord, auto = false) => {
    const answers = quiz.questions.map((q) => ({ qid: q.id, answer: userAnswers[quiz.id]?.[q.id] ?? '' }))
    // 防误触：空题会按空答案判 0 分，交卷前明确告知还剩几题没答（限时自动交卷不打断）
    if (!auto) {
      const unanswered = quiz.questions.filter((q) => !(userAnswers[quiz.id]?.[q.id] ?? '').trim()).length
      if (unanswered > 0) {
        const go = await uxConfirm({ title: '还有未作答的题目',
          message: `本卷还有 ${unanswered} 题未作答，将按空答案判分。确定交卷？`, confirmText: '交卷' })
        if (!go) return
      }
    }
    setBusy(true); setPhase('判卷中…'); setGradingId(quiz.id)
    try {
      // 交卷前自评预测正确率（用于校准）；限时自动交卷时跳过。
      // 输入非数字必须明确告知：静默跳过会让用户以为校准数据已记录
      if (!auto) {
        let raw: string | null = await uxPrompt({ title: '交卷前自评', label: '你预计本卷正确率是多少？（0-100，可留空跳过）', placeholder: '如 80' })
        while (raw != null && raw.trim() !== '' && (Number.isNaN(Number(raw)) || Number(raw) < 0 || Number(raw) > 100)) {
          toast('warn', '请输入 0-100 之间的数字')
          raw = await uxPrompt({ title: '交卷前自评', label: '你预计本卷正确率是多少？（0-100，可留空跳过）', placeholder: '如 80' })
        }
        if (raw != null && raw.trim() !== '') {
          try { await api.predictQuiz(sid, quiz.id, Math.max(0, Math.min(100, Number(raw))) / 100) } catch { /* 预测失败不阻塞判分 */ }
        }
      }
      await api.runSkill(sid, 'quiz.grade', { quiz_id: quiz.id, answers })
      lsRemove(`exam_start_${quiz.id}`)
      lsRemove(`exam_minutes_${quiz.id}`)
      lsRemove(draftKey(quiz.id))
      setUserAnswers((u) => { const n = { ...u }; delete n[quiz.id]; return n })
      await refresh()
    } catch (e: any) { toast('error', e.message) }
    setBusy(false); setPhase(''); setGradingId('')
  }

  const examRemaining = (quiz: QuizRecord) => {
    const start = Number(lsGet(`exam_start_${quiz.id}`)) || Date.now()
    return examMinutes(quiz.id) * 60 - Math.floor((now - start) / 1000)
  }

  // 到时自动交卷（每卷只自动尝试一次：判卷是长请求，失败后每秒重试只会
  // 刷屏 toast + 打爆后端；失败后保留「时间到，请交卷」徽标让用户手动交）。
  // 超时超过 10 分钟视为隔天/久隔重开：用户还没看卷子就被按空草稿判分太伤，改为只提示
  useEffect(() => {
    if (busy) return
    for (const q of examLive) {
      const remain = examRemaining(q)
      if (remain <= 0 && remain > -600 && !autoTried.current.has(q.id)) {
        const quiz = quizzes.find((x) => x.id === q.id)
        if (quiz) {
          autoTried.current.add(q.id)
          submit(quiz, true)
          break
        }
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
            <p className="sub">出题官依据讲义出题 → 判卷助教逐题分析 → 错题自动存入错题本与长期记忆，成为日后复习题的素材。</p>
            <div style={{ display: 'flex', gap: 12, marginTop: 14, flexWrap: 'wrap' }}>
              <input type="text" placeholder="主题（如：高斯定理），留空覆盖全课程"
                value={topic} onChange={(e) => setTopic(e.target.value)} />
              <button className="btn" disabled={busy} onClick={() => generate('quiz.generate', { topic, count: 5 })} style={{ flex: 'none' }}>
                {busy ? <><span className="spin" /> {phase || '生成中…'}</> : <><Icon name="quiz" size={14} /> 生成 5 道题</>}
              </button>
              <button className="btn ghost" disabled={busy} onClick={() => generate('exam.mock', { count: 10, minutes: 30 })} style={{ flex: 'none' }}>
                <Icon name="plan" size={14} /> 模拟考试（10 题 · 限时 30 分钟）
              </button>
            </div>
          </div>
          {quizErr && (
            <div className="card" style={{ marginBottom: 18, padding: '12px 16px', borderColor: 'var(--red)', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span>⚠ 卷子列表加载失败：{quizErr}</span>
              <div style={{ flex: 1 }} />
              <button className="btn small" onClick={refresh}>重新加载</button>
            </div>
          )}
          {!quizErr && quizLoading && !quizzes.length && (
            <p className="sub" style={{ textAlign: 'center' }}><span className="spin" /> 正在加载卷子…</p>
          )}
          {quizzes.map((quiz) => {
            const graded = quiz.answers.length > 0
            const byQid: Record<string, any> = {}
            quiz.answers.forEach((a) => { byQid[a.qid] = a })
            const isExam = quiz.topic === '模拟考试'
            const remain = isExam && !graded ? examRemaining(quiz) : 0
            const summary = graded ? pointSummary(quiz) : {}
            return (
              <div key={quiz.id} id={`quiz-${quiz.id}`} className={`card${hl === quiz.id ? ' quiz-focus' : ''}`}
                style={{ marginBottom: 18 }}>
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
                          {(q.options || []).length > 0 && graded && (
                            <div style={{ color: 'var(--muted)', margin: '7px 0' }}>{q.options.join('　')}</div>
                          )}
                          {!graded ? (
                            (q.options || []).length > 0 ? (
                              <div style={{ margin: '7px 0', display: 'grid', gap: 6, maxWidth: 480 }}>
                                {(q.options || []).map((opt, oi) => {
                                  const active = (userAnswers[quiz.id]?.[q.id] ?? '') === opt
                                  const label = /^[a-d][.、．]/i.test(opt) ? opt : `${String.fromCharCode(65 + oi)}. ${opt}`
                                  return (
                                    <button key={oi} type="button" onClick={() => setAnswer(quiz.id, q.id, opt)}
                                      style={{ textAlign: 'left', padding: '7px 11px', borderRadius: 8, cursor: 'pointer',
                                        fontSize: 13, color: 'inherit',
                                        border: `1px solid ${active ? 'var(--accent)' : 'var(--hairline-2)'}`,
                                        background: active ? 'rgba(154,143,240,.12)' : 'transparent' }}>
                                      {label}
                                    </button>
                                  )
                                })}
                              </div>
                            ) : (
                              <input type="text" style={{ maxWidth: 420 }} placeholder="输入你的答案"
                                value={userAnswers[quiz.id]?.[q.id] ?? ''}
                                onChange={(e) => setAnswer(quiz.id, q.id, e.target.value)} />
                            )
                          ) : (
                            <div style={{ fontSize: 13, marginTop: 7, display: 'grid', gap: 4 }}>
                              <span>
                                判定：<span className={`verdict-${byQid[q.id]?.verdict ?? ''}`}>{byQid[q.id]?.verdict}</span>
                                　<span style={{ color: 'var(--muted)' }}>
                                  参考答案：{byQid[q.id]?.correct_answer ?? '（未记录）'}
                                </span>
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
                {!graded && (
                  <button className="btn" style={{ marginTop: 14 }} disabled={busy} onClick={() => submit(quiz)}>
                    {gradingId === quiz.id ? <><span className="spin" /> 判卷中，约需几十秒…</> : '交卷判分'}
                  </button>
                )}
              </div>
            )
          })}
        </>
      )}

      {sub === 'wrong' && <WrongBook sid={sid} onRedone={(quizId) => { refresh(); setSub('practice'); if (quizId) focusRef.current = quizId }} />}
      {sub === 'teach' && <TeachView sid={sid} />}
    </div>
  )
}

function WrongBook({ sid, onRedone }: { sid: string; onRedone: (quizId?: string) => void }) {
  const { toast } = useUX()
  const [items, setItems] = useState<WrongQ[]>([])
  const [picked, setPicked] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [err, setErr] = useState('')  // 加载失败不能伪装成「没有错题」——那是主动误导
  const load = () => {
    setErr('')
    api.wrongQuestions(sid).then((r) => { setItems(r); setLoaded(true) })
      .catch((e: any) => { setErr(e?.message || '网络错误'); setLoaded(true) })
  }
  useEffect(() => { setLoaded(false); load() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const redo = async (qids?: string[]) => {
    setBusy(true)
    try {
      const r = await api.redoWrong(sid, qids || [])
      toast('success', `已按 ${r.redo_count} 道错题重组测验，请作答`)
      onRedone(r.quiz_id)
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const variants = async (qids?: string[]) => {
    setBusy(true)
    try {
      const r: any = await new Promise((resolve, reject) => {
        runSkillStream(sid, 'wrong.variants', { qids: qids || [] }, {
          onPhase: (label) => toast('info', label),
          onDone: resolve, onError: reject,
        })
      })
      // 该技能返回数组（每卷一项），取第一项读 variant_count / quiz_id
      const made = Array.isArray(r) ? r[0] : r
      toast('success', `已生成 ${made?.variant_count ?? '?'} 道变式题（同知识点换数字/换情境/换问法），请作答`)
      onRedone(made?.quiz_id)
    } catch (e: any) { toast('error', e?.message || '生成失败') }
    setBusy(false)
  }

  const exportWrong = async () => downloadMd('wrong', await api.exportMd(sid, 'wrong'))

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
      {items.map((q, i) => {
        // 测验分组头：与前一题的 quiz_topic 比较（不在渲染期改写外层变量）
        const showTopic = i === 0 || q.quiz_topic !== items[i - 1].quiz_topic
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
      {!loaded && <p className="sub" style={{ textAlign: 'center' }}><span className="spin" /> 正在加载错题本…</p>}
      {loaded && !!err && (
        <div className="card" style={{ padding: '12px 16px', borderColor: 'var(--red)', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span>⚠ 错题本加载失败：{err}</span>
          <div style={{ flex: 1 }} />
          <button className="btn small" onClick={load}>重新加载</button>
        </div>
      )}
      {loaded && !err && !items.length && <div className="empty" style={{ padding: 30 }}>没有错题——去「练习」页生成一次测验吧</div>}
    </>
  )
}

function TeachView({ sid }: { sid: string }) {
  const { toast } = useUX()
  const [topic, setTopic] = useState('')
  const [explanation, setExplanation] = useState('')
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState('')
  const [result, setResult] = useState<TeachResult | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const sidRef = useRef(sid)
  useEffect(() => { sidRef.current = sid }, [sid])
  // 切空间清空旧空间的讲解与结果；讲解是长文，切页卸载即丢，草稿按空间存 sessionStorage
  // （不在卸载时清理：切页回来草稿还在；键按 sid 隔离，会话结束随 sessionStorage 释放）
  useEffect(() => { setTopic(''); setExplanation(''); setResult(null); abortRef.current?.abort() }, [sid])
  useEffect(() => {
    setTopic(sessionStorage.getItem(`sp-teach-topic-${sid}`) || '')
    setExplanation(sessionStorage.getItem(`sp-teach-text-${sid}`) || '')
  }, [sid])  
  useEffect(() => {
    if (topic) sessionStorage.setItem(`sp-teach-topic-${sid}`, topic)
    if (explanation) sessionStorage.setItem(`sp-teach-text-${sid}`, explanation)
  }, [sid, topic, explanation])
  useEffect(() => () => abortRef.current?.abort(), [])

  const check = () => {
    if (!topic.trim() || !explanation.trim()) { toast('warn', '请填写概念主题和你的讲解'); return }
    // 走流式端点：拿到阶段进度与取消能力（同步版是一条黑盒长请求，模型慢时只能干等）
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const sidAtStart = sid
    setBusy(true); setResult(null)
    runSkillStream(sid, 'teach.check', { topic, explanation }, {
      onPhase: setPhase,
      onDone: (r: TeachResult) => {
        if (sidRef.current !== sidAtStart) return
        setBusy(false); setPhase(''); setResult(r)
      },
      onError: (m: string) => {
        if (sidRef.current !== sidAtStart) return
        setBusy(false); setPhase(''); toast('error', m)
      },
      onAbort: () => { if (sidRef.current === sidAtStart) { setBusy(false); setPhase('') } },
    }, ctrl.signal)
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
            {busy ? <><span className="spin" /> {phase || '判定中'}</> : <><Icon name="spark" size={14} /> 提交讲解</>}
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
