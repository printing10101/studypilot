// 闪卡：FSRS 间隔复习刷卡流 + Anki 牌组导入导出
import { useEffect, useRef, useState } from 'react'
import { api, Flashcard, runSkillStream } from '../api'
import { Icon } from '../ui'
import { Md } from '../md'
import { useUX } from '../ux'
// 间隔秒数 → 人话（FSRS 刷卡按钮的间隔预告用）
function fmtInterval(sec?: number): string {
  if (!sec || sec <= 0) return ''
  const m = sec / 60
  if (m < 60) return `${Math.max(1, Math.round(m))}分钟`
  const h = m / 60
  if (h < 24) return `${Math.round(h)}小时`
  const d = h / 24
  if (d < 31) return `${Math.round(d)}天`
  if (d < 365) return `${(d / 30.4).toFixed(1)}个月`
  return `${(d / 365).toFixed(1)}年`
}

export function CardsView({ sid }: { sid: string }) {
  const { toast, confirm: uxConfirm } = useUX()
  const [cards, setCards] = useState<Flashcard[]>([])
  const [stats, setStats] = useState<{ total: number; due: number }>({ total: 0, due: 0 })
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState('')
  const [cur, setCur] = useState<Flashcard | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [exporting, setExporting] = useState(false)
  // 切空间竞态 + 评分防重入：旧空间的卡滞留后按评分会拿新 sid 打旧卡 id（404 静默）；
  // 快速连按 3/4 会把同一张卡交给 FSRS 两次，复习间隔被双计
  const seq = useRef(0)
  const grading = useRef(false)
  const genAbort = useRef<AbortController | null>(null)
  const sidRef = useRef(sid)
  useEffect(() => { sidRef.current = sid }, [sid])

  // 复习流只取到期卡；新卡 due_at=入库时刻，天然立即到期
  const refresh = () => {
    const id = ++seq.current
    return Promise.all([
      api.flashcards(sid, true), api.flashcards(sid),
    ]).then(([dueRes, all]) => {
      if (id !== seq.current) return
      setCards(dueRes.cards); setStats(all.stats)
      setCur(dueRes.cards[0] || null); setRevealed(false)
    }).catch(() => { if (id === seq.current) toast('error', '闪卡加载失败，请检查服务是否正常') })
      .finally(() => { if (id === seq.current) setLoaded(true) })
  }
  useEffect(() => {
    seq.current++
    genAbort.current?.abort(); genAbort.current = null
    setCards([]); setCur(null); setRevealed(false); setLoaded(false)
    refresh()
  }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  // 切页卸载时中断生成：LLM 任务不取消只是干等，切回来还在跑
  useEffect(() => () => genAbort.current?.abort(), [])

  const generate = () => {
    // SSE 流式：按钮实时显示「检索讲义/生成/入库」阶段；可中途取消
    const ctrl = new AbortController()
    genAbort.current = ctrl
    const sidAtStart = sid
    setBusy(true)
    setPhase('准备中…')
    runSkillStream(sid, 'flashcard.generate', { topic, count: 10 }, {
      onPhase: setPhase,
      onDone: (made: any) => {
        if (sidRef.current !== sidAtStart) return  // 生成期间切了空间，回调不写入新视图
        const n = Array.isArray(made) ? made.length : (made?.count ?? made?.cards?.length ?? 0)
        const inst = Array.isArray(made) ? 0 : (made?.instruction_cards || 0)
        toast('success', `已生成 ${n} 张闪卡${inst ? `（含 ${inst} 张追问指令卡）` : ''}`)
        setBusy(false); setPhase('')
        refresh()
      },
      onError: (m) => {
        if (sidRef.current !== sidAtStart) return
        setBusy(false); setPhase(''); toast('error', m)
      },
      onAbort: () => { if (sidRef.current === sidAtStart) { setBusy(false); setPhase('') } },
    }, ctrl.signal)
  }

  const clearAll = async () => {
    if (!stats.total) return
    if (!(await uxConfirm({ title: '清空闪卡', message: `清空全部 ${stats.total} 张闪卡？此操作不可恢复。`, confirmText: '清空', danger: true }))) return
    try {
      await api.clearFlashcards(sid)
      await refresh()
    } catch (e: any) { toast('error', '清空失败：' + (e.message || '未知错误')) }
  }

  const importAnki = async (file: File) => {
    setBusy(true)
    try {
      const r = await api.ankiImport(sid, file)
      toast('success', `Anki 导入完成：新增 ${r.imported} 张${r.skipped ? `，跳过 ${r.skipped} 张` : ''}`)
      await refresh()
    } catch (e: any) { toast('error', '导入失败：' + (e.message || '未知错误')) }
    setBusy(false)
  }

  // 裸 <a download> 对 4xx/5xx 无感知：后端报错时浏览器会把错误页存成 .apkg
  const exportAnki = async () => {
    setExporting(true)
    try {
      const r = await fetch(api.ankiExportUrl(sid))
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `studypilot_${sid}.apkg`
      a.click()
      // 等浏览器开始下载再回收 URL，避免大文件场景下载被中断
      setTimeout(() => URL.revokeObjectURL(url), 3000)
      toast('success', '已导出 .apkg，可导入 Anki 复习')
    } catch (e: any) {
      toast('error', '导出失败：' + (e.message || '未知错误'))
    }
    setExporting(false)
  }

  const grade = async (rating: number) => {
    if (!cur || grading.current) return  // 防重入：连按会把同一张卡交给 FSRS 两次
    grading.current = true
    try {
      await api.gradeFlashcard(sid, cur.id, rating)
      // 旧卡要等 refresh 返回后才被替换：防重入标志必须等刷新完成再解除，
      // 否则窗口期内再按 1-4 仍会把同一张卡交给 FSRS
      await refresh()
    } catch (e: any) {
      toast('error', '评分失败：' + (e.message || '未知错误'))
    } finally {
      grading.current = false
    }
  }

  // 键盘刷卡流（Anki 习惯）：空格/回车翻面，翻面后 1-4 评分；焦点在输入框或按钮上时不劫持按键
  // （焦点在 BUTTON 时按 Enter/Space 应激活该按钮而不是翻卡）；确认弹窗打开时也不抢按键
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(el.tagName) || el.isContentEditable)) return
      if (document.querySelector('[role="dialog"]')) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (!cur) return
      if (!revealed) {
        if (e.code === 'Space' || e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setRevealed(true) }
        return
      }
      if (['1', '2', '3', '4'].includes(e.key)) { e.preventDefault(); grade(Number(e.key)) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cur, revealed, sid]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>闪卡 · 间隔记忆</h3>
        <p className="sub">
          从讲义生成问答卡，按 FSRS 记忆算法调度间隔（目标记住率 90%，随你的评分历史自适应）：
          新卡先经分钟级学习步进，答对毕业进入天级间隔，答错很快重现。
          不填主题时自动优先覆盖薄弱知识点。支持导入 Anki 牌组（.apkg），也可导出带去 Anki 复习。
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <input type="text" placeholder="主题（留空=优先薄弱知识点）" value={topic} onChange={(e) => setTopic(e.target.value)} />
          <button className="btn" disabled={busy} onClick={generate} style={{ flex: 'none' }}>
            {busy ? <><span className="spin" /> {phase || '生成中…'}</> : <><Icon name="cards" size={14} /> 生成 10 张闪卡</>}
          </button>
          {busy && (
            <button className="btn ghost" onClick={() => { genAbort.current?.abort(); genAbort.current = null }} style={{ flex: 'none' }}>
              停止
            </button>
          )}
          <span className="badge">共 {stats.total} 张</span>
          <span className={`badge ${stats.due > 0 ? 'expert' : ''}`}>待复习 {stats.due}</span>
          <div style={{ flex: 1 }} />
          <label className="btn ghost small" style={{ cursor: 'pointer', flex: 'none' }}>
            <Icon name="download" size={12} /> 导入 Anki
            <input type="file" accept=".apkg" style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) importAnki(f); e.target.value = '' }} disabled={busy} />
          </label>
          <button className="btn ghost small" style={{ flex: 'none' }} disabled={exporting} onClick={exportAnki}>
            {exporting ? <span className="spin" /> : <Icon name="upload" size={12} />} 导出 .apkg
          </button>
          {stats.total > 0 && (
            <button className="btn danger small" onClick={clearAll} style={{ flex: 'none' }}>
              <Icon name="trash" size={12} /> 清空闪卡
            </button>
          )}
        </div>
      </div>

      {cur ? (
        <div className="card" style={{ textAlign: 'center', padding: '36px 24px' }}>
          <span className="badge">{cur.point || '知识点'}</span>
          <div style={{ fontSize: 19, margin: '22px 0', minHeight: 60, display: 'grid', alignItems: 'center' }}>
            <b>{cur.front}</b>
          </div>
          {revealed ? (
            <>
              <div className="md" style={{ fontSize: 15, margin: '0 auto 22px', maxWidth: 560, color: 'var(--green)' }}><Md>{cur.back}</Md></div>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button className="btn danger small" onClick={() => grade(1)} title="快捷键 1">😰 忘了 · {fmtInterval(cur.preview?.['1'])}</button>
                <button className="btn ghost small" onClick={() => grade(2)} title="快捷键 2">😖 困难 · {fmtInterval(cur.preview?.['2'])}</button>
                <button className="btn small" onClick={() => grade(3)} title="快捷键 3">🙂 良好 · {fmtInterval(cur.preview?.['3'])}</button>
                <button className="btn small" onClick={() => grade(4)} title="快捷键 4">😎 轻松 · {fmtInterval(cur.preview?.['4'])}</button>
              </div>
            </>
          ) : (
            <button className="btn" onClick={() => setRevealed(true)} title="快捷键 空格">
              <Icon name="spark" size={14} /> 显示答案
            </button>
          )}
          <p className="sub" style={{ marginTop: 18 }}>本批还剩 {cards.length - 1} 张 · 快捷键：空格翻面，评分按 1-4</p>
        </div>
      ) : loaded && (
        <div className="empty" style={{ padding: 30 }}>
          {stats.total ? '当前没有到期待复习的卡片 ✓' : '还没有闪卡——用上方按钮从讲义生成，或导入 Anki 牌组'}
        </div>
      )}
    </div>
  )
}
