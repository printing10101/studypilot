// 全局 UX 交互 Hook：toast / confirm / prompt / select
// 替代浏览器原生 alert() / confirm() / prompt()
import { createContext, useCallback, useContext, useState } from 'react'
import { ConfirmDialog, PromptDialog, SelectDialog, useToast } from './ui'

interface ConfirmOpts { title: string; message: string; confirmText?: string; danger?: boolean }
interface PromptOpts { title: string; label?: string; placeholder?: string; defaultValue?: string; multiline?: boolean }
interface SelectOpts { title: string; message?: string; options: { value: string; label: string; sub?: string }[] }

interface UXCtx {
  toast: (type: 'success' | 'error' | 'info' | 'warn', text: string) => void
  confirm: (opts: ConfirmOpts) => Promise<boolean>
  prompt: (opts: PromptOpts) => Promise<string | null>
  select: (opts: SelectOpts) => Promise<string | null>
}

const Ctx = createContext<UXCtx | null>(null)

export function useUX(): UXCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useUX must be used inside UXProvider')
  return c
}

export function UXProvider({ children }: { children: React.ReactNode }) {
  const toast = useToast()
  const [confirmState, setConfirmState] = useState<(ConfirmOpts & { resolve: (v: boolean) => void }) | null>(null)
  const [promptState, setPromptState] = useState<(PromptOpts & { resolve: (v: string | null) => void }) | null>(null)
  const [selectState, setSelectState] = useState<(SelectOpts & { resolve: (v: string | null) => void }) | null>(null)

  const confirm = useCallback((opts: ConfirmOpts) =>
    new Promise<boolean>((resolve) => setConfirmState({ ...opts, resolve })), [])

  const prompt = useCallback((opts: PromptOpts) =>
    new Promise<string | null>((resolve) => setPromptState({ ...opts, resolve })), [])

  const select = useCallback((opts: SelectOpts) =>
    new Promise<string | null>((resolve) => setSelectState({ ...opts, resolve })), [])

  return (
    <Ctx.Provider value={{ toast, confirm, prompt, select }}>
      {children}
      {confirmState && (
        <ConfirmDialog open title={confirmState.title} message={confirmState.message}
          confirmText={confirmState.confirmText} danger={confirmState.danger}
          onConfirm={() => { confirmState.resolve(true); setConfirmState(null) }}
          onCancel={() => { confirmState.resolve(false); setConfirmState(null) }} />
      )}
      {promptState && (
        <PromptDialog open title={promptState.title} label={promptState.label}
          placeholder={promptState.placeholder} defaultValue={promptState.defaultValue}
          multiline={promptState.multiline}
          onConfirm={(v) => { promptState.resolve(v); setPromptState(null) }}
          onCancel={() => { promptState.resolve(null); setPromptState(null) }} />
      )}
      {selectState && (
        <SelectDialog open title={selectState.title} message={selectState.message}
          options={selectState.options}
          onConfirm={(v) => { selectState.resolve(v); setSelectState(null) }}
          onCancel={() => { selectState.resolve(null); setSelectState(null) }} />
      )}
    </Ctx.Provider>
  )
}
