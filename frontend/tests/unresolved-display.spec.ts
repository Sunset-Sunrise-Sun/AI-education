import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PlanResultPanel from '@/components/PlanResultPanel.vue'
import PendingAdjustments from '@/components/PendingAdjustments.vue'
import MakeupTaskList from '@/components/MakeupTaskList.vue'
import { isTechnicalEvidence, studentText, toDisplayUnresolved, unresolvedTypeHint, unresolvedTypeLabel } from '@/utils/displayLanguage'
import type { MakeupTask, PlanResult } from '@/types/contracts'

const names = { FL101: '大学外语', CSE335: '数据库系统原理' }
const forbidden = /manual_confirmation|selection_required|missing_data|unresolved|sha256|case-owner-confirmed:\/\/|upload:|table:\d|provenance|后端类型|source_evidence|[a-f0-9]{32,64}/i
const task: MakeupTask = { course_id: 'FL101', course_name: '大学外语', credit: 2, status: 'manual_confirmation', reason: '请核对外语修读要求', source_evidence: 'case-owner-confirmed://private' }
function plan(items: PlanResult['unresolved'] = []): PlanResult {
  return { status: 'partially_feasible', selected_classes: [], changes: [], risks: [], unresolved: items }
}
function panel(value: PlanResult, tasks: MakeupTask[] = []) {
  return mount(PlanResultPanel, { props: { planResult: value, courseNameById: names, makeupTasks: tasks } })
}

describe('学生语言和详情', () => {
  it('已知及未知类型统一为用户语言', () => {
    expect(unresolvedTypeLabel('manual_confirmation')).toBe('需要你的确认')
    expect(unresolvedTypeLabel('selection_required')).toBe('请选择课程')
    expect(unresolvedTypeLabel('missing_data')).toBe('缺少必要信息')
    for (const value of ['new_kind', '', null, undefined]) expect(unresolvedTypeLabel(value)).toBe('需要进一步确认')
    expect(unresolvedTypeHint('manual_confirmation')).toBe('系统发现该课程可能需要补修，请确认是否纳入规划。')
    expect(unresolvedTypeHint('new_kind')).toContain('核实')
  })
  it('过滤嵌入正文的技术引用，保留可读文字', () => {
    for (const text of ['case-owner-confirmed://abc', '依据 upload:pdf:sha256:abcdef', '详情 table:2,row:3', '本地 C:\\Users\\private', '校验 abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789']) expect(studentText(text, '请查看课程说明')).toBe('请查看课程说明')
    expect(isTechnicalEvidence('课程 FL101，见 case-owner-confirmed://private')).toBe(true)
    expect(studentText('需要核对外语课程')).toBe('需要核对外语课程')
  })
  it('显示转换不改写原始响应', () => {
    const original = [{ type: 'manual_confirmation', message: '请核对课程', evidence: ['sha256:abc', '成绩单第 2 页'] }]
    const before = JSON.stringify(original)
    const display = toDisplayUnresolved(original)
    expect(display[0].label).toBe('需要你的确认')
    expect(display[0].technicalEvidence).toEqual(['sha256:abc'])
    expect(JSON.stringify(original)).toBe(before)
    expect(toDisplayUnresolved(original)).toEqual(display)
  })
  it('展开后也不泄漏类型、hash、内部路径，保留可读依据', async () => {
    const value = plan([{ type: 'manual_confirmation', message: 'FL101 请核对修读情况', evidence: ['upload:pdf:sha256:341a05306507fc49', 'table:2,row:3', '成绩单第 2 页'] } as PlanResult['unresolved'][number]])
    const wrapper = panel(value)
    expect((wrapper.get('details').element as HTMLDetailsElement).open).toBe(false)
    await wrapper.get('summary').trigger('click')
    expect(wrapper.text()).not.toMatch(forbidden)
    expect(wrapper.text()).toContain('大学外语')
    expect(wrapper.text()).toContain('课程编号：FL101')
    expect(wrapper.text()).toContain('为什么需要确认')
    expect(wrapper.text()).toContain('系统判断依据')
    expect(wrapper.text()).toContain('成绩单第 2 页')
  })
  it('相似课程号不会匹配为另一门课程', () => {
    const wrapper = panel(plan([{ type: 'manual_confirmation', message: 'FL1010 需要核对' }]))
    expect(wrapper.get('[data-testid="case-a-unresolved-name"]').text()).toBe('课程信息待核对')
  })
})

