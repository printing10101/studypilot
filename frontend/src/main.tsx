import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { ToastProvider } from './ui'
import { UXProvider } from './ux'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>
      <UXProvider>
        <App />
      </UXProvider>
    </ToastProvider>
  </React.StrictMode>,
)
