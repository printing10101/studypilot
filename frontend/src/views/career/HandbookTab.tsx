// 子页签⑤：成长手册（档案来自「个人中心」，这里不再重复表单）。
import { useEffect, useState } from 'react'
import { api, Handbook, HandbookMeta, Space, StudentProfile } from '../../api'
import { Icon, downloadMd } from '../../ui'
import { Md } from '../../md'
import { useUX } from '../../ux'

export function HandbookTab({ profile, profileErr, currentSid, spaces, onGoto }: {
  profile: StudentProfile | null
  profileErr: string
  currentSid: string
  spaces: Space[]
  onGoto: (t: string) => void
}) {
  const { toast, confirm: uxConfirm } = useUX()
  const [handbooks, setHandbooks] = useState<HandbookMeta[]>([])
  const [currentHb, setCurrentHb] = useState<Handbook | null>(null)
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api.handbooks().then(setHandbooks).catch(() => {})
  }, [])

  const generateHandbook = async () => {
    if (!profile) return
    if (!profile.target_school) { toast('warn', '还没有目标院校——先到「个人中心」的档案里填写'); return }
    setBusy('handbook')
    try {
      const h = await api.generateHandbook({ ...profile, space_id: currentSid || '' })
      setCurrentHb(h)
      api.handbooks().then(setHandbooks).catch(() => {})
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const openHandbook = async (id: string) => {
    try { setCurrentHb(await api.handbook(id)) } catch (e: any) { toast('error', '打开失败：' + (e.message || '未知错误')) }
  }
  const removeHandbook = async (id: string) => {
    if (!(await uxConfirm({ title: '删除手册', message: '此操作不可恢复。', confirmText: '删除', danger: true }))) return
    try {
      await api.deleteHandbook(id)
      if (currentHb?.id === id) setCurrentHb(null)
      api.handbooks().then(setHandbooks).catch(() => {})
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>成长手册 · 升学战略引擎</h3>
        <p className="sub">
          基于真实院校政策（学籍/重修/推免/招生要求，每条结论标注官方来源）× 你的处境 × StudyPilot 掌握度数据，
          生成直达目标的分阶段行动手册。政策每年可能调整，关键节点以官方最新文件为准。
        </p>
        {profile ? (
          <>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 4px' }}>
              <span className="badge">本科：{[profile.current_school, profile.major, profile.year].filter(Boolean).join(' · ') || '（未填写）'}</span>
              <span className="badge">目标：{[profile.goal_type, profile.target_school, profile.target_major].filter(Boolean).join(' · ') || '（未填写）'}</span>
              {profile.timeline && <span className="badge">时间线：{profile.timeline}</span>}
              {profile.flags.map((f) => <span key={f} className="badge expert">{f}</span>)}
            </div>
            <p className="sub" style={{ marginTop: 6 }}>
              以上来自「个人中心」的档案。要修改学校、专业、目标或补充经历，<a href="#" onClick={(e) => { e.preventDefault(); onGoto('profile') }} style={{ textDecoration: 'underline' }}>去个人中心修改</a>，生成手册时会自动带入。
            </p>
          </>
        ) : profileErr ? (
          <p className="sub" style={{ marginTop: 8, color: 'var(--red)' }}>
            ⚠ 个人档案加载失败：{profileErr}。
            <button className="btn ghost small" onClick={() => window.location.reload()} style={{ marginLeft: 6 }}>刷新重试</button>
            或到「个人中心」手动检查。
          </p>
        ) : (
          <p className="sub" style={{ marginTop: 8 }}><span className="spin" /> 正在读取个人档案…</p>
        )}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
          <button className="btn" disabled={busy === 'handbook' || !profile} onClick={generateHandbook}>
            {busy === 'handbook'
              ? <><span className="spin" /> 正在结合政策库生成…（约1分钟）</>
              : <><Icon name="compass" size={14} /> 生成成长手册</>}
          </button>
          {currentSid && profile && (
            <span className="sub">将结合当前空间「{spaces.find((s) => s.id === currentSid)?.name}」的掌握度数据</span>
          )}
        </div>
      </div>

      {currentHb && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>{currentHb.title}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn ghost small" onClick={() => downloadMd('成长手册', currentHb.content)}>
                <Icon name="book" size={12} /> 导出 Markdown
              </button>
              <button className="btn ghost small" onClick={() => setCurrentHb(null)}>收起</button>
            </div>
          </div>
          <Md>{currentHb.content}</Md>
        </div>
      )}

      {handbooks.length > 0 && (
        <div className="card">
          <h3>历史手册</h3>
          <table className="quiz" style={{ marginTop: 10 }}>
            <tbody>
              {handbooks.map((h) => (
                <tr key={h.id}>
                  <td style={{ cursor: 'pointer' }} onClick={() => openHandbook(h.id)}><b>{h.title}</b></td>
                  <td style={{ width: 150, color: 'var(--muted)', fontSize: 12 }}>
                    {new Date(h.created_at * 1000).toLocaleDateString()}</td>
                  <td style={{ width: 60 }}>
                    <button className="btn danger small" onClick={() => removeHandbook(h.id)} aria-label={`删除手册《${h.title}》`}><Icon name="trash" size={12} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
