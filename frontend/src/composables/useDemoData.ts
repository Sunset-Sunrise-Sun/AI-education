import { ref } from 'vue'
import { fetchDemo } from '../api/demo'
import type { DemoPayload } from '../types/contracts'

/** 页面只有三种状态：加载中 / 加载成功 / 请求失败。 */
export type LoadState = 'loading' | 'success' | 'error'

/**
 * Demo 数据加载状态机。
 *
 * 关键约定：请求失败时 `data` 一定保持 `null`。
 * 页面因此不可能"在后端挂掉时自己编一份数据继续演示"——这是本项目明确的红线。
 */
export function useDemoData() {
  const state = ref<LoadState>('loading')
  const data = ref<DemoPayload | null>(null)
  const dataSource = ref<string | null>(null)
  const errorMessage = ref('')

  async function load(): Promise<void> {
    state.value = 'loading'
    data.value = null
    dataSource.value = null
    errorMessage.value = ''

    try {
      const result = await fetchDemo()
      data.value = result.data
      dataSource.value = result.dataSource
      state.value = 'success'
    } catch (error) {
      data.value = null
      dataSource.value = null
      errorMessage.value =
        error instanceof Error ? error.message : '发生了未知错误，请查看浏览器控制台。'
      state.value = 'error'
    }
  }

  return { state, data, dataSource, errorMessage, load }
}
