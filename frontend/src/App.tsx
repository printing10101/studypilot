// 应用外壳：顶栏 + 侧边栏导航 + 视图路由。
// 各界面实现拆在 views/ 下：
//   空间级：今日学习 / 学习对话 / 测验 / 闪卡 / 学习计划 / 学习分析
//   全局级：个人中心 / 资料中心（知识库+教材书库合并）/ 学涯中心（学涯规划+成长手册合并）/ 校园网 / 模型设置
import { useEffect, useState } from 'react'
import { api, Space } from './api'
import { Icon } from './ui'
import { useUX } from './ux'
import { TodayView } from './views/TodayView'
import { ChatView } from './views/ChatView'
import { QuizView } from './views/QuizView'
import { CardsView } from './views/CardsView'
import { PlanView } from './views/PlanView'
import { AnalyticsView } from './views/AnalyticsView'
import { LibraryView } from './views/LibraryView'
import { ProfileView } from './views/ProfileView'
import { CareerView } from './views/CareerView'
import { CampusView } from './views/CampusView'
import { SettingsView } from './views/SettingsView'

type Tab = 'profile' | 'library' | 'campus' | 'career' | 'settings'
  | 'today' | 'chat' | 'quiz' | 'cards' | 'plan' | 'analytics'

const SPACE_TABS: [Tab, string, string][] = [
  ['today', '今日学习', 'sun'],
  ['chat', '学习对话', 'chat'],
  ['quiz', '测验练习', 'quiz'],
  ['cards', '闪卡', 'cards'],
  ['plan', '学习计划', 'plan'],
  ['analytics', '学习分析', 'brain'],
]
const GLOBAL_TABS: [Tab, string, string][] = [
  ['profile', '个人中心', 'user'],
  ['library', '资料中心', 'book'],
  ['career', '学涯中心', 'compass'],
  ['campus', '校园网', 'wifi'],
  ['settings', '模型设置', 'spark'],
]

