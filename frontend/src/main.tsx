import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ToastProvider } from './ui'
import { UXProvider } from './ux'
import './styles.css'

// 顶层兜底：任何未捕获的渲染错误显示可恢复的错误页，而不是整树卸载白屏
// （此前 localStorage 配额满/组件异常都会让窗口全白且无提示）
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, maxWidth: 640, margin: '10vh auto', fontFamily: 'inherit' }}>
          <h2 style={{ marginBottom: 12 }}>页面出错了</h2>
          <p style={{ color: '#888', marginBottom: 8 }}>
            界面遇到未处理的异常。你的数据都在本机，刷新后可继续使用。
          </p>
          <pre style={{
            background: 'rgba(128,128,128,.1)', padding: 12, borderRadius: 8,
            fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}>
            {this.state.error.message}
          </pre>
          <button
            style={{ marginTop: 16, padding: '8px 20px', cursor: 'pointer' }}
            onClick={() => { this.setState({ error: null }); location.reload() }}
          >
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ToastProvider>
        <UXProvider>
          <App />
        </UXProvider>
      </ToastProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
