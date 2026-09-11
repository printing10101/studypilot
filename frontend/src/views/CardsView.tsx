// 闪卡：FSRS 间隔复习刷卡流 + Anki 牌组导入导出
import { useEffect, useState } from 'react'
import { api, Flashcard } from '../api'
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
  const [cur, setCur] = useState<Flashcard | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // 复习流只取到期卡；新卡 due_at=入库时刻，天然立即到期
  const refresh = () => Promise.all([
    api.flashcards(sid, true), api.flashcards(sid),
  ]).then(([dueRes, all]) => {
    setCards(dueRes.cards); setStats(all.stats)
    setCur(dueRes.cards[0] || null); setRevealed(false)
  }).catch(() => toast('error', '闪卡加载失败，请检查服务是否正常'))
    .finally(() => setLoaded(true))
  useEffect(() => { refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async () => {
    setBusy(true)
    try {
      const made = await api.runSkill(sid, 'flashcard.generate', { topic, count: 10 })
      const n = Array.isArray(made) ? made.length : (made?.count ?? made?.cards?.length ?? 0)
      const inst = Array.isArray(made) ? 0 : (made?.instruction_cards || 0)
      toast('success', `已生成 ${n} 张闪卡${inst ? `（含 ${inst} 张追问指令卡）` : ''}`)
      await refresh()
    } catch (e: any) { toast('error', e.message) }
    setBusy(false)
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

  const grade = async (rating: number) => {
    if (!cur) return
    try { await api.gradeFlashcard(sid, cur.id, rating) } catch { /* 单卡评分失败不阻塞 */ }
    refresh()
  }

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
            {busy ? <><span className="spin" /> 生成中</> : <><Icon name="cards" size={14} /> 生成 10 张闪卡</>}
          </button>
          <span className="badge">共 {stats.total} 张</span>
          <span className={`badge ${stats.due > 0 ? 'expert' : ''}`}>待复习 {stats.due}</span>
          <div style={{ flex: 1 }} />
          <label className="btn ghost small" style={{ cursor: 'pointer', flex: 'none' }}>
            <Icon name="download" size={12} /> 导入 Anki
            <input type="file" accept=".apkg" style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) importAnki(f); e.target.value = '' }} disabled={busy} />
          </label>
          <a className="btn ghost small" style={{ flex: 'none' }} href={api.ankiExportUrl(sid)} download>
            <Icon name="upload" size={12} /> 导出 .apkg
          </a>
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
                <button className="btn danger small" onClick={() => grade(1)}>😰 忘了 · {fmtInterval(cur.preview?.['1'])}</button>
                <button className="btn ghost small" onClick={() => grade(2)}>😖 困难 · {fmtInterval(cur.preview?.['2'])}</button>
                <button className="btn small" onClick={() => grade(3)}>🙂 良好 · {fmtInterval(cur.preview?.['3'])}</button>
                <button className="btn small" onClick={() => grade(4)}>😎 轻松 · {fmtInterval(cur.preview?.['4'])}</button>
              </div>
            </>
          ) : (
            <button className="btn" onClick={() => setRevealed(true)}>
              <Icon name="spark" size={14} /> 显示答案
            </button>
          )}
          <p className="sub" style={{ marginTop: 18 }}>本批还剩 {cards.length - 1} 张</p>
        </div>
      ) : loaded && (
        <div className="empty" style={{ padding: 30 }}>
          {stats.total ? '当前没有到期待复习的卡片 ✓' : '还没有闪卡——用上方按钮从讲义生成，或导入 Anki 牌组'}
        </div>
      )}
    </div>
  )
}
