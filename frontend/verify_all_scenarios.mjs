import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

async function runTests() {
  console.log('=== 学航·转衔 前端综合场景验证 ===\n')

  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  })

  try {
    const { default: CourseOfferingList } = await server.ssrLoadModule('/src/components/CourseOfferingList.vue')
    const { default: PlanResultPanel } = await server.ssrLoadModule('/src/components/PlanResultPanel.vue')
    const { default: MakeupTaskList } = await server.ssrLoadModule('/src/components/MakeupTaskList.vue')
    const { default: PreferencePanel } = await server.ssrLoadModule('/src/components/PreferencePanel.vue')
    const { default: TopStatusBar } = await server.ssrLoadModule('/src/components/TopStatusBar.vue')
    const { default: SectionCard } = await server.ssrLoadModule('/src/components/SectionCard.vue')

    // 场景 1: 正常多 Meeting
    console.log('[测试 1] 正常多 Meeting 开课展示...')
    {
      const offerings = [
        {
          course_id: 'CS101',
          course_name: '计算机导论',
          class_id: 'CS101-01',
          semester: '2026-1',
          teacher: '张老师',
          credit: 3,
          meetings: [
            { weekday: 1, start_section: 1, end_section: 2, weeks: [1, 2, 3, 4], campus: '东校园', classroom: 'A101' },
            { weekday: 3, start_section: 3, end_section: 4, weeks: [1, 2, 3, 4], campus: '东校园', classroom: 'B202' },
          ],
          capacity: 60,
          remaining_capacity: 15,
          data_source: 'mock',
        },
      ]
      const app = createSSRApp({ render: () => h(CourseOfferingList, { offerings }) })
      const html = await renderToString(app)
      if (!html.includes('CS101-01') || !html.includes('张老师') || !html.includes('A101') || !html.includes('B202')) {
        throw new Error('场景 1 失败：多 Meeting 渲染不完整')
      }
      console.log('  ✓ 正常多 Meeting 成功渲染 2 段排课安排')
    }

    // 场景 2: meetings=[] 严格符合 DG-07D 规范
    console.log('[测试 2] DG-07D meetings=[] 中性数据状态展示...')
    {
      const offerings = [
        {
          course_id: 'CS102',
          course_name: '未知排课课程',
          class_id: 'CS102-01',
          semester: '2026-1',
          teacher: '李老师',
          credit: 2,
          meetings: [], // 空数组
          capacity: 40,
          remaining_capacity: 5,
          data_source: 'mock',
        },
      ]
      const app = createSSRApp({ render: () => h(CourseOfferingList, { offerings }) })
      const html = await renderToString(app)

      if (!html.includes('当前数据中无排课信息')) {
        throw new Error('场景 2 失败：未包含规范文本“当前数据中无排课信息”')
      }

      const forbidden = ['无课', '无需上课', '异步课程', '尚未排课', '无冲突']
      for (const phrase of forbidden) {
        if (html.includes(phrase)) {
          throw new Error(`场景 2 违规：包含了严禁推断的词汇“${phrase}”`)
        }
      }
      console.log('  ✓ 成功渲染“当前数据中无排课信息”，未包含任何违规推断词汇')
    }

    // 场景 3: feasible / partially_feasible / infeasible 方案状态
    console.log('[测试 3] feasible / partially_feasible / infeasible 三种方案状态...')
    for (const status of ['feasible', 'partially_feasible', 'infeasible']) {
      const planResult = {
        status,
        selected_classes: [{ course_id: 'CS101', class_id: 'CS101-01' }],
        changes: [],
        risks: [],
        unresolved: [],
        objective_summary: `方案状态为 ${status}`,
      }
      const app = createSSRApp({
        render: () => h(PlanResultPanel, { planResult, courseNameById: { CS101: '计算机导论' } }),
      })
      const html = await renderToString(app)
      if (!html.includes(`tag--plan-${status}`)) {
        throw new Error(`场景 3 失败：${status} 状态样式未正确挂载`)
      }
      console.log(`  ✓ 成功渲染 ${status} 方案`)
    }

    // 场景 4: unresolved 多类型与通用 fallback
    console.log('[测试 4] unresolved 多类型支持与 fallback...')
    {
      const planResult = {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [
          { type: 'manual_confirmation', message: '课程等价关系需教务人工核实' },
          { type: 'missing_data', message: '缺少开课教室详细数据' },
          { type: 'schedule_unknown', message: '选中的班级排课信息在数据源中未知' },
          { type: 'unrecognized_custom_type', message: '未来扩展的自定义未决类型' },
        ],
        objective_summary: '多类型 unresolved 测试',
      }
      const app = createSSRApp({
        render: () => h(PlanResultPanel, { planResult, courseNameById: {} }),
      })
      const html = await renderToString(app)

      if (!html.includes('待人工确认')) throw new Error('场景 4 失败：manual_confirmation 未正确翻译')
      if (!html.includes('缺少数据')) throw new Error('场景 4 失败：missing_data 未正确翻译')
      if (!html.includes('排课信息未知')) throw new Error('场景 4 失败：schedule_unknown 未正确翻译')
      if (!html.includes('unrecognized_custom_type')) throw new Error('场景 4 失败：未知类型 fallback 未生效')

      console.log('  ✓ 成功渲染 manual_confirmation、missing_data、schedule_unknown 及未知类型 fallback')
    }

    // 场景 5: 空列表测试
    console.log('[测试 5] 各组件空列表容错与空状态渲染...')
    {
      const appOffering = createSSRApp({ render: () => h(CourseOfferingList, { offerings: [] }) })
      const htmlOffering = await renderToString(appOffering)
      if (!htmlOffering.includes('教学班列表为空')) throw new Error('场景 5 失败：教学班空列表未提示')

      const appMakeup = createSSRApp({ render: () => h(MakeupTaskList, { tasks: [] }) })
      const htmlMakeup = await renderToString(appMakeup)
      if (!htmlMakeup.includes('补修任务')) throw new Error('场景 5 失败：补修任务空列表未正常呈现')

      const planEmpty = {
        status: 'feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [],
        objective_summary: null,
      }
      const appPlan = createSSRApp({
        render: () => h(PlanResultPanel, { planResult: planEmpty, courseNameById: {} }),
      })
      const htmlPlan = await renderToString(appPlan)
      if (!htmlPlan.includes('无已排定教学班') || !htmlPlan.includes('无需换班')) {
        throw new Error('场景 5 失败：PlanResult 空列表提示不完善')
      }
      console.log('  ✓ 所有空列表边界均优雅呈现友好提示')
    }

    // 场景 6: 长文本容错测试
    console.log('[测试 6] 长文本排版与安全换行...')
    {
      const longName = '超级长课程名称'.repeat(10)
      const longReason = '这是一个非常非常长的课程认定说明，包含了历史培养方案与最新版本教学大纲的全面比对。'.repeat(5)
      const longEvidence = '中山大学本科教务文件〔2026〕62号第七章第四节关于学分折算的官方说明'.repeat(3)

      const tasks = [
        {
          course_id: 'LONG001',
          course_name: longName,
          credit: 4,
          status: 'required',
          recommended_semester: 3,
          deadline_semester: 5,
          prerequisites: ['MATH101', 'CS100', 'PHYS001'],
          reason: longReason,
          source_evidence: longEvidence,
        },
      ]
      const app = createSSRApp({ render: () => h(MakeupTaskList, { tasks }) })
      const html = await renderToString(app)
      if (!html.includes(longName) || !html.includes('依据：')) {
        throw new Error('场景 6 失败：长文本渲染异常')
      }
      console.log('  ✓ 超长课程名、详细认定理由与证据文本渲染正常')
    }

    // 场景 7: 小屏幕与响应式规则检查
    console.log('[测试 7] 样式表与响应式适配规则...')
    {
      const fs = await import('fs')
      const css = fs.readFileSync('./src/styles/base.css', 'utf-8')
      if (!css.includes('@media (max-width: 860px)')) throw new Error('未定义 860px 平板断点')
      if (!css.includes('@media (max-width: 640px)')) throw new Error('未定义 640px 手机断点')
      console.log('  ✓ 响应式断点完整支持 (860px / 640px)')
    }

    console.log('\n=== 全部 7 项关键场景自动化测试均已通过！===')
  } finally {
    await server.close()
  }
}

runTests().catch((err) => {
  console.error('\n❌ 测试失败:', err)
  process.exit(1)
})
