// Markdown 渲染：PDF/模型输出的 \(..\) \[..\] 定界符转成 $..$ / $$..$$，让 remark-math 识别
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

function normalizeMath(src: string): string {
  return src
    .replace(/\\\((.+?)\\\)/gs, (_, m) => `$${m}$`)
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`)
}

export function Md({ children }: { children: string }) {
  return (
    <div className="md">
      <Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizeMath(children)}
      </Markdown>
    </div>
  )
}
