// 校园网：网络状态感知 + 校园信息自动同步（教务处/学校/新闻网/图书馆/学院）
import { useEffect, useState } from 'react'
import { api, CampusItem, CampusStatus } from '../api'
import { EmptyState, Icon } from '../ui'
import { useUX } from '../ux'

export function CampusView() {
  const { toast } = useUX()
  const [status, setStatus] = useState<CampusStatus | null>(null)
  const [items, setItems] = useState<CampusItem[]>([])
  const [source, setSource] = useState('')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState('')
  const [autoSync, setAutoSync] = useState(true)
  const [intervalMin, setIntervalMin] = useState(30)

  const applyStatus = (s: CampusStatus) => {
    setStatus(s); setAutoSync(s.config.auto_sync); setIntervalMin(s.config.interval_min)
  }
  const refresh = (force = false) => api.campusStatus(force).then(applyStatus).catch(() => {})
  const loadItems = (src: string, q: string) =>
    api.campusItems(src, 100, q).then((r) => setItems(r.items)).catch(() => setItems([]))
  useEffect(() => { refresh() }, [])
  useEffect(() => {
    const t = setTimeout(() => loadItems(source, query), query ? 300 : 0)
    return () => clearTimeout(t)
  }, [source, query]) // eslint-disable-line react-hooks/exhaustive-deps

  const syncNow = async () => {
    setBusy('sync')
    try {
      const r = await api.campusSync()
      if (r.skipped) toast('warn', '当前无网络，稍后再试')
      else toast('success', `同步完成，新增 ${r.added} 条校园信息`)
      refresh(); loadItems(source, query)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const redetect = async () => {
    setBusy('detect')
    try { applyStatus(await api.campusStatus(true)) } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const saveCfg = async () => {
    setBusy('save')
    try { applyStatus(await api.campusConfig({ auto_sync: autoSync, interval_min: intervalMin })); toast('success', '同步设置已保存') }
    catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const net = status?.network
  const stateColor = net?.state === 'campus' ? 'var(--green)'
    : net?.state === 'campus_likely' ? 'var(--orange)'
      : net?.state === 'offline' ? 'var(--red)' : 'var(--muted)'
  const sourceName = Object.fromEntries((status?.config.sources || []).map((s) => [s.id, s.name]))
  const fmtTs = (ts: number) => new Date(ts * 1000).toLocaleString()

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>校园网 · 状态与自动同步</h3>
        <p className="sub">
          连着校园网时，后台自动抓取全校与学院的学习相关信息：教务处通知（四六级 / 计算机等级 /
          考试安排 / 选课）、学校通知公告、示例大学新闻网、图书馆资源动态、学院通知与新闻。
          教务成绩、个人借阅等需要登录的内容不做自动抓取。
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '14px 0 6px', flexWrap: 'wrap' }}>
          <span className="chip" style={{ paddingLeft: 12, paddingRight: 12 }}>
            <span className="pulse" style={{ background: stateColor, animation: net?.state === 'offline' ? 'none' : undefined }} />
            {net?.label || '检测中…'}
          </span>
          <span className="sub" style={{ maxWidth: 560 }}>{net?.detail}</span>
        </div>
        <div className="sub" style={{ marginBottom: 14 }}>
          校园站点 {net?.latency_campus_ms != null ? `${net.latency_campus_ms} ms` : '不可达'}
          {' · '}外网 {net?.latency_external_ms != null ? `${net.latency_external_ms} ms` : '不可达'}
          {status?.last_sync
            ? ` · 上次同步 ${fmtTs(status.last_sync.ts)}，新增 ${status.last_sync.added} 条${status.last_sync.skipped ? '（当时离线，已跳过）' : ''}`
            : ' · 尚未同步过'}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn ghost" disabled={!!busy} onClick={redetect}>
            {busy === 'detect' ? <><span className="spin" /> 检测中</> : '重新检测'}
          </button>
          <button className="btn" disabled={!!busy} onClick={syncNow}>
            {busy === 'sync' ? <><span className="spin" /> 同步中</> : '立即同步'}
          </button>
          <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', marginLeft: 8 }}>
            <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center', cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={autoSync} onChange={(e) => setAutoSync(e.target.checked)} /> 自动同步
            </label>
            <input type="number" min={5} max={1440} value={intervalMin} style={{ width: 76 }}
              onChange={(e) => setIntervalMin(Number(e.target.value) || 30)} />
            <span className="sub">分钟/次</span>
            <button className="btn ghost small" disabled={!!busy} onClick={saveCfg}>
              {busy === 'save' ? <><span className="spin" /> 保存中</> : '保存设置'}
            </button>
          </span>
        </div>
        <p className="sub" style={{ marginTop: 14 }}>
          常用入口：<a href="https://findexample.libsp.cn" target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'underline' }}>示例大学馆藏统一检索</a>
          {' · '}<a href="http://mech.example.edu.cn" target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'underline' }}>机械学院官网</a>
          {' · '}<a href="http://www.example.edu.cn" target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'underline' }}>示例大学主页</a>
          {' · '}在校园网内检索馆藏/访问教务前，记得先完成校园网认证
        </p>
      </div>

      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>校园信息{status ? `（共 ${status.total} 条）` : ''}</h3>
          <div style={{ flex: 1 }} />
          <Icon name="wifi" size={15} />
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
          <input type="text" style={{ maxWidth: 300 }} placeholder="按标题搜索，如：四六级、考试、讲座"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && <button className="btn ghost small" onClick={() => setQuery('')}>清除</button>}
          {query && <span className="sub">找到 {items.length} 条</span>}
        </div>
        <div className="mode-tabs" style={{ marginTop: 10 }}>
          <button className={`mode-tab ${source === '' ? 'active' : ''}`} onClick={() => setSource('')}>
            全部{status ? ` ${status.total}` : ''}
          </button>
          {(status?.config.sources || []).map((s) => (
            <button key={s.id} className={`mode-tab ${source === s.id ? 'active' : ''}`} onClick={() => setSource(s.id)}>
              {s.name}{status?.counts[s.id] ? ` ${status.counts[s.id]}` : ''}
            </button>
          ))}
        </div>
        {status && status.total === 0 ? (
          <EmptyState icon="wifi" title="还没有校园信息"
            desc="点「立即同步」抓一次全校与学院的信息源（教务处通知、学校公告、图书馆、学院动态…）；之后连着校园网会按设定的间隔自动更新。"
            action="立即同步" onAction={syncNow} />
        ) : (
          <div className="campus-list" style={{ marginTop: 8 }}>
            {items.map((it) => (
              <a key={it.id} href={it.url} target="_blank" rel="noopener noreferrer">
                <span className="sub" style={{ flex: 'none', width: 88, fontSize: 12 }}>{it.published || '—'}</span>
                <span style={{ flex: 1, fontSize: 13.5, lineHeight: 1.5 }}>{it.title}</span>
                {source === '' && <span className="badge" style={{ flex: 'none', fontSize: 11 }}>{sourceName[it.source] || it.source}</span>}
              </a>
            ))}
            {status && status.total > 0 && !items.length && (
              <div className="sub" style={{ padding: '16px 4px' }}>该筛选条件下没有内容——换个关键词，或点「立即同步」更新</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
