/**
 * Mock 数据切换工具
 * 通过 VITE_USE_MOCK 环境变量控制是否使用 Mock 数据
 * .env.development: VITE_USE_MOCK=true
 * .env.production:  VITE_USE_MOCK=false
 */

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/**
 * 如果 VITE_USE_MOCK=true，直接返回 mockData（模拟网络延迟 delay ms）
 * 否则执行真实 apiCall
 */
export function withMock<T>(apiCall: () => Promise<T>, mockData: T, delay = 500): Promise<T> {
  if (USE_MOCK) {
    return new Promise((resolve) => setTimeout(() => resolve(mockData), delay))
  }
  return apiCall()
}

export { USE_MOCK }
