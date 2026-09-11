// 个人中心：全应用唯一的档案表单（原成长手册/学涯规划里的重复表单已移除）+ 跨空间学习总览 + 迁移机会
import { useEffect, useState } from 'react'
import { api, LearnerPersonaMeta, Space, SpaceOverview, StudentProfile, SyllabusSchool, TransferOpportunity } from '../api'
import { Icon } from '../ui'
import { useUX } from '../ux'

const FLAGS = ['重修', '挂科', '跨考', '无科研经历', '无竞赛奖项', '英语未过级']
const RANKS = ['', '前10%', '前20%', '前30%', '前50%', '50%以后']

export function ProfileView({ spaces, onOpenSpace }: { spaces: Space[]; onOpenSpace: (id: string) => void }) {
  const { toast } = useUX()
  const [form, setForm] = useState<StudentProfile>({
    current_school: '', major: '', year: '', rank_hint: '', flags: [], goal_type: '考研',
    target_school: '', target_major: '', timeline: '', notes: '', learner_personas: [],
  })
  const [savedAt, setSavedAt] = useState(0)
  const [overview, setOverview] = useState<SpaceOverview[] | null>(null)
  const [transfers, setTransfers] = useState<TransferOpportunity[]>([])
  const [busy, setBusy] = useState(false)
  const [schoolList, setSchoolList] = useState<SyllabusSchool[]>([])
  const [majorList, setMajorList] = useState<string[]>([])
  const [personaList, setPersonaList] = useState<LearnerPersonaMeta[]>([])

  useEffect(() => {
    api.profile().then((p) => {
      setForm({ ...p, learner_personas: p.learner_personas || [] })
      setSavedAt(p.updated_at || 0)
    }).catch(() => {})
    api.profileOverview().then((o) => setOverview(o.spaces)).catch(() => {})
    api.transferOpportunities().then(setTransfers).catch(() => setTransfers([]))
    api.schools().then(setSchoolList).catch(() => {})
    api.learnerPersonas().then((r) => setPersonaList(r.personas)).catch(() => {})
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

  const save = async () => {
    setBusy(true)
    try {
      const p = await api.saveProfile(form)
      setForm(p); setSavedAt(p.updated_at || Date.now() / 1000)
      toast('success', '档案已保存，成长手册 / 学涯规划会自动带入')
    } catch (e: any) { toast('error', e.message) }
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
          你的学生名片，全应用只有这一处：成长手册、学涯规划、复习提醒都会自动读取。
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
        <div style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <b style={{ fontSize: 13 }}>学习者画像</b>
            <span className="sub">可多选；不选时会按测验/到期/疲劳等行为自动推断。只调方法侧重与任务写法。</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            {personaList.map((p) => {
              const on = (form.learner_personas || []).includes(p.id)
              return (
                <button key={p.id} className={`fb-btn ${on ? 'fb-on' : ''}`}
                  title={p.blurb}
                  onClick={() => {
                    const cur = form.learner_personas || []
                    set('learner_personas', on ? cur.filter((x) => x !== p.id) : [...cur, p.id])
                  }}>
                  {on ? '✓ ' : ''}{p.name}
                </button>
              )
            })}
          </div>
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

      <div className="card" style={{ marginBottom: 18 }}>
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

      <div className="card">
        <h3>跨空间迁移机会</h3>
        <p className="sub">课程 A 里已掌握的概念，和课程 B 里未掌握的近名概念相关——先学 B 的这个概念，可以借 A 的底子加速。</p>
        {transfers.length > 0 ? (
          <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
            {transfers.slice(0, 8).map((t, i) => (
              <div key={i} style={{ border: '1px solid var(--hairline)', borderRadius: 12, padding: '10px 14px', fontSize: 13, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <Icon name="spark" size={14} />
                <span><b>{t.source_space}</b> 的「<b>{t.source_concept}</b>」已掌握（{Math.round(t.source_mastery * 100)}%）</span>
                <span className="sub">→</span>
                <span>可加速 <b>{t.target_space}</b> 的「<b>{t.target_concept}</b>」（当前 {Math.round(t.target_mastery * 100)}%）</span>
                <span className="badge">相似度 {Math.round(t.similarity * 100)}%</span>
                <div style={{ flex: 1 }} />
                <button className="btn ghost small" onClick={() => onOpenSpace(t.target_space_id)}>去学习</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="sub" style={{ marginTop: 10 }}>暂未发现可迁移的概念关联——多建几个课程空间并积累掌握度后会出现。</p>
        )}
      </div>
    </div>
  )
}
