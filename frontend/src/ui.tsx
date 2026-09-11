// 图标与通用小组件
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { PlanTask } from './api'

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  const p = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  switch (name) {
    case 'compass': return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></svg>
    case 'chat': return <svg {...p}><path d="M21 12a8 8 0 0 1-8 8H4l2.5-2.5A8 8 0 1 1 21 12z" /></svg>
    case 'book': return <svg {...p}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5v13z" /><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" /></svg>
    case 'quiz': return <svg {...p}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="m8.5 10 2 2 4-4.5" /><path d="M8 16h8" /></svg>
    case 'brain': return <svg {...p}><circle cx="12" cy="12" r="3" /><path d="M12 2v4m0 12v4M2 12h4m12 0h4" /><circle cx="12" cy="12" r="9" strokeDasharray="3 3" /></svg>
    case 'plus': return <svg {...p}><path d="M12 5v14M5 12h14" /></svg>
    case 'trash': return <svg {...p}><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m3 0-1 13a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1L6 7" /></svg>
    case 'send': return <svg {...p}><path d="m5 12 14-7-4 7 4 7z" /></svg>
    case 'spark': return <svg {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="M19 16l.9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9z" /></svg>
    case 'user': return <svg {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5" /></svg>
    case 'layers': return <svg {...p}><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5" /></svg>
    case 'cards': return <svg {...p}><rect x="3" y="7" width="13" height="14" rx="2" /><path d="M8 4h11a2 2 0 0 1 2 2v11" /></svg>
    case 'plan': return <svg {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="m8.5 12 2 2 5-5" /><path d="M8 17h8" /></svg>
    case 'sun': return <svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" /></svg>
    case 'upload': return <svg {...p}><path d="M12 16V4m0 0-4 4m4-4 4 4" /><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
    case 'download': return <svg {...p}><path d="M12 4v12m0 0-4-4m4 4 4-4" /><path d="M4 18v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
    case 'chart': return <svg {...p}><path d="M4 20V10m6 10V4m6 16v-7m4 7H2" /></svg>
    case 'check': return <svg {...p}><path d="m5 12 5 5L20 7" /></svg>
    case 'close': return <svg {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>
    case 'info': return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 8v.01M12 11v5" /></svg>
    case 'warn': return <svg {...p}><path d="M12 3 2 21h20L12 3z" /><path d="M12 10v4m0 3v.01" /></svg>
    case 'wifi': return <svg {...p}><path d="M2.5 9a15 15 0 0 1 19 0" /><path d="M5.5 12.5a10 10 0 0 1 13 0" /><path d="M8.6 16a5.5 5.5 0 0 1 6.8 0" /><circle cx="12" cy="19.3" r="1" /></svg>
    case 'arrow': return <svg {...p}><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
  }
  return null
}

export function Typing() {
  return <span className="typing"><i /><i /><i /></span>
}

export function downloadMd(kind: string, text: string) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `studypilot-${kind}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

// ============ Toast 通知系统 ============

type ToastType = 'success' | 'error' | 'info' | 'warn'
interface ToastItem { id: number; type: ToastType; text: string }

const ToastCtx = createContext<(type: ToastType, text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

let _toastId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const push = useCallback((type: ToastType, text: string) => {
    const id = ++_toastId
    setToasts((t) => [...t.slice(-4), { id, type, text }])
    const timer = setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id))
      timers.current.delete(id)
    }, type === 'error' ? 5000 : 3000)
    timers.current.set(id, timer)
  }, [])

  useEffect(() => () => { timers.current.forEach((t) => clearTimeout(t)) }, [])

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}
            onClick={() => { setToasts((s) => s.filter((x) => x.id !== t.id)); const tm = timers.current.get(t.id); if (tm) clearTimeout(tm) }}>
            <Icon name={t.type === 'success' ? 'check' : t.type === 'error' ? 'close' : t.type === 'warn' ? 'warn' : 'info'} size={15} />
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

// ============ Modal 对话框 ============

interface ModalProps {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  width?: number
}
export function Modal({ open, title, onClose, children, width = 440 }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" style={{ maxWidth: width }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>{title}</b>
          <button className="modal-x" onClick={onClose}><Icon name="close" size={14} /></button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

// ============ Confirm 确认框 ============

interface ConfirmProps {
  open: boolean
  title: string
  message: string
  confirmText?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}
export function ConfirmDialog({ open, title, message, confirmText = '确认', danger, onConfirm, onCancel }: ConfirmProps) {
  return (
    <Modal open={open} title={title} onClose={onCancel} width={400}>
      <p style={{ margin: '0 0 18px', color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{message}</p>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button className="btn ghost small" onClick={onCancel}>取消</button>
        <button className={`btn small ${danger ? 'danger' : ''}`} onClick={onConfirm}>{confirmText}</button>
      </div>
    </Modal>
  )
}

// ============ Prompt 输入框 ============

interface PromptProps {
  open: boolean
  title: string
  label?: string
  placeholder?: string
  defaultValue?: string
  multiline?: boolean
  onConfirm: (value: string) => void
  onCancel: () => void
}
export function PromptDialog({ open, title, label, placeholder, defaultValue = '', multiline, onConfirm, onCancel }: PromptProps) {
  const [val, setVal] = useState(defaultValue)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)
  useEffect(() => { if (open) { setVal(defaultValue); setTimeout(() => inputRef.current?.focus(), 50) } }, [open, defaultValue])
  const submit = () => { const v = val.trim(); if (v) { onConfirm(v) } }
  return (
    <Modal open={open} title={title} onClose={onCancel} width={440}>
      {label && <label style={{ display: 'block', fontSize: 13, color: 'var(--muted)', marginBottom: 8 }}>{label}</label>}
      {multiline ? (
        <textarea ref={inputRef as React.RefObject<HTMLTextAreaElement>} value={val}
          onChange={(e) => setVal(e.target.value)} placeholder={placeholder} rows={4}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit() }} />
      ) : (
        <input ref={inputRef as React.RefObject<HTMLInputElement>} value={val}
          onChange={(e) => setVal(e.target.value)} placeholder={placeholder}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
      )}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
        <button className="btn ghost small" onClick={onCancel}>取消</button>
        <button className="btn small" disabled={!val.trim()} onClick={submit}>确认</button>
      </div>
    </Modal>
  )
}

// ============ Select 选择框 ============

interface SelectProps {
  open: boolean
  title: string
  message?: string
  options: { value: string; label: string; sub?: string }[]
  onConfirm: (value: string) => void
  onCancel: () => void
}
export function SelectDialog({ open, title, message, options, onConfirm, onCancel }: SelectProps) {
  return (
    <Modal open={open} title={title} onClose={onCancel} width={440}>
      {message && <p style={{ margin: '0 0 12px', color: 'var(--muted)', fontSize: 13 }}>{message}</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflowY: 'auto' }}>
        {options.map((opt) => (
          <button key={opt.value} className="select-opt" onClick={() => onConfirm(opt.value)}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>{opt.label}</div>
              {opt.sub && <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{opt.sub}</div>}
            </div>
            <Icon name="arrow" size={14} />
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
        <button className="btn ghost small" onClick={onCancel}>取消</button>
      </div>
    </Modal>
  )
}

// ============ 空状态引导 ============

export function EmptyState({ icon, title, desc, action, onAction }: {
  icon: string; title: string; desc: string
  action?: string; onAction?: () => void
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={icon} size={28} /></div>
      <h3 style={{ margin: '12px 0 6px', fontSize: 16 }}>{title}</h3>
      <p style={{ margin: '0 0 18px', color: 'var(--muted)', fontSize: 13, maxWidth: 360 }}>{desc}</p>
      {action && onAction && (
        <button className="btn" onClick={onAction}>
          {action} <Icon name="arrow" size={14} />
        </button>
      )}
    </div>
  )
}

// ============ 计划任务行（今日清单 / 学习计划共用） ============

export function PlanTaskRow({ t, overdue, onToggle, onDate }: {
  t: PlanTask
  overdue?: boolean
  onToggle: (t: PlanTask) => void
  onDate?: (t: PlanTask, date: string) => void
}) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '9px 0', borderBottom: '1px solid var(--hairline)' }}>
      <input type="checkbox" checked={!!t.done} onChange={() => onToggle(t)} style={{ marginTop: 4 }} />
      <div style={{ flex: 1, fontSize: 13 }}>
        <div style={t.done ? { textDecoration: 'line-through', color: 'var(--muted)' } : undefined}>
          {t.method && <span className="badge" style={{ marginRight: 6 }}>{t.method}</span>}
          {t.content}
        </div>
        {t.accept && <div style={{ color: 'var(--muted)', marginTop: 3 }}>验收：{t.accept}</div>}
        {t.due_date && (
          <div style={{ marginTop: 4 }}><span className="badge expert">⏱ {t.due_date} 前完成</span></div>
        )}
        {t.points.length > 0 && (
          <div style={{ marginTop: 4 }}>{t.points.map((p, i) => <span key={i} className="badge" style={{ margin: 1 }}>{p}</span>)}</div>
        )}
      </div>
      {overdue && !t.done && (
        <span className="badge expert" style={{ color: 'var(--red)', borderColor: 'rgba(238,154,169,.4)', flex: 'none' }}>逾期</span>
      )}
      {onDate && (
        <input type="date" style={{ maxWidth: 148, flex: 'none' }} value={t.due_date || ''} title="调整截止日期"
          onChange={(e) => onDate(t, e.target.value)} />
      )}
    </div>
  )
}

// ============ 页内子页签（测验 / 学涯中心 / 学习分析共用） ============

export function SubTabs({ tabs, value, onChange }: {
  tabs: [string, string][]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="mode-tabs" style={{ marginBottom: 16 }}>
      {tabs.map(([v, label]) => (
        <button key={v} className={`mode-tab ${value === v ? 'active' : ''}`} onClick={() => onChange(v)}>{label}</button>
      ))}
    </div>
  )
}
