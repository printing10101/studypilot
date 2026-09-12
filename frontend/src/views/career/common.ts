// 学涯中心各子页签共享的常量与工具函数。
export const DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
export const GOALS = ['保研', '考研', '就业', '竞赛', '出国', '期末', '毕业']

// 个人档案页的目标词表（"推免/保研"等）映射到规划页词表，避免同一档案在两页显示不一致
export const goalAlias = (g: string) => {
  if (GOALS.includes(g)) return g
  if (/推免|保研/.test(g)) return '保研'
  return '考研'
}

export const HORIZONS = ['本学期', '本学年', '至毕业']
export const PERIOD_ORDER = ['1-2', '3-4', '5-6', '7-8', '9-10', '11-12']

export function periodKey(p: string): number {
  const n = parseInt((p || '').split('-')[0])
  return isNaN(n) ? 99 : n
}

export function periodLabel(p: string): string {
  return p ? `第${p}节` : '未排时段'
}
