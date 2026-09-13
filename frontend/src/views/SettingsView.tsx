// 模型设置：本地/云端双通道路由 + MCP 连接器 + LLM 用量仪表盘 + 专家团/技能/课程图谱 + 推送提醒
import { useEffect, useState } from 'react'
import { api, CurriculumMeta, LlmStatus, NotifyStatus, UsageDashboard } from '../api'
import { Icon } from '../ui'
import { useUX } from '../ux'

export function SettingsView() {
  const { toast, confirm: uxConfirm } = useUX()
  const [status, setStatus] = useState<LlmStatus | null>(null)
  const [routing, setRouting] = useState('local')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [localBaseUrl, setLocalBaseUrl] = useState('')
  const [localModel, setLocalModel] = useState('')
  const [localApiKey, setLocalApiKey] = useState('')
  const [busy, setBusy] = useState('')
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; latency_ms?: number; error?: string }> | null>(null)
  const [mcps, setMcps] = useState<{ name: string; command: string[] }[]>([])
  const [mcpName, setMcpName] = useState('')
  const [mcpCmd, setMcpCmd] = useState('')
  const [experts, setExperts] = useState<{ id: string; name: string; description: string }[]>([])
  const [skills, setSkills] = useState<{ id: string; name: string }[]>([])
  const [curricula, setCurricula] = useState<CurriculumMeta[]>([])
  const [usage, setUsage] = useState<UsageDashboard | null>(null)
  const [cfgLoaded, setCfgLoaded] = useState(false)  // 配置未加载完成前禁止保存，防空值覆盖云端配置

  const refreshMcp = () => api.connectors().then((c) => setMcps(c.mcp)).catch(() => {})
  const refreshUsage = () => api.llmUsage(30).then(setUsage).catch(() => setUsage(null))
  useEffect(() => {
    api.llmConfig().then((s) => {
      setStatus(s); setRouting(s.routing); setBaseUrl(s.cloud.base_url); setModel(s.cloud.model)
      setLocalBaseUrl(s.local.base_url); setLocalModel(s.local.model)
      setCfgLoaded(true)
    }).catch(() => setCfgLoaded(true))  // 失败也放行保存，但 baseUrl/model 保持原样不动
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
    if (!(await uxConfirm({ title: '移除 MCP server', message: `确定移除「${name}」？注册将在重启后不再恢复。`, danger: true }))) return
    try {
      await api.removeMcp(name); refreshMcp()
    } catch (e: any) { toast('error', '删除失败：' + (e.message || '未知错误')) }
  }

  const save = async () => {
    if (!cfgLoaded) {
      // 配置读取完成前，baseUrl/model 还是空字符串：无条件提交会把已配置的
      // 云端端点/模型名清空（apiKey 已有条件展开保护，这两项此前没有）
      toast('warn', '配置尚未加载完成，请稍后再保存')
      return
    }
    setBusy('save')
    try {
      const s = await api.updateLlmConfig({
        routing,
        cloud_base_url: baseUrl,
        cloud_model: model,
        ...(apiKey ? { cloud_api_key: apiKey } : {}),
        // 本地端点：与默认值一致时不提交，避免把 .env 配置固化进运行时配置
        ...(localBaseUrl !== (status?.local.base_url || '') ? { local_base_url: localBaseUrl } : {}),
        ...(localModel !== (status?.local.model || '') ? { local_model: localModel } : {}),
        ...(localApiKey ? { local_api_key: localApiKey } : {}),
      })
      setStatus(s); setApiKey(''); setLocalApiKey('')
      toast('success', '模型配置已保存')
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  const test = async () => {
    setBusy('test')
    try {
      // 携带表单当前值测试：此前只测已保存配置，新填端点直接点测试会误报「不通」
      setTestResult(await api.testLlm({
        local_base_url: localBaseUrl, local_model: localModel,
        ...(localApiKey ? { local_api_key: localApiKey } : {}),
        cloud_base_url: baseUrl, cloud_model: model,
        ...(apiKey ? { cloud_api_key: apiKey } : {}),
      }))
    } catch (e: any) { toast('error', e.message) }
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
          本地通道连接本机或局域网的 OpenAI 兼容服务（llama-server / Ollama / LM Studio），
          端口或模型名不同就在下方改成对应值；配置云端 API 后，可按任务把重推理交给云端。
          密钥仅保存在本机 data 目录。模型没连上时，先在下方「测试连通」定位问题。
        </p>
        <div style={{ display: 'grid', gap: 10, margin: '16px 0', maxWidth: 640 }}>
          {ROUTES.map(([v, t, d]) => (
            <label key={v} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: cfgLoaded ? 'pointer' : 'wait' }}>
              <input type="radio" name="routing" checked={routing === v} onChange={() => setRouting(v)} style={{ marginTop: 3 }} disabled={!cfgLoaded} />
              <span><b>{t}</b><span style={{ color: 'var(--muted)' }}>　{d}</span></span>
            </label>
          ))}
        </div>
        <b style={{ fontSize: 13 }}>本地通道</b>
        <div style={{ display: 'grid', gap: 10, maxWidth: 640, margin: '8px 0 16px' }}>
          <input type="text" placeholder="本地服务地址（如 http://127.0.0.1:8080/v1 或 http://127.0.0.1:11434/v1）"
            value={localBaseUrl} onChange={(e) => setLocalBaseUrl(e.target.value)} />
          <input type="text" placeholder="本地模型名（如 qwen2.5:7b，Ollama 用 ollama list 查看）"
            value={localModel} onChange={(e) => setLocalModel(e.target.value)} />
          <input type="password" placeholder={status?.local.api_key_masked || '本地 API Key（通常留空即可）'}
            value={localApiKey} onChange={(e) => setLocalApiKey(e.target.value)} />
        </div>
        <b style={{ fontSize: 13 }}>云端通道（可选）</b>
        <div style={{ display: 'grid', gap: 10, maxWidth: 640, margin: '8px 0' }}>
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
                  <td><button className="btn danger small" onClick={() => delMcp(m.name)} aria-label={`移除 MCP server ${m.name}`}><Icon name="trash" size={12} /></button></td>
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

      <NotifyCard />
    </div>
  )
}

