// 子页签⑥：竞赛规划（目标导向的竞赛推荐与分析）。
import { useEffect, useState } from 'react'
import { api, CompetitionAnalysis, CompetitionItem, CompetitionPick, StudentProfile } from '../../api'
import { Icon } from '../../ui'
import { Md } from '../../md'
import { useUX } from '../../ux'
import { goalAlias } from './common'

const COMPETE_GOALS = ['考研', '推免/保研', '就业', '出国']

export function CompeteTab({ profile, profileErr, onGoto }: {
  profile: StudentProfile | null; profileErr: string; onGoto: (t: string) => void
}) {
  const { toast } = useUX()
  const [goal, setGoal] = useState('考研')
  const [useLlm, setUseLlm] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<CompetitionAnalysis | null>(null)
  const [catalog, setCatalog] = useState<CompetitionItem[] | null>(null)
  const [catalogOpen, setCatalogOpen] = useState(false)

  useEffect(() => {
    if (profile) setGoal(goalAlias(profile.goal_type) === '保研' ? '推免/保研' : goalAlias(profile.goal_type) === '考研' ? '考研' : '就业')
  }, [profile])

  useEffect(() => {
    if (catalogOpen && !catalog) api.competitionCatalog().then((r) => setCatalog(r.items)).catch(() => setCatalog([]))
  }, [catalogOpen, catalog])

  const analyze = async () => {
    if (!profile) { toast('warn', '个人档案还在加载中，稍后再试'); return }
    setBusy(true)
    try {
      setResult(await api.competitionAnalyze({ goal, use_llm: useLlm, ...profile }))
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
  }

  const tierBlock = (title: string, tone: 'ok' | 'mid' | 'bad', items: CompetitionPick[]) => {
    if (!items.length) return null
    const color = tone === 'ok' ? 'var(--green)' : tone === 'mid' ? 'var(--orange)' : 'var(--red)'
    return (
      <div style={{ marginTop: 14 }}>
        <b style={{ color, fontSize: 13.5 }}>{title}（{items.length}）</b>
        <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
          {items.map((p) => (
            <div key={p.id} style={{ border: '1px solid var(--hairline)', borderRadius: 12, padding: '10px 14px', fontSize: 13 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <b>{p.name}</b>
                <span className="badge">{p.tier}</span>
                {p.specialist && <span className="badge expert">专业对口</span>}
                <span className="sub">{p.team}</span>
              </div>
              <div className="sub" style={{ marginTop: 4 }}>
                赛期：{p.window_label}
                {p.suggested_date && `　·　建议参加 ${p.suggested_date} 那届`}
                　·　备赛约 {p.prep_weeks} 周
              </div>
              <p style={{ margin: '6px 0 0', color: 'var(--muted)', lineHeight: 1.6 }}>{p.why}</p>
              {p.note && <p style={{ margin: '4px 0 0', color: 'var(--orange)' }}>◎ {p.note}</p>}
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>竞赛规划 · 目标倒推分析</h3>
        <p className="sub">
          从目标反推「至少要参加哪几个竞赛」：按目标路径（考研复试 / 推免综测 / 求职简历 / 留学背景）
          给各竞赛的价值打分，结合专业对口度与时间可行性（赛期、出成绩周期 vs 你的截止日）分级推荐。
          赛期为常见惯例，报名与赛制以当年官方通知为准。
        </p>
        {profile ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 4px' }}>
            <span className="badge">本科：{[profile.current_school, profile.major, profile.year].filter(Boolean).join(' · ') || '（未填写）'}</span>
            <span className="badge">目标：{[profile.target_school, profile.target_major].filter(Boolean).join(' ') || '（未填写）'}</span>
            {profile.timeline && <span className="badge">时间线：{profile.timeline}</span>}
            <span className="sub">
              档案在 <a href="#" onClick={(e) => { e.preventDefault(); onGoto('profile') }} style={{ textDecoration: 'underline' }}>个人中心</a> 维护，分析自动带入
            </span>
          </div>
        ) : profileErr ? (
          <p className="sub" style={{ marginTop: 8, color: 'var(--red)' }}>⚠ 个人档案加载失败：{profileErr}——分析依赖档案中的时间线与目标，请刷新页面重试。</p>
        ) : (
          <p className="sub" style={{ marginTop: 8 }}><span className="spin" /> 正在读取个人档案…</p>
        )}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
          <select value={goal} onChange={(e) => setGoal(e.target.value)} style={{ maxWidth: 180 }}>
            {COMPETE_GOALS.map((g) => <option key={g} value={g}>目标路径：{g}</option>)}
          </select>
          <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center', cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
            追加 AI 备赛策略
          </label>
          <button className="btn" disabled={busy || !profile} onClick={analyze} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> 分析中{useLlm ? '（含模型策略）' : ''}…</> : <><Icon name="quiz" size={14} /> 分析该参加哪些竞赛</>}
          </button>
          <button className="btn ghost" onClick={() => setCatalogOpen((o) => !o)} style={{ flex: 'none' }}>
            {catalogOpen ? '收起完整目录' : `浏览完整目录${catalog ? `（${catalog.length} 项）` : ''}`}
          </button>
        </div>
      </div>

      {catalogOpen && (
        <div className="card" style={{ marginBottom: 18 }}>
          <h3>内置竞赛目录</h3>
          <p className="sub">各竞赛在四条目标路径下的价值评分（1-5，越高越值得），专业标注表示强对口方向。</p>
          {!catalog ? <p className="sub"><span className="spin" /> 加载中…</p> : (
            <table className="quiz" style={{ marginTop: 8 }}>
              <thead><tr><th>竞赛</th><th>级别</th><th>赛期</th><th>备赛</th><th>对口专业</th><th>考研</th><th>推免</th><th>就业</th><th>出国</th></tr></thead>
              <tbody>
                {catalog.map((c) => (
                  <tr key={c.id}>
                    <td><b>{c.name}</b><div className="sub">{c.team}</div></td>
                    <td><span className="badge">{c.tier}</span></td>
                    <td className="sub">{c.window_label}</td>
                    <td>{c.prep_weeks} 周</td>
                    <td className="sub">{c.majors.join('、')}</td>
                    {['考研', '推免', '就业', '出国'].map((g) => (
                      <td key={g}>
                        <b style={{ color: (c.goals[g] || 0) >= 4 ? 'var(--green)' : undefined }}>{c.goals[g] || '—'}</b>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {result && (
        <div className="card">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>分析结果 · {result.goal_label}</h3>
            {result.months_left != null && (
              <span className="badge expert">距截止约 {result.months_left} 个月</span>
            )}
            {result.deadline && <span className="badge">截止 {result.deadline}</span>}
          </div>
          <p className="sub" style={{ marginTop: 6 }}>
            {result.target ? `目标去向：${result.target}。` : ''}
            {result.deadline_source}。目标院校的具体加分/复试政策每年可能调整，以官方最新文件为准。
          </p>

          {tierBlock('至少参加 · 强烈推荐', 'ok', result.tier1)}
          {tierBlock('有余力 · 值得考虑', 'mid', result.tier2)}
          {tierBlock('谨慎投入 · 时间或回报不匹配', 'bad', result.tier3)}

          {result.strategy_md && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--hairline)', paddingTop: 12 }}>
              <h3>AI 备赛策略</h3>
              <Md>{result.strategy_md}</Md>
            </div>
          )}
          {result.strategy_error && (
            <p className="sub" style={{ marginTop: 10, color: 'var(--orange)' }}>◎ {result.strategy_error}</p>
          )}
        </div>
      )}
    </>
  )
}
