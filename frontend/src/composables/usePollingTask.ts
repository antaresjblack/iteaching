/** 通用轮询 composable：页面卸载/完成/失败/超时均自动清理定时器 */
import { onScopeDispose, readonly, ref } from 'vue'

export type PollingState = 'idle' | 'polling' | 'done' | 'failed' | 'timeout'

export interface UsePollingTaskOptions<T> {
  /** 轮询间隔，默认 5000ms */
  intervalMs?: number
  /** 总超时，默认 15 分钟；超时后 state 变为 timeout */
  timeoutMs?: number
  /** 依据最新数据判断是否结束轮询 */
  shouldStop: (data: T) => boolean
}

export function usePollingTask<T>(pollFn: () => Promise<T>, options: UsePollingTaskOptions<T>) {
  const { intervalMs = 5000, timeoutMs = 15 * 60 * 1000, shouldStop } = options

  const state = ref<PollingState>('idle')
  const data = ref<T | null>(null)
  const error = ref<Error | null>(null)

  let timer: ReturnType<typeof setInterval> | null = null
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null

  function clearTimers(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    if (timeoutTimer !== null) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
  }

  /** 立即执行一次轮询并决定是否继续 */
  async function tick(): Promise<void> {
    try {
      const result = await pollFn()
      data.value = result
      error.value = null
      if (shouldStop(result)) {
        state.value = 'done'
        clearTimers()
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      state.value = 'failed'
      clearTimers()
    }
  }

  /** 启动轮询；重复调用会先停止上一轮 */
  function start(): void {
    clearTimers()
    state.value = 'polling'
    error.value = null
    void tick()
    timer = setInterval(() => {
      void tick()
    }, intervalMs)
    timeoutTimer = setTimeout(() => {
      clearTimers()
      state.value = 'timeout'
    }, timeoutMs)
  }

  function stop(): void {
    clearTimers()
  }

  onScopeDispose(clearTimers)

  return { state: readonly(state), data: readonly(data), error: readonly(error), start, stop, tick }
}
