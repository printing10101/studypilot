// 学习分析：薄弱诊断（缺陷 + 依赖图谱）· 掌握度趋势（含 BKT 个性化拟合）· 记忆档案（L1/L2/L3）
// 原名「记忆图谱」，一页塞了四件事；现按用途拆成三个子页签，构建图谱按钮只保留一个
import { useEffect, useMemo, useState } from 'react'
import { api, BktParam, DefectDiag, GraphData, GraphEdge, GraphNode, MasteryData, MasteryHistoryPoint, MemoryData } from '../api'
import { downloadMd, Icon, SubTabs } from '../ui'
import { Md } from '../md'
import { useUX } from '../ux'

export function AnalyticsView({ sid, onGoto }: { sid: string; onGoto: (t: string) => void }) {
  const [sub, setSub] = useState('defects')
  return (
    <div className="content">
      <SubTabs value={sub} onChange={setSub}
        tabs={[['defects', '薄弱诊断'], ['mastery', '掌握度趋势'], ['memory', '记忆档案']]} />
      {sub === 'defects' && <DefectTab sid={sid} onGoto={onGoto} />}
      {sub === 'mastery' && <MasteryTab sid={sid} />}
      {sub === 'memory' && <MemoryTab sid={sid} />}
    </div>
  )
}

// ---------- 子页 1：薄弱诊断（缺陷传播 + 依赖图谱，共用一个构建按钮） ----------

