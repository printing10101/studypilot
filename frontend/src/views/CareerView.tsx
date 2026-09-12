// 学涯中心：编排层。只持有跨页签共享的状态（档案/学籍/课程表元数据/计划列表/常驻提示），
// 各子页签的实现见 ./career/：ProgramTab / ScheduleTab / AuditTab / PlanTab / HandbookTab / CompeteTab。
// 档案只在「个人中心」维护一次——这里展示只读摘要，不再重复整张表单。
import { useEffect, useState } from 'react'
import { api, CareerPlan, ScheduleData, Space, StudentProfile } from '../api'
import { SubTabs } from '../ui'
import { ProgramTab } from './career/ProgramTab'
import { ScheduleTab } from './career/ScheduleTab'
import { AuditTab } from './career/AuditTab'
import { PlanTab } from './career/PlanTab'
import { HandbookTab } from './career/HandbookTab'
import { CompeteTab } from './career/CompeteTab'

export function CareerView({ spaces, currentSid, onGoto }: {
  spaces: Space[]; currentSid: string; onGoto: (t: string) => void
}) {
  const [sub, setSub] = useState('program')

  // 学籍（个人档案只读来源 + 学籍页的查找输入）
  const [profile, setProfile] = useState<StudentProfile | null>(null)
  const [profileErr, setProfileErr] = useState('')  // 加载失败 ≠ 「正在读取」：否则成长手册/竞赛页永远转圈
  const [school, setSchool] = useState('')
  const [major, setMajor] = useState('')
  const [year, setYear] = useState('')

  // 课程表元数据（草稿/解析在 ScheduleTab 内部；学期名供学涯计划参考）
  const [schedule, setSchedule] = useState<ScheduleData | null>(null)

  // 学涯计划列表（页签徽标需要待办数，故列表由编排层持有）
  const [plans, setPlans] = useState<CareerPlan[]>([])

  // 常驻提示：解析结果的关键引导（「检查无误后点保存」）不该 2.5 秒后消失；
  // 下一次操作会覆盖，或点 ✕ 手动关闭
  const [msg, setMsg] = useState('')
  const flash = (text: string) => setMsg(text)

  const loadPlans = () =>
    api.careerPlans().then(async (metas) => {
      // allSettled：单份计划损坏/404 不应把整个计划列表静默清空
      const results = await Promise.allSettled(metas.map((m) => api.careerPlan(m.id)))
      setPlans(results.filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled').map((r) => r.value))
    }).catch(() => {})

  useEffect(() => {
    api.profile().then((p) => {
      setProfile(p)
      setSchool(p.current_school || '')
      setMajor(p.major || '')
      setYear(p.year || '')
      setProfileErr('')
    }).catch((e: any) => setProfileErr(e?.message || '网络错误'))
    // 首次加载失败也走兜底骨架：schedule 为 null 时学期名输入框永远无法输入，整个页签死锁
    api.schedule().then((s) => setSchedule(s)).catch(() => setSchedule({ term: '', terms: [], courses: [] }))
    loadPlans()
  }, [])  

  const applyProfile = (p: StudentProfile) => {
    setProfile(p)
    setSchool(p.current_school || '')
    setMajor(p.major || '')
    setYear(p.year || '')
  }

  const reloadProfile = () => {
    setProfileErr('')
    api.profile().then(applyProfile).catch((e: any) => setProfileErr(e?.message || '网络错误'))
  }

  const planTotal = plans.reduce((a, p) => a + p.tasks.filter((t) => !t.done).length, 0)

  return (
    <div className="content">
      <SubTabs value={sub} onChange={setSub} tabs={[
        ['program', '① 学籍与培养方案'], ['schedule', '② 课程表'], ['audit', '③ 成绩审核'],
        ['plan', `④ 学涯计划${planTotal ? `（${planTotal} 待办）` : ''}`], ['handbook', '⑤ 成长手册'],
        ['compete', '⑥ 竞赛规划'],
      ]} />

      {/* ① 学籍与培养方案 */}
      {sub === 'program' && (
        <ProgramTab school={school} major={major} year={year}
          onSchoolChange={setSchool} onMajorChange={setMajor} onYearChange={setYear}
          profile={profile} profileErr={profileErr}
          reloadProfile={reloadProfile} onProfileSaved={setProfile} flash={flash} />
      )}

      {/* ② 课程表 */}
      {sub === 'schedule' && (
        <ScheduleTab schedule={schedule} onScheduleChange={setSchedule}
          flash={flash} msg={msg} onDismissMsg={() => setMsg('')} />
      )}

      {/* ③ 成绩审核 */}
      {sub === 'audit' && <AuditTab school={school} major={major} />}

      {/* ④ 学涯计划 */}
      {sub === 'plan' && (
        <PlanTab plans={plans} setPlans={setPlans} loadPlans={loadPlans}
          school={school} major={major} year={year}
          scheduleTerm={schedule?.term || ''} scheduleEmpty={!!schedule && !schedule.courses.length}
          profile={profile} spaces={spaces} onGoto={onGoto} />
      )}

      {/* ⑤ 成长手册 */}
      {sub === 'handbook' && (
        <HandbookTab profile={profile} profileErr={profileErr}
          currentSid={currentSid} spaces={spaces} onGoto={onGoto} />
      )}

      {/* ⑥ 竞赛规划 */}
      {sub === 'compete' && <CompeteTab profile={profile} profileErr={profileErr} onGoto={onGoto} />}
    </div>
  )
}
