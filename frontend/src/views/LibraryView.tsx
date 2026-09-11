// 资料中心：合并原「知识库」与「教材书库」两页——
// 上半是当前空间的讲义（RAG 检索源），下半是全局教材库（可挂载到多个空间），消除两处重复的上传体验
import { useEffect, useState } from 'react'
import { api, Book, Doc, Space } from '../api'
import { EmptyState, Icon } from '../ui'
import { useUX } from '../ux'

const ACCEPT = '.pdf,.pptx,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp,.zip'

export function LibraryView({ spaces, currentSid }: { spaces: Space[]; currentSid: string }) {
  return (
    <div className="content">
      {currentSid ? (
        <SpaceDocsCard key={currentSid} sid={currentSid} spaceName={spaces.find((s) => s.id === currentSid)?.name || ''} />
      ) : (
        <div className="card" style={{ marginBottom: 18 }}>
          <EmptyState icon="upload" title="还没有选择课程空间"
            desc="在左侧选择或新建一个课程空间，即可在这里上传讲义构建该课的私有知识库（答疑/出题自动引用）。下方教材书库不依赖空间，随时可用。" />
        </div>
      )}
      <BookLibraryCard spaces={spaces} currentSid={currentSid} />
    </div>
  )
}

// ---------- 上：本空间讲义（RAG） ----------