function DefectTab({ sid, onGoto }: { sid: string; onGoto: (t: string) => void }) {
  const { toast } = useUX()
  const [diag, setDiag] = useState<DefectDiag | null>(null)
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [building, setBuilding] = useState(false)
  const [open, setOpen] = useState('')

  const load = () => {
    api.defects(sid).then(setDiag).catch(() => {})
    api.graph(sid).then(setGraph).catch(() => {})
  }
  useEffect(() => { setDiag(null); setGraph(null); load() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const build = async () => {
    setBuilding(true)
    try {
      const r = await api.runSkill(sid, 'graph.build', {})
      toast('success', `知识图谱已构建：${r.total} 条依赖边（讲义抽取 ${r.llm_edges} + 内置课程图谱匹配 ${r.curriculum_edges}）`)
      load()
    } catch (e: any) { toast('error', e.message) }
    setBuilding(false)
  }

  const hasGraph = !!graph && graph.edges.length > 0
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <span className="sub">掌握度由贝叶斯知识追踪（BKT）更新，叠加遗忘曲线估算「此刻留存」，再沿依赖图把前置缺陷向下游传播。</span>
        <div style={{ flex: 1 }} />
        <button className="btn small" disabled={building} onClick={build}>
          <Icon name="brain" size={12} /> {building ? '构建中…' : hasGraph ? '重建知识图谱' : '构建知识图谱'}
        </button>
      </div>
      <DefectPanel diag={diag} open={open} setOpen={setOpen} hasGraph={hasGraph} />
      <GraphCard sid={sid} data={graph} onGoto={onGoto} />
    </>
  )
}

function DefectPanel({ diag, open, setOpen, hasGraph }: {
  diag: DefectDiag | null; open: string; setOpen: (v: string) => void; hasGraph: boolean
}) {
  if (!diag) return <div className="card" style={{ marginBottom: 18 }}><span className="spin" /> 缺陷诊断计算中…</div>
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>知识缺陷诊断</h3>
        <span className="badge expert">缺陷 {diag.points.length} 处</span>
        {hasGraph
          ? <span className="badge">已启用依赖传播</span>
          : <span className="badge">未建依赖图</span>}
      </div>
      <p className="sub" style={{ marginTop: 6 }}>
        排序按综合风险，而非只看单点得分。
        {!hasGraph && ' 构建依赖图后可发现「前置拖累」与根因链。'}
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

function GraphCard({ sid, data, onGoto }: { sid: string; data: GraphData | null; onGoto: (t: string) => void }) {
  const { toast } = useUX()
  const [sel, setSel] = useState('')
  useEffect(() => { setSel('') }, [data])

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
            : '还没有依赖边——点右上角「构建知识图谱」，LLM 会从讲义抽取前置关系并与内置课程图谱合并。'}
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
                } catch (e: any) { toast('error', e.message) }
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

// ---------- 子页 2：掌握度趋势（知识点掌握 + 折线 + BKT 个性化拟合） ----------

function MasteryTab({ sid }: { sid: string }) {
  const { toast } = useUX()
  const [mastery, setMastery] = useState<MasteryData | null>(null)
  const [history, setHistory] = useState<MasteryHistoryPoint[]>([])
  const [bkt, setBkt] = useState<Record<string, Omit<BktParam, 'point'>> | null>(null)
  const [busy, setBusy] = useState(false)
  const refresh = () => {
    api.mastery(sid).then(setMastery).catch(() => {})
    api.masteryHistory(sid).then(setHistory).catch(() => {})
    api.bktParams(sid).then(setBkt).catch(() => {})
  }
  useEffect(() => { refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const makeReview = async () => {
    setBusy(true)
    try {
      await api.runSkill(sid, 'review.generate', { count: 5 })
      toast('info', '已按薄弱点生成复习测验，请切到「测验」页作答；答对会自动推进复习间隔')
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const fitBkt = async () => {
    setBusy(true)
    try {
      const r = await api.bktFit(sid)
      toast('success', r.fitted_count > 0
        ? `已为 ${r.fitted_count} 个知识点拟合个性化 BKT 参数（Baum-Welch EM）`
        : '答题记录还不够，无法拟合（每个知识点至少需要几条作答记录）')
      setBkt(await api.bktParams(sid))
    } catch (e: any) { toast('error', e.message) }
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

  const fittedCount = bkt ? Object.values(bkt).filter((p) => p.source === 'fitted').length : 0
  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        {mastery && mastery.points.length > 0 ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0 }}>知识点掌握度</h3>
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
            <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
              {mastery.points.slice(0, 20).map((p) => {
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
          </>
        ) : (
          <p className="sub" style={{ marginTop: 6 }}>还没有知识点记录——做几次测验、或在对话里反馈「懂了/没懂」就会开始积累。</p>
        )}
      </div>

      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>BKT 学习参数个性化</h3>
          {bkt && <span className="badge">{Object.keys(bkt).length} 个知识点</span>}
          {fittedCount > 0 && <span className="badge expert">{fittedCount} 个已按你的作答历史拟合</span>}
          <div style={{ flex: 1 }} />
          <button className="btn small" disabled={busy} onClick={fitBkt}>
            <Icon name="chart" size={12} /> {busy ? '拟合中…' : '按我的答题记录拟合'}
          </button>
        </div>
        <p className="sub" style={{ marginTop: 6 }}>
          贝叶斯知识追踪有 4 个参数：初始掌握 p(L0)、每次练习学会 p(T)、猜对 p(G)、失误 p(S)。
          默认用通用值；有足够作答记录后可拟合出你自己的参数，掌握度估计会更准。
        </p>
        {bkt && Object.keys(bkt).length > 0 && (
          <table className="quiz" style={{ marginTop: 10, maxWidth: 720 }}>
            <thead><tr><th>知识点</th><th>p(L0) 初始</th><th>p(T) 学会</th><th>p(G) 猜对</th><th>p(S) 失误</th><th>来源</th></tr></thead>
            <tbody>
              {Object.entries(bkt).slice(0, 12).map(([point, p]) => (
                <tr key={point}>
                  <td><b>{point}</b></td>
                  <td>{(p.p_l0 * 100).toFixed(0)}%</td>
                  <td>{(p.p_t * 100).toFixed(0)}%</td>
                  <td>{(p.p_g * 100).toFixed(0)}%</td>
                  <td>{(p.p_s * 100).toFixed(0)}%</td>
                  <td>{p.source === 'fitted' ? <span className="badge expert">个性化拟合</span> : <span className="badge">通用默认</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

// ---------- 子页 3：记忆档案（三层记忆 L1/L2/L3 原貌） ----------

function MemoryTab({ sid }: { sid: string }) {
  const { toast, confirm: uxConfirm } = useUX()
  const [mem, setMem] = useState<MemoryData | null>(null)
  const refresh = () => api.memory(sid).then(setMem).catch(() => setMem({ l1_count: 0, l2: [], l3: [] }))
  useEffect(() => { refresh() }, [sid])
  if (!mem) return <div className="empty"><span className="spin" /> 加载中…</div>

  const R = [118, 168, 212]
  const l3 = mem.l3.slice(-12)
  const kindLabel: Record<string, string> = { weakness: '⚠ 薄弱', error: '✗ 错题', mastery: '✓ 掌握' }
  return (
    <div className="card">
      <h3>三层记忆</h3>
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
          <button className="btn ghost small" style={{ marginTop: 14 }} onClick={async () => {
            // 一键永久删除全部长期学习档案（错题沉淀/薄弱点），必须有二次确认
            if (!(await uxConfirm({ title: '清空长期档案', message: '错题沉淀与薄弱点记录将永久删除，且不可恢复。', confirmText: '清空', danger: true }))) return
            try {
              await api.clearMemory(sid, 3); refresh()
            } catch (e: any) { toast('error', '清空失败：' + (e.message || '未知错误')) }
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
  )
}
