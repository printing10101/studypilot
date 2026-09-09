// 图标与通用小组件
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