// ---------- 外部推送提醒（Server酱 / 企业微信群机器人） ----------

function NotifyCard() {
  const { toast } = useUX()
  const [st, setSt] = useState<NotifyStatus | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [channel, setChannel] = useState('serverchan')
  const [sendkey, setSendkey] = useState('')
  const [webhook, setWebhook] = useState('')
  const [pushHour, setPushHour] = useState(8)
  const [busy, setBusy] = useState('')
  const loaded = !!st

  const refresh = () => api.notifyStatus().then((s) => {
    setSt(s)
    setEnabled(s.config.enabled)
    setChannel(s.config.channel)
    setSendkey(s.config.serverchan_sendkey)   // 掩码值：原样回填，保存时服务端会忽略
    setWebhook(s.config.wecom_webhook)
    setPushHour(s.config.push_hour)
  }).catch(() => {})
  useEffect(() => { refresh() }, [])

  const save = async () => {
    setBusy('save')
    try {
      await api.saveNotify({ enabled, channel, serverchan_sendkey: sendkey,
        wecom_webhook: webhook, push_hour: pushHour })
      toast('success', '推送配置已保存')
      refresh()
    } catch (e: any) { toast('error', '保存失败：' + (e.message || '未知错误')) }
    setBusy('')
  }
  const test = async () => {
    setBusy('test')
    try {
      const r = await api.testNotify()
      if (r.ok) toast('success', '测试消息已发送，去微信看看')
      else toast('error', '测试失败：' + (r.error || '未知错误'))
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }
  const pushNow = async () => {
    setBusy('push')
    try {
      const r = await api.pushNotify()
      toast(r.pushed ? 'success' : 'info',
        r.pushed ? '今日摘要已推送' : `未推送（${r.reason}）`)
    } catch (e: any) { toast('error', e.message) }
    setBusy('')
  }

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>推送提醒 · 人不在电脑前也不漏复习</h3>
        {st?.last_push_date && <span className="badge">上次推送 {st.last_push_date}</span>}
      </div>
      <p className="sub" style={{ marginTop: 6 }}>
        每天最多推 1 次：首次发现「有到期知识点 / 闪卡 / 逾期任务」时，把跨空间摘要推到微信。
        Server酱（sctapi.ftqq.com 免费申请 SendKey，推到微信服务号）或企业微信群机器人 webhook 二选一。
      </p>
      <div style={{ display: 'grid', gap: 10, maxWidth: 640, margin: '14px 0' }}>
        <label style={{ display: 'flex', gap: 10, alignItems: 'center', cursor: 'pointer' }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <b>启用每日推送</b>
        </label>
        <div style={{ display: 'flex', gap: 12 }}>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
            <input type="radio" name="notify-ch" checked={channel === 'serverchan'} onChange={() => setChannel('serverchan')} />
            <span>Server酱（微信）</span>
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
            <input type="radio" name="notify-ch" checked={channel === 'wecom_webhook'} onChange={() => setChannel('wecom_webhook')} />
            <span>企业微信群机器人</span>
          </label>
        </div>
        {channel === 'serverchan' ? (
          <input type="password" placeholder={st?.config.serverchan_sendkey || 'Server酱 SendKey（SCT 开头）'}
            value={sendkey} onChange={(e) => setSendkey(e.target.value)} />
        ) : (
          <input type="text" placeholder={st?.config.wecom_webhook || '企业微信群机器人 webhook 地址（qyapi.weixin.qq.com/…）'}
            value={webhook} onChange={(e) => setWebhook(e.target.value)} />
        )}
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
          不早于
          <input type="number" min={0} max={23} value={pushHour} style={{ width: 70 }}
            onChange={(e) => setPushHour(Number(e.target.value))} /> 点推送
        </label>
      </div>
      {st?.last_error && (
        <p style={{ color: 'var(--red)', fontSize: 12, margin: '0 0 10px' }}>上次错误：{st.last_error}</p>
      )}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <button className="btn" disabled={!loaded || !!busy} onClick={save}>
          {busy === 'save' ? <><span className="spin" /> 保存中</> : '保存配置'}
        </button>
        <button className="btn ghost" disabled={!!busy} onClick={test}>
          {busy === 'test' ? <><span className="spin" /> 发送中</> : '测试推送'}
        </button>
        <button className="btn ghost" disabled={!!busy} onClick={pushNow}>
          {busy === 'push' ? <><span className="spin" /> 推送中</> : '立即推送今日摘要'}
        </button>
      </div>
    </div>
  )
}
