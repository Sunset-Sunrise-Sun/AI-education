/**
 * 规划结果的**前端指纹**（用于 AI 调整的 `plan_digest`）。
 *
 * 边界：
 * - 这里只做"把当前页面上的方案变成一个稳定的短标识"，**不做任何业务判断**；
 * - ⛔ 它不是公共契约字段，也不代替后端的结果版本号；
 * - 后端返回的 `adopted_digest` 优先使用（那是服务端的权威标识）。
 *
 * 用 `crypto.subtle`（浏览器 / jsdom 均可用）计算真正的内容摘要，
 * 从而避免用递增计数器这类"看起来像摘要其实不是"的值冒充指纹。
 */

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value ?? null)
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(',')}]`
  }
  const record = value as Record<string, unknown>
  const keys = Object.keys(record).sort()
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`
}

/** 计算 `plan_digest`：`sha256:<hex>`。 */
export async function computePlanDigest(plan: unknown): Promise<string> {
  const text = canonicalJson(plan)
  const bytes = new TextEncoder().encode(text)

  if (typeof crypto !== 'undefined' && crypto.subtle !== undefined) {
    const buffer = await crypto.subtle.digest('SHA-256', bytes)
    const hex = [...new Uint8Array(buffer)]
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('')
    return `sha256:${hex}`
  }

  // 环境不支持 WebCrypto 时**如实降级**：使用一个明确标注的非加密标识，
  // ⛔ 不把它伪装成 sha256。
  let hash = 0
  for (const byte of bytes) {
    hash = (hash * 31 + byte) % 0xffffffff
  }
  return `local-fnv:${hash.toString(16)}`
}