function SpaceDocsCard({ sid, spaceName }: { sid: string; spaceName: string }) {
  const { toast, confirm: uxConfirm } = useUX()
  const [docs, setDocs] = useState<Doc[]>([])
  const [busy, setBusy] = useState(false)
  const refresh = () => api.listDocs(sid).then(setDocs).catch(() => setDocs([]))
  useEffect(() => { refresh() }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    const errors: string[] = []
    let ok = 0
    for (const f of Array.from(files)) {
      try {
        const r: any = await api.uploadDoc(sid, f)
        if (r.batch) {
          const bad = r.batch.filter((b: any) => b.status === 'error')
          ok += r.batch.length - bad.length
          bad.forEach((b: any) => errors.push(`${b.filename}: ${b.error}`))
        } else ok++
      } catch (e: any) { errors.push(`${f.name}: ${e.message}`) }
    }
    await refresh(); setBusy(false)
    if (errors.length) toast('warn', `导入完成：成功 ${ok} 个\n失败：\n${errors.join('\n')}`)
  }

  const removeDoc = async (d: Doc) => {
    if (!(await uxConfirm({ title: '删除讲义', message: `删除《${d.filename}》？向量与上传文件会一并清理。`, confirmText: '删除', danger: true }))) return
    try {
      await api.deleteDoc(sid, d.id)
      refresh()
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>本空间讲义{spaceName && ` · ${spaceName}`}</h3>
        <span className="badge">RAG 检索源</span>
        <div style={{ flex: 1 }} />
        <label className="btn" style={{ cursor: 'pointer' }}>
          <Icon name="plus" size={14} /> 上传讲义
          <input type="file" multiple accept={ACCEPT} style={{ display: 'none' }}
            onChange={(e) => upload(e.target.files)} disabled={busy} />
        </label>
      </div>
      <p className="sub" style={{ marginTop: 6 }}>
        解析 → 语义分块 → BGE 向量化 → 答疑/出题时检索引用并标注来源。支持 PDF / PPTX 课件（含讲者备注）/
        TXT / Markdown / 图片（离线 OCR）/ zip 压缩包（自动展开导入）。
      </p>
      {busy && <p className="sub" style={{ marginTop: 8 }}><span className="spin" /> 正在解析并向量化…（首次运行会下载嵌入模型）</p>}
      {docs.length > 0 ? (
        <table className="quiz" style={{ marginTop: 12 }}>
          <thead><tr><th>文件</th><th>状态</th><th>分块</th><th>错误</th><th></th></tr></thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td>{d.status === 'ready' ? <span className="status-ok">✓ 已索引</span> : d.status === 'error' ? <span className="status-err">✗ 失败</span> : <span className="status-wait"><span className="spin" /> 处理中</span>}</td>
                <td>{d.chunks}</td>
                <td style={{ color: 'var(--red)' }}>{d.error}</td>
                <td>
                  <button className="btn danger small" onClick={() => removeDoc(d)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="sub" style={{ marginTop: 12 }}>还没有讲义——上传后答疑即可引用本课内容。</p>
      )}
    </div>
  )
}

// ---------- 下：教材书库（全局，可挂载到多个空间） ----------

function BookLibraryCard({ spaces, currentSid }: { spaces: Space[]; currentSid: string }) {
  const { toast, confirm: uxConfirm, select: uxSelect } = useUX()
  const [books, setBooks] = useState<Book[]>([])
  const [subjects, setSubjects] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [subject, setSubject] = useState('')
  const [busy, setBusy] = useState('')
  const [done, setDone] = useState(0)
  const [pageUrl, setPageUrl] = useState('')
  const [mounted, setMounted] = useState<Record<string, string[]>>({})
  const refresh = () => {
    api.library(query, subject).then(async (bs) => {
      setBooks(bs)
      // 每本书已挂载到哪些课程空间：本地书目可能有挂载，外部/仅书目必然为空
      const entries = await Promise.all(bs.map(async (b) => {
        try { return [b.id, (await api.bookSpaces(b.id)).map((s) => s.name)] as const } catch { return [b.id, []] as const }
      }))
      setMounted(Object.fromEntries(entries))
    }).catch(() => setBooks([]))
    api.librarySubjects().then(setSubjects).catch(() => {})
  }
  useEffect(() => { refresh() }, [query, subject]) // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (files: FileList | null, tag: string) => {
    if (!files?.length) return
    setBusy(tag); setDone(0)
    let ok = 0
    let skipped = 0
    for (const f of Array.from(files)) {
      const low = f.name.toLowerCase()
      if (!['.pdf', '.pptx', '.txt', '.md', '.markdown', '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.zip'].some((ext) => low.endsWith(ext))) { skipped++; continue }
      try {
        const r: any = await api.uploadBook(f)
        if (r.batch) ok += r.batch.length
        else ok++
      } catch (e: any) { toast('error', `${f.name}: ${e.message}`) }
      setDone((d) => d + 1)
    }
    setBusy(''); refresh()
    if (ok) toast('success', `已入库 ${ok} 本教材，可在「挂载到空间」后用于答疑引用`)
    else if (skipped) toast('warn', `没有可导入的文件（跳过了 ${skipped} 个不支持的文件）\n支持：PDF / PPTX / TXT / Markdown / 图片 / zip`)
  }

  const fetchPdf = async (b: Book) => {
    setBusy(b.id)
    try { await api.fetchBook(b.id); toast('success', `《${b.title}》已下载入库`) }
    catch (e: any) { toast('error', e.message) }
    setBusy(''); refresh()
  }

  const importFromUrl = async () => {
    if (!pageUrl.trim()) return
    setBusy('url')
    try {
      const r = await api.importUrl(pageUrl.trim(), '')
      toast('success', `已剪藏入库：《${r.title}》（${r.chars} 字），挂载到空间后即可参与答疑检索`)
      setPageUrl(''); refresh()
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const attach = async (b: Book) => {
    if (!spaces.length) { toast('warn', '请先在左侧新建一个课程空间'); return }
    let sid = currentSid
    if (!sid) {
      const spaceId = await uxSelect({ title: '挂载到哪个课程空间？', options: spaces.map((s) => ({ value: s.id, label: s.name })) })
      if (!spaceId) return
      sid = spaceId
    }
    if (!sid) return
    // 明确告知挂到哪个空间，避免"随手点挂载、书进了自己遗忘的旧空间"
    const target = spaces.find((s) => s.id === sid)
    if (!(await uxConfirm({ title: '挂载教材', message: `将《${b.title}》挂载到「${target?.name || '所选空间'}」？`, confirmText: '挂载' }))) return
    setBusy(b.id)
    try {
      const r = await api.attachBook(b.id, sid)
      toast('info', r.status === 'already' ? '该书已在此空间' : `已挂载并索引 ${r.chunks} 个分块`)
    } catch (e: any) { toast('error', e.message) }
    setBusy(''); refresh()
  }

  const remove = async (b: Book) => {
    if (!(await uxConfirm({ title: '移除教材', message: `从书库移除《${b.title}》？各空间的挂载索引会一并清理。`, confirmText: '移除', danger: true }))) return
    try {
      await api.deleteBook(b.id); refresh()
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  const statusBadge = (b: Book) => b.status === 'local'
    ? <span className="status-ok">✓ 已入库</span>
    : b.status === 'external'
      ? <span className="badge expert">官方免费</span>
      : <span className="badge">仅书目</span>

  return (
    <div className="card">
      <h3>教材书库</h3>
      <p className="sub">
        像词库一样管理的教材库：官方免费开放教材可一键获取；自有正版 PDF / PPTX / 图片 /
        zip 批量上传入库；挂载到课程空间后，答疑 / 出题自动引用书内内容并标注来源。
      </p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '14px 0 4px', flexWrap: 'wrap' }}>
        <input type="text" style={{ maxWidth: 260 }} placeholder="搜索书名 / 作者…"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        <label className="btn" style={{ cursor: 'pointer' }}>
          <Icon name="plus" size={14} /> 上传教材文件
          <input type="file" multiple accept={ACCEPT} style={{ display: 'none' }}
            onChange={(e) => upload(e.target.files, 'files')} disabled={!!busy} />
        </label>
        <label className="btn ghost" style={{ cursor: 'pointer' }}>
          <Icon name="layers" size={14} /> 整个文件夹批量导入
          <input type="file" multiple style={{ display: 'none' }}
            {...({ webkitdirectory: '' } as any)}
            onChange={(e) => upload(e.target.files, 'folder')} disabled={!!busy} />
        </label>
        {busy === 'files' || busy === 'folder' ? (
          <span className="sub"><span className="spin" /> 正在上传入库… 已处理 {done} 个文件</span>
        ) : busy ? (
          <span className="sub"><span className="spin" /> 处理中…</span>
        ) : null}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
        <input type="text" style={{ maxWidth: 340 }} placeholder="网页剪藏：粘贴讲义 / 博客文章链接（仅公网 http/https）"
          value={pageUrl} onChange={(e) => setPageUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') importFromUrl() }} />
        <button className="btn ghost" disabled={!!busy} onClick={importFromUrl} style={{ flex: 'none' }}>
          <Icon name="book" size={13} /> 剪藏入库
        </button>
      </div>
      <div className="mode-tabs" style={{ marginTop: 12 }}>
        <button className={`mode-tab ${subject === '' ? 'active' : ''}`} onClick={() => setSubject('')}>全部</button>
        {subjects.map((s) => (
          <button key={s} className={`mode-tab ${subject === s ? 'active' : ''}`} onClick={() => setSubject(s)}>{s}</button>
        ))}
      </div>

      {books.length > 0 ? (
        <table className="quiz" style={{ marginTop: 12 }}>
          <thead><tr><th style={{ width: '34%' }}>书名</th><th>学科</th><th>状态</th><th style={{ width: '30%' }}>说明 / 操作</th></tr></thead>
          <tbody>
            {books.map((b) => (
              <tr key={b.id}>
                <td>
                  <b>{b.title}</b>
                  <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 3 }}>
                    {b.author}{b.publisher && b.publisher !== '—' ? ` · ${b.publisher}` : ''}
                  </div>
                  {mounted[b.id]?.length ? (
                    <div className="sub" style={{ fontSize: 12, marginTop: 3, color: 'var(--green)' }}>
                      已挂载：{mounted[b.id].join('、')}
                    </div>
                  ) : null}
                </td>
                <td><span className="badge">{b.subject}</span></td>
                <td>{statusBadge(b)}{b.error && <div style={{ color: 'var(--red)', fontSize: 11 }}>{b.error}</div>}</td>
                <td>
                  <div style={{ color: 'var(--muted)', fontSize: 12 }}>{b.note}</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 7, flexWrap: 'wrap' }}>
                    {b.status === 'external' && b.pdf_url && (
                      <button className="btn small" disabled={!!busy} onClick={() => fetchPdf(b)}>
                        <Icon name="book" size={12} /> {b.pdf_url.startsWith('http://') ? '获取 PDF（约 70MB）' : '获取 PDF'}
                      </button>
                    )}
                    {b.status === 'local' && (
                      <button className="btn small" disabled={!!busy} onClick={() => attach(b)}>
                        <Icon name="layers" size={12} /> 挂载到空间
                      </button>
                    )}
                    {b.source_url && (
                      <a className="btn ghost small" href={b.source_url} target="_blank" rel="noreferrer">官网来源 ↗</a>
                    )}
                    <button className="btn danger small" disabled={!!busy} onClick={() => remove(b)}>
                      <Icon name="trash" size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="sub" style={{ marginTop: 12 }}>书库为空——点击上方按钮导入你的教材。</p>
      )}
    </div>
  )
}