function App() {
  const { toast, confirm: uxConfirm, prompt: uxPrompt } = useUX()
  const [spaces, setSpaces] = useState<Space[]>([])
  const [sid, setSid] = useState<string>('')
  const [tab, setTab] = useState<Tab>('today')
  const [health, setHealth] = useState<{ llm: boolean; model: string } | null>(null)
  const [dueCount, setDueCount] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const refreshSpaces = () => api.listSpaces().then(setSpaces).catch(() => {})
  const refreshHealth = () => api.health().then(setHealth).catch(() => setHealth({ llm: false, model: '未连接' }))
  useEffect(() => {
    refreshSpaces()
    refreshHealth()
    // 先开应用后启动 llama-server 是常见顺序：健康状态定期复查，不再只在启动时查一次
    const t = setInterval(refreshHealth, 60 * 1000)
    const onVis = () => { if (document.visibilityState === 'visible') refreshHealth() }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVis) }
  }, [])

  // 到期复习提醒：切空间/每 5 分钟检查一次，到期数变化时尝试系统通知
  useEffect(() => {
    if (!sid) { setDueCount(0); return }
    let stop = false
    const last = { n: -1 }
    const check = () => api.reviewDue(sid).then((r) => {
      if (stop) return
      setDueCount(r.due.length)
      if (r.due.length > 0 && last.n !== r.due.length && 'Notification' in window
        && Notification.permission === 'granted') {
        try { new Notification('StudyPilot 复习提醒', { body: `有 ${r.due.length} 个知识点到了间隔复习时间` }) } catch { /* 通知失败静默 */ }
      }
      last.n = r.due.length
    }).catch(() => {})
    check()
    const t = setInterval(check, 5 * 60 * 1000)
    return () => { stop = true; clearInterval(t) }
  }, [sid])

  const enableNotifications = async () => {
    if (!('Notification' in window)) { toast('info', '当前环境不支持系统通知'); return }
    const p = await Notification.requestPermission()
    if (p === 'granted') {
      try { new Notification('StudyPilot 复习提醒已开启', { body: '知识点到期时会在这里提醒你' }) } catch { /* 忽略 */ }
    }
  }

  const newSpace = async () => {
    const name = await uxPrompt({ title: '新建课程空间', label: '课程名称', placeholder: '如：清华普通物理' })
    if (!name) return
    const s = await api.createSpace(name, '')
    await refreshSpaces()
    setSid(s.id)
    setTab('today')
    toast('success', `已创建「${name}」，去资料中心上传讲义开始吧`)
  }

  const nav = (t: string) => { setTab(t as Tab); setSidebarOpen(false) }
  const openSpace = (id: string) => { setSid(id); setTab('today'); setSidebarOpen(false) }

  const renderView = () => {
    if (tab === 'profile') return <ProfileView spaces={spaces} onOpenSpace={openSpace} />
    if (tab === 'settings') return <SettingsView />
    if (tab === 'career') return <CareerView spaces={spaces} currentSid={sid} onGoto={nav} />
    if (tab === 'library') return <LibraryView spaces={spaces} currentSid={sid} />
    if (tab === 'campus') return <CampusView />
    if (!sid) {
      return (
        <div className="content">
          <div className="hero">
            <div className="hero-badge"><Icon name="spark" size={13} /> 本地 AI 助教 · 完全离线</div>
            <h1 className="hero-title">把你的电脑变成<br /><em>一位懂你的私人助教</em></h1>
            <p className="hero-sub">
              上传讲义，构建私有知识库；答疑带引用、出题判卷、错题沉淀成长期记忆。<br />
              所有数据与推理都在本机完成，无需联网，不计 token。
            </p>
            <button className="btn" style={{ fontSize: 15, padding: '12px 32px', marginBottom: 36 }}
              onClick={newSpace}>
              开始使用 <Icon name="arrow" size={16} />
            </button>
            <div className="hero-steps">
              {[
                ['STEP 1', '建空间', '为每门课创建独立空间'],
                ['STEP 2', '传讲义', 'PDF / PPT 自动向量化入库'],
                ['STEP 3', '对话练习', '答疑 · 出题 · 判卷 · 总结'],
                ['STEP 4', '记忆生长', '错题薄弱点进入长期记忆'],
              ].map(([no, t, d]) => (
                <div key={no} className="hero-step">
                  <span className="no">{no}</span><b>{t}</b><span>{d}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )
    }
    switch (tab) {
      case 'chat': return <ChatView sid={sid} />
      case 'quiz': return <QuizView sid={sid} />
      case 'cards': return <CardsView sid={sid} />
      case 'plan': return <PlanView sid={sid} />
      case 'analytics': return <AnalyticsView sid={sid} onGoto={nav} />
      default: return <TodayView sid={sid} onGoto={nav} />
    }
  }

  return (
    <>
      <div className="aurora" />
      <div className="topbar">
        <button className="btn ghost small mobile-menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}
          style={{ padding: '6px 10px' }} aria-label="菜单">
          ☰
        </button>
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
      </div>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}
      <div className="layout">
        <div className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
          <div className="nav-section">课程空间</div>
          {spaces.map((s) => (
            <div key={s.id} className={`nav-item ${sid === s.id ? 'active' : ''}`}
              onClick={() => openSpace(s.id)}>
              <Icon name="layers" />{s.name}
            </div>
          ))}
          <button className="side-btn" onClick={newSpace}><Icon name="plus" size={14} /> 新建课程空间</button>

          {sid && (
            <>
              <div className="nav-section">空间功能</div>
              {SPACE_TABS.map(([t, label, ic]) => (
                <div key={t} className={`nav-item ${tab === t ? 'active' : ''}`} onClick={() => nav(t)}>
                  <Icon name={ic} />{label}
                  {t === 'today' && dueCount > 0 && <span className="badge expert" style={{ marginLeft: 'auto' }}>{dueCount} 到期</span>}
                </div>
              ))}
            </>
          )}

          <div className="nav-section">通用</div>
          {GLOBAL_TABS.map(([t, label, ic]) => (
            <div key={t} className={`nav-item ${tab === t ? 'active' : ''}`} onClick={() => nav(t)}>
              <Icon name={ic} />{label}
            </div>
          ))}

          {sid && (
            <>
              <div className="nav-section">管理</div>
              <button className="btn danger small" style={{ width: '100%', justifyContent: 'center' }}
                onClick={async () => {
                  if (await uxConfirm({ title: '删除课程空间', message: '删除后所有数据不可恢复。', confirmText: '删除', danger: true })) {
                    await api.deleteSpace(sid); setSid(''); refreshSpaces()
                    toast('success', '空间已删除')
                  }
                }}><Icon name="trash" size={13} /> 删除当前空间</button>
            </>
          )}
        </div>

        <div className="main">
          {sid && dueCount > 0 && (
            <div className="card" style={{ margin: '14px 18px 0', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, borderColor: 'var(--orange)' }}>
              <span className="badge expert">⏰ 间隔复习</span>
              <b>{dueCount} 个知识点到了复习时间</b>
              <span className="sub">按 FSRS 记忆曲线，现在复习留存率最高</span>
              <div style={{ flex: 1 }} />
              {'Notification' in window && Notification.permission === 'default' && (
                <button className="btn small" onClick={enableNotifications} title="授权系统通知后，到期提醒可在应用外弹出">
                  🔔 开启系统通知
                </button>
              )}
              <button className="btn small" onClick={() => nav('today')}>去看今日清单</button>
            </div>
          )}
          {renderView()}
        </div>
      </div>
    </>
  )
}

export default App
