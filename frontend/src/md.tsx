// Markdown 渲染：PDF/模型输出的 \(..\) \[..\] 定界符转成 $..$ / $$..$$，让 remark-math 识别
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

// 围栏代码块不参与数学定界符改写：代码里的 \(..\) 是字面量（如 LaTeX 源码示例）
function normalizeMath(src: string): string {
  const parts = src.split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
  return parts
    .map((part, i) => {
      // split 带捕获组：奇数下标是代码块/行内代码本身，原样保留
      if (i % 2 === 1) return part
      return part
        .replace(/\\\((.+?)\\\)/gs, (_, m) => `$${m}$`)
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`)
    })
    .join('')
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
