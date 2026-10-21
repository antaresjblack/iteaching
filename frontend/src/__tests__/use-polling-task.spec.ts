import { describe, expect, it, vi } from 'vitest'

import { usePollingTask } from '@/composables/usePollingTask'

describe('usePollingTask 轮询', () => {
  it('轮询至满足停止条件后自动停止并置为 done', async () => {
    vi.useFakeTimers()
    let count = 0
    const pollFn = vi.fn(async () => ++count)
    const polling = usePollingTask(pollFn, {
      intervalMs: 100,
      shouldStop: (value) => value >= 2,
    })

    polling.start()
    expect(polling.state.value).toBe('polling')

    // start 时立即执行 1 次（count=1），100ms 定时第 1 次（count=2）后满足停止条件
    await vi.advanceTimersByTimeAsync(100)
    await vi.advanceTimersByTimeAsync(100)
    expect(polling.state.value).toBe('done')
    expect(polling.data.value).toBe(2)
    expect(pollFn).toHaveBeenCalledTimes(2)

    // 停止后不再轮询
    await vi.advanceTimersByTimeAsync(1000)
    expect(pollFn).toHaveBeenCalledTimes(2)
    polling.stop()
    vi.useRealTimers()
  })

  it('轮询函数抛错时停止并置为 failed', async () => {
    vi.useFakeTimers()
    const pollFn = vi.fn(async () => {
      throw new Error('network down')
    })
    const polling = usePollingTask(pollFn, { intervalMs: 100, shouldStop: () => false })

    polling.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(polling.state.value).toBe('failed')
    expect(polling.error.value?.message).toBe('network down')
    polling.stop()
    vi.useRealTimers()
  })

  it('超过超时时间后置为 timeout 并清理定时器', async () => {
    vi.useFakeTimers()
    const pollFn = vi.fn(async () => null)
    const polling = usePollingTask(pollFn, {
      intervalMs: 100,
      timeoutMs: 250,
      shouldStop: () => false,
    })

    polling.start()
    await vi.advanceTimersByTimeAsync(250)
    expect(polling.state.value).toBe('timeout')

    await vi.advanceTimersByTimeAsync(1000)
    expect(pollFn.mock.calls.length).toBeLessThanOrEqual(3)
    polling.stop()
    vi.useRealTimers()
  })

  it('stop 后不再执行任何轮询', async () => {
    vi.useFakeTimers()
    const pollFn = vi.fn(async () => 1)
    const polling = usePollingTask(pollFn, { intervalMs: 100, shouldStop: () => false })

    polling.start()
    await vi.advanceTimersByTimeAsync(100)
    polling.stop()
    const callsAfterStop = pollFn.mock.calls.length
    await vi.advanceTimersByTimeAsync(1000)
    expect(pollFn.mock.calls.length).toBe(callsAfterStop)
    vi.useRealTimers()
  })
})
