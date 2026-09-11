// 模型设置：本地/云端双通道路由 + MCP 连接器 + LLM 用量仪表盘 + 专家团/技能/课程图谱
import { useEffect, useState } from 'react'
import { api, CurriculumMeta, LlmStatus, UsageDashboard } from '../api'
import { Icon } from '../ui'
import { useUX } from '../ux'

export function SettingsView() {
  const { toast, confirm: uxConfirm } = useUX()
  const [status, setStatus] = useState<LlmStatus | null>(null)
  const [routing, setRouting] = useState('local')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState('')
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; latency_ms?: number; error?: string }> | null>(null)
  const [mcps, setMcps] = useState<{ name: string; command: string[] }[]>([])
  const [mcpName, setMcpName] = useState('')
  const [mcpCmd, setMcpCmd] = useState('')
  const [experts, setExperts] = useState<{ id: string; name: string; description: string }[]>([])
  const [skills, setSkills] = useState<{ id: string; name: string }[]>([])
  const [curricula, setCurricula] = useState<CurriculumMeta[]>([])
  const [usage, setUsage] = useState<UsageDashboard | null>(null)

  const refreshMcp = () => api.connectors().then((c) => setMcps(c.mcp)).catch(() => {})
  const refreshUsage = () => api.llmUsage(30).then(setUsage).catch(() => setUsage(null))
  useEffect(() => {
    api.llmConfig().then((s) => {
      setStatus(s); setRouting(s.routing); setBaseUrl(s.cloud.base_url); setModel(s.cloud.model)
    }).catch(() => {})
    refreshMcp()
    refreshUsage()
    api.listExperts().then(setExperts).catch(() => {})
    api.listSkills().then(setSkills).catch(() => {})
    api.curriculums().then(setCurricula).catch(() => {})
  }, [])

  const addMcp = async () => {
    const cmd = mcpCmd.trim().split(/\s+/).filter(Boolean)
    if (!mcpName.trim() || !cmd.length) { toast('warn', '请填写名称与启动命令'); return }
    setBusy('mcp')
    try {
      await api.registerMcp(mcpName.trim(), cmd)
      setMcpName(''); setMcpCmd(''); refreshMcp()
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const delMcp = async (name: string) => {
    try {
      await api.removeMcp(name); refreshMcp()
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  const save = async () => {
    setBusy('save')
    try {
      const s = await api.updateLlmConfig({
        routing,
        cloud_base_url: baseUrl,
        cloud_model: model,
        ...(apiKey ? { cloud_api_key: apiKey } : {}),
      })
      setStatus(s); setApiKey(''); toast('success', '模型配置已保存')
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const test = async () => {
    setBusy('test')
    try { setTestResult(await api.testLlm()) } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const clearStats = async () => {
    if (!(await uxConfirm({ title: '清空调用统计', message: '全部 LLM 调用统计记录将被删除。', confirmText: '清空', danger: true }))) return
    try { await api.clearLlmStats(); refreshUsage(); toast('success', '统计已清空') } catch (e: any) { toast('error', e.message) }
  }

  const ROUTES: [string, string, string][] = [
    ['local', '全本地', '所有任务走本机模型，完全离线'],
    ['auto', '自动路由', '出题 / 判卷 / 分析 / 规划走云端，日常问答走本地'],
    ['cloud', '全云端', '全部走云端 API，云端失败自动回退本地'],
  ]
  const fmtTokens = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n)

  return (
    <div className="content">
      <div className="card" style={{ marginBottom: 18 }}>
        <h3>模型设置 · 本地 / 云端双通道</h3>
        <p className="sub">
          本地通道始终可用（{status?.local.model || '…'}）；配置云端 OpenAI 兼容 API 后，
          可按任务把重推理交给云端，日常答疑保持本地低延迟。云端密钥仅保存在本机 data 目录。
        </p>
        <div style={{ display: 'grid', gap: 10, margin: '16px 0', maxWidth: 640 }}>
          {ROUTES.map(([v, t, d]) => (
            <label key={v} className="route-opt" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
              <input type="radio" name="routing" checked={routing === v} onChange={() => setRouting(v)} style={{ marginTop: 3 }} />
              <span><b>{t}</b><span style={{ color: 'var(--muted)' }}>　{d}</span></span>
            </label>
          ))}
        </div>
        <div style={{ display: 'grid', gap: 10, maxWidth: 640 }}>
          <input type="text" placeholder="云端 API 地址（如 https://api.openai.com/v1 或国内兼容端点）"
            value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          <input type="text" placeholder="云端模型名（如 gpt-4o-mini / deepseek-chat）"
            value={model} onChange={(e) => setModel(e.target.value)} />
          <input type="password" placeholder={status?.cloud.api_key_masked || '云端 API Key（留空则不修改）'}
            value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 16, alignItems: 'center' }}>
          <button className="btn" disabled={!!busy} onClick={save}>
            {busy === 'save' ? <><span className="spin" /> 保存中</> : '保存配置'}
          </button>
          <button className="btn ghost" disabled={!!busy} onClick={test}>
            {busy === 'test' ? <><span className="spin" /> 测试中</> : '测试连通'}
          </button>
        </div>
        {testResult && (
          <table className="quiz" style={{ marginTop: 16, maxWidth: 640 }}>
            <thead><tr><th>通道</th><th>状态</th><th>延迟</th><th>错误</th></tr></thead>
            <tbody>
              {(['local', 'cloud'] as const).map((p) => (
                <tr key={p}>
                  <td>{p === 'local' ? '本地模型' : '云端 API'}</td>
                  <td>{testResult[p]?.ok ? <span className="status-ok">✓ 连通</span> : <span className="status-err">✗ 不通</span>}</td>
                  <td>{testResult[p]?.latency_ms ? `${testResult[p].latency_ms} ms` : '—'}</td>
                  <td style={{ color: 'var(--red)', fontSize: 12 }}>{testResult[p]?.error || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>LLM 用量仪表盘</h3>
          <span className="sub">最近 30 天 · 本机记录，用于观察双通道分工与开销</span>
          <div style={{ flex: 1 }} />
          {usage && usage.totals.calls > 0 && (
            <button className="btn danger ghost small" onClick={clearStats}><Icon name="trash" size={12} /> 清空统计</button>
          )}
        </div>
        {!usage || usage.totals.calls === 0 ? (
          <p className="sub" style={{ marginTop: 10 }}>还没有调用记录——开始对话/出题后这里会出现调用量、Token 与延迟分布。</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '12px 0' }}>
              <span className="badge">调用 <b>{usage.totals.calls}</b> 次</span>
              <span className="badge">成功率 <b>{Math.round(usage.totals.success_rate * 100)}%</b></span>
              <span className="badge">输入 <b>{fmtTokens(usage.totals.tokens_in)}</b> tok</span>
              <span className="badge">输出 <b>{fmtTokens(usage.totals.tokens_out)}</b> tok</span>
            </div>
            <table className="quiz" style={{ maxWidth: 760 }}>
              <thead>
                <tr><th>通道 / 任务</th><th>调用</th><th>成功率</th><th>平均延迟</th><th>P50</th><th>Token</th></tr>
              </thead>
              <tbody>
                {Object.entries(usage.by_channel).map(([ch, v]) => (
                  <tr key={ch}>
                    <td><b>通道：{ch === 'local' ? '本地' : '云端'}</b></td>
                    <td>{v.calls}</td>
                    <td>{Math.round(v.success_rate * 100)}%</td>
                    <td>{v.avg_latency_ms ? `${(v.avg_latency_ms / 1000).toFixed(1)}s` : '—'}</td>
                    <td>{v.p50_latency_ms ? `${(v.p50_latency_ms / 1000).toFixed(1)}s` : '—'}</td>
                    <td>{fmtTokens(v.tokens_total)}</td>
                  </tr>
                ))}
                {Object.entries(usage.by_task)
                  .sort((a, b) => b[1].calls - a[1].calls).slice(0, 8)
                  .map(([task, v]) => (
                    <tr key={task}>
                      <td>任务：{task}</td>
                      <td>{v.calls}</td>
                      <td>{Math.round(v.success_rate * 100)}%</td>
                      <td>—</td>
                      <td>—</td>
                      <td>{fmtTokens(v.tokens_total)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <h3>MCP 连接器</h3>
        <p className="sub">
          注册本机 MCP server（stdio 命令），答疑专家在需要时会自动调用其工具（如读本地文件）。
          注册持久化保存，重启后自动恢复。命令以空格分隔，如：
          <code> npx -y @modelcontextprotocol/server-filesystem C:/path</code>
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <input type="text" style={{ maxWidth: 160 }} placeholder="名称（如 fs）"
            value={mcpName} onChange={(e) => setMcpName(e.target.value)} />
          <input type="text" style={{ flex: 1, minWidth: 280 }} placeholder="启动命令（空格分隔）"
            value={mcpCmd} onChange={(e) => setMcpCmd(e.target.value)} />
          <button className="btn" disabled={!!busy} onClick={addMcp} style={{ flex: 'none' }}>
            {busy === 'mcp' ? <><span className="spin" /> 注册中</> : '注册'}
          </button>
        </div>
        {mcps.length > 0 && (
          <table className="quiz" style={{ marginTop: 14, maxWidth: 720 }}>
            <thead><tr><th>名称</th><th>命令</th><th style={{ width: 60 }}></th></tr></thead>
            <tbody>
              {mcps.map((m) => (
                <tr key={m.name}>
                  <td><b>{m.name}</b></td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{m.command.join(' ')}</td>
                  <td><button className="btn danger small" onClick={() => delMcp(m.name)}><Icon name="trash" size={12} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>专家团 · 技能 · 内置课程图谱</h3>
        <p className="sub">
          答疑按问题内容自动路由到对应专家；技能由各功能页的按钮触发（出题、判卷、闪卡、讲义总结…）；
          构建知识图谱时，讲义抽取的前置关系会与内置课程图谱合并。
        </p>
        <b style={{ fontSize: 13 }}>专家团（{experts.length} 位）</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 14px' }}>
          {experts.map((e) => (
            <span key={e.id} className="badge" title={e.description}>{e.name}</span>
          ))}
        </div>
        <b style={{ fontSize: 13 }}>技能（{skills.length} 项）</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 14px' }}>
          {skills.map((s) => (
            <span key={s.id} className="badge" title={s.id}>{s.name}</span>
          ))}
        </div>
        <b style={{ fontSize: 13 }}>内置课程图谱（{curricula.length} 门）</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0 0' }}>
          {curricula.map((c) => (
            <span key={c.file} className="badge">{c.course} · {c.concepts} 个知识点</span>
          ))}
          {!curricula.length && <span className="sub">暂无内置课程图谱数据</span>}
        </div>
      </div>
    </div>
  )
}