describe('实际确认交互', () => {
  it('空状态没有假操作按钮', () => {
    const wrapper = panel(plan())
    expect(wrapper.find('[data-testid="case-a-confirm-selection"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('本次没有推荐课程')
    expect(wrapper.text()).toContain('本次没有需要你确认的课程')
  })
  it('勾选与撤回更新计数；确认只改变选中项的本地状态', async () => {
    const value = plan([{ type: 'manual_confirmation', message: 'FL101 请核对' }, { type: 'missing_data', message: 'CSE335 缺少信息' }])
    const original = JSON.stringify(value)
    const wrapper = panel(value)
    const boxes = wrapper.findAll('input[type="checkbox"]')
    const button = wrapper.get('[data-testid="case-a-confirm-selection"]')
    expect(button.attributes('disabled')).toBeDefined()
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await boxes[1].setValue(false)
    expect(wrapper.get('[data-testid="case-a-confirmation-count"]').text()).toContain('已选择 1 项')
    await button.trigger('click')
    expect(wrapper.findAll('[data-testid="case-a-unresolved-status"]').map(node => node.text())).toEqual(['已确认'])
    expect(wrapper.text()).toContain('课程信息不完整，请补充后再生成方案')
    expect(boxes[0].attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="case-a-confirmation-count"]').text()).toContain('已选择 0 项 · 已确认 1 项')
    expect(wrapper.get('[data-testid="case-a-confirmation-feedback"]').text()).toContain('已确认 1 项')
    expect(wrapper.get('[data-testid="case-a-confirmation-feedback"]').text()).toContain('重新生成方案后仍会继续显示')
    expect(JSON.stringify(value)).toBe(original)
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('update:planResult')).toBeUndefined()
    expect(wrapper.emitted('update:currentSchedule')).toBeUndefined()
  })
  it('新结果返回后清空已确认和未提交的选择', async () => {
    const value = plan([{ type: 'manual_confirmation', message: 'FL101 请核对' }, { type: 'missing_data', message: '缺少学分' }])
    const wrapper = panel(value)
    await wrapper.findAll('input[type="checkbox"]')[0].setValue(true)
    await wrapper.get('[data-testid="case-a-confirm-selection"]').trigger('click')
    await wrapper.findAll('input[type="checkbox"]')[1].setValue(true)
    await wrapper.setProps({ planResult: structuredClone(value) })
    expect(wrapper.get('[data-testid="case-a-confirmation-count"]').text()).toBe('已选择 0 项 · 已确认 0 项')
    expect(wrapper.findAll('[data-testid="case-a-unresolved-status"]')).toHaveLength(0)
  })
  it('核对后仍提示缺失信息和选课的实际下一步', async () => {
    const value = plan([{ type: 'missing_data', message: '缺少学分信息' }, { type: 'selection_required', message: '请选择教学班' }])
    const before = JSON.stringify(value)
    const wrapper = panel(value)
    for (const box of wrapper.findAll('input[type="checkbox"]')) await box.setValue(true)
    await wrapper.get('[data-testid="case-a-confirm-selection"]').trigger('click')
    expect(wrapper.text()).toContain('请补充后再生成方案')
    expect(wrapper.text()).toContain('请选择对应课程或教学班后重新生成方案')
    // ⚠️ 拆分后每个子模块各自说明自己的边界
    expect(wrapper.text()).toContain('需要你确认自己的历史学习情况')
    expect(JSON.stringify(value)).toBe(before)
  })
})

describe('唯一入口与旧结果模块', () => {
  it('推荐课程与需要你确认分列两个子模块，语义不混', () => {
    const value = plan([{ type: 'manual_confirmation', message: 'FL101 请核对' }])
    value.selected_classes = [{ course_id: 'CSE335', class_id: '01' }]
    const wrapper = panel(value)

    // ⚠️ 产品语义拆分（P0）：两类课程各有自己的子模块与标题。
    const recommended = wrapper.get('[data-testid="case-a-recommended"]')
    const needConfirm = wrapper.get('[data-testid="case-a-need-confirm"]')

    expect(recommended.text()).toContain('推荐课程')
    expect(recommended.text()).toContain('数据库系统原理（CSE335）')
    expect(recommended.text()).toContain('推荐原因')
    expect(recommended.findAll('[data-testid="case-a-recommended-checkbox"]')).toHaveLength(1)
    // ⛔ 推荐里不出现"确认类"课程
    expect(recommended.text()).not.toContain('大学外语')

    expect(needConfirm.text()).toContain('需要你确认')
    expect(needConfirm.text()).toContain('大学外语')
    expect(needConfirm.text()).toContain('为什么需要确认')
    expect(needConfirm.findAll('[data-testid="case-a-confirmation-checkbox"]')).toHaveLength(1)
    // ⛔ 确认里不出现"推荐类"课程
    expect(needConfirm.text()).not.toContain('数据库系统原理')

    expect(wrapper.text()).not.toContain('待你确认的课程事项')
  })

  it('培养表中的人工确认课程统一进入推荐方案，重复条目只出现一次', () => {
    const value = plan([{ type: 'manual_confirmation', message: 'FL101 请核对' }, { type: 'manual_confirmation', message: 'FL101 请核对' }])
    expect(panel(value, [task]).findAll('[data-testid="case-a-unresolved-row"]')).toHaveLength(1)
    expect(panel(plan(), [task]).text()).toContain('大学外语')
    expect(panel(plan(), [task]).text()).toContain('课程编号：FL101')
    const table = mount(MakeupTaskList, { props: { tasks: [task], compactConfirmations: true } })
    expect(table.findAll('tr.task-row')).toHaveLength(1)
    expect(table.text()).toContain('大学外语')
    expect(table.text()).toContain('需要你的确认')
    // ⚠️ 设计变更（产品流程合并）：需要确认的课程现在**在培养表里直接勾选**，
    //    不再要求用户跳到推荐方案找同一个动作。因此这里**有**勾选框与确认按钮。
    expect(table.findAll('[data-testid="case-a-makeup-checkbox"]')).toHaveLength(1)
    expect(table.find('[data-testid="case-a-makeup-confirm-selection"]').exists()).toBe(true)
    // ⛔ 确认语义不变：不自动认定修读/满足
    expect(table.text()).toContain('不会')
    const adjustments = mount(PendingAdjustments, { props: { planResult: value, courseNameById: names } })
    expect(adjustments.text()).not.toContain('大学外语')
    expect(adjustments.findAll('input, button, details')).toHaveLength(0)
  })

  it('培养表的勾选与推荐方案共用同一份确认状态（不再重复两份）', async () => {
    const table = mount(MakeupTaskList, {
      props: { tasks: [task], compactConfirmations: true, confirmedKeys: ['course:FL101'] },
    })
    // 受控：父级已确认 → 显示「已确认」而不是勾选框
    expect(table.find('[data-testid="case-a-makeup-confirmed"]').exists()).toBe(true)
    expect(table.findAll('[data-testid="case-a-makeup-checkbox"]')).toHaveLength(0)

    // 勾选后点确认 → 发出与推荐方案一致的键格式
    const free = mount(MakeupTaskList, { props: { tasks: [task], compactConfirmations: true } })
    await free.find('[data-testid="case-a-makeup-checkbox"]').setValue(true)
    await free.find('[data-testid="case-a-makeup-confirm-selection"]').trigger('click')
    const emitted = free.emitted('update:confirmedKeys') as unknown[][]
    expect(emitted).toHaveLength(1)
    expect(emitted[0][0]).toEqual(['course:FL101'])
    // ⚠️ 受控组件：只 emit，不自行改判定。父级把键写回来后才会显示「已确认」。
    //    这里刻意断言它**没有**自行把判定改掉（⛔ 不自动认定修读/满足）。
    await free.setProps({ confirmedKeys: emitted[0][0] as string[] })
    expect(free.find('[data-testid="case-a-makeup-confirmed"]').exists()).toBe(true)
    // 判定状态列仍是「需要你的确认」，⛔ 未变成「已满足」之类结论
    const row = free.get('tr.task-row')
    expect(row.text()).toContain('需要你的确认')
    expect(row.text()).not.toContain('已满足')
  })
  it('补修、调整建议、风险内容保留，原始证据不泄漏', () => {
    const table = mount(MakeupTaskList, { props: { tasks: [{ ...task, status: 'required' }], compactConfirmations: true } })
    expect(table.text()).toContain('大学外语')
    expect(table.text()).toContain('需要补修')
    expect(table.text()).not.toMatch(forbidden)
    const value = plan()
    value.changes = [{ course_id: 'FL101', from_class: '01', to_class: '02', reason: '原班时间冲突' }]
    value.risks = [{ course_id: 'FL101', level: 'high', reason: '请核对修读期限' }]
    const wrapper = panel(value)
    expect(wrapper.text()).toContain('原班时间冲突')
    expect(wrapper.text()).toContain('请核对修读期限')
    expect(wrapper.text()).toContain('高风险')
    expect(wrapper.text()).not.toMatch(forbidden)
  })
})
