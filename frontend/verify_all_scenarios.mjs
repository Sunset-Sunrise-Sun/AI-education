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
          { type: 'selection_required', message: '存在多个 CLEAR 候选，需要用户明确选择' },
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
      if (!html.includes('需要明确选择')) throw new Error('场景 4 失败：selection_required 未正确翻译')
      if (!html.includes('unrecognized_custom_type')) throw new Error('场景 4 失败：未知类型 fallback 未生效')

      console.log('  ✓ 成功渲染 manual_confirmation、missing_data、schedule_unknown、selection_required 及未知类型 fallback')
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
      if (!htmlPlan.includes('当前建议课表中暂无教学班') || !htmlPlan.includes('未返回方案变更记录')) {
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


    // 场景 8: feasible 不得暗示学校可直接执行
    console.log('[测试 8] feasible 文案不得过度承诺...')
    {
      const planResult = {
        status: 'feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [],
        objective_summary: null,
      }
      const app = createSSRApp({ render: () => h(PlanResultPanel, { planResult, courseNameById: {} }) })
      const html = await renderToString(app)
      if (html.includes('可直接执行')) throw new Error('场景 8 失败：feasible 仍包含“可直接执行”')
      if (!html.includes('不代表学校已经完成正式选课或审批')) throw new Error('场景 8 失败：feasible 边界说明缺失')
      console.log('  ✓ feasible 文案保持认证范围，不冒充学校执行结果')
    }

    // 场景 9: Preference 仅展示输入，不声称 Planner 已执行
    console.log('[测试 9] PreferencePanel 不得暗示 Planner 已执行...')
    {
      const preference = { avoid_cross_campus: true, max_credit: 20, preferred_courses: [], avoid_times: [] }
      const app = createSSRApp({ render: () => h(PreferencePanel, { preference, courseNameById: {} }) })
      const html = await renderToString(app)
      if (html.includes('将优先过滤') || html.includes('允许调度不同校区')) {
        throw new Error('场景 9 失败：PreferencePanel 仍包含越权求解文案')
      }
      if (!html.includes('以 PlanResult 输出为准')) throw new Error('场景 9 失败：Preference 边界声明缺失')
      console.log('  ✓ PreferencePanel 只展示偏好，不声称已被 Planner 执行')
    }

    // 场景 10: risks=[] 不得推断无风险
    console.log('[测试 10] risks=[] 不得推断无风险...')
    {
      const planResult = {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [],
        objective_summary: null,
      }
      const app = createSSRApp({ render: () => h(PlanResultPanel, { planResult, courseNameById: {} }) })
      const html = await renderToString(app)
      if (html.includes('未检测到显著方案风险')) throw new Error('场景 10 失败：risks=[] 被错误解释为无风险')
      if (!html.includes('本次 PlanResult 未返回风险项')) throw new Error('场景 10 失败：risks=[] 中性文案缺失')
      console.log('  ✓ risks=[] 仅表示本次未返回风险项')
    }

    // 场景 11: changes=[] 不得推断无需换班
    console.log('[测试 11] changes=[] 不得推断无需换班...')
    {
      const planResult = {
        status: 'partially_feasible',
        selected_classes: [],
        changes: [],
        risks: [],
        unresolved: [{ type: 'selection_required', message: '需要用户选择' }],
        objective_summary: null,
      }
      const app = createSSRApp({ render: () => h(PlanResultPanel, { planResult, courseNameById: {} }) })
      const html = await renderToString(app)
      if (html.includes('无需换班')) throw new Error('场景 11 失败：changes=[] 被错误解释为无需换班')
      if (!html.includes('未返回方案变更记录')) throw new Error('场景 11 失败：changes=[] 中性文案缺失')
      console.log('  ✓ changes=[] 仅表示没有返回变更记录')
    }

    // 场景 12: 容量展示不得引入 <=5 的业务阈值
    console.log('[测试 12] 容量展示无前端自造阈值...')
    {
      const fs = await import('fs')
      const source = fs.readFileSync('./src/components/CourseOfferingList.vue', 'utf-8')
      const css = fs.readFileSync('./src/styles/base.css', 'utf-8')
      if (source.includes('remaining_capacity <= 5') || source.includes('capacity-remain--low')) {
        throw new Error('场景 12 失败：组件仍包含容量阈值业务判断')
      }
      if (css.includes('.capacity-remain--low')) throw new Error('场景 12 失败：CSS 仍保留容量阈值样式')
      console.log('  ✓ 容量只展示数据，不自行判定紧俏')
    }

    // 场景 13: 地点缺失采用数据中性描述
    console.log('[测试 13] 地点缺失使用数据中性描述...')
    {
      const offerings = [{
        course_id: 'CS103',
        course_name: '地点未知课程',
        class_id: 'CS103-01',
        semester: '2026-1',
        meetings: [{ weekday: 2, start_section: 1, end_section: 2, weeks: [1,2] }],
        data_source: 'mock',
      }]
      const app = createSSRApp({ render: () => h(CourseOfferingList, { offerings }) })
      const html = await renderToString(app)
      if (!html.includes('当前数据中无地点信息')) throw new Error('场景 13 失败：地点中性文案缺失')
      if (html.includes('地点待公布')) throw new Error('场景 13 失败：仍在推断未来公布状态')
      console.log('  ✓ 地点缺失仅描述当前数据状态')
    }

    // 场景 14: 静态语义防回潮
    console.log('[测试 14] 前端业务语义静态防回潮...')
    {
      const fs = await import('fs')
      const files = [
        './src/App.vue',
        './src/components/PreferencePanel.vue',
        './src/components/PlanResultPanel.vue',
        './src/utils/labels.ts',
      ]
      const combined = files.map((path) => fs.readFileSync(path, 'utf-8')).join('\n')
      const forbidden = [
        '方案可直接执行',
        '核心排课可行',
        '求解器将优先过滤',
        '允许调度不同校区的可用教学班',
        '未检测到显著方案风险',
        '方案未发生教学班调整（无需换班）',
        '地点待公布',
      ]
      for (const phrase of forbidden) {
        if (combined.includes(phrase)) throw new Error(`场景 14 失败：发现过度业务推断文案“${phrase}”`)
      }
      console.log('  ✓ 关键越权文案均未回潮')
    }

    console.log('\n=== 全部 14 项关键场景自动化测试均已通过！===')
  } finally {
    await server.close()
  }
}

runTests().catch((err) => {
  console.error('\n❌ 测试失败:', err)
  process.exit(1)
})
