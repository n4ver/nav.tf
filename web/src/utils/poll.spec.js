import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { pollUntil } from './poll'

describe('pollUntil', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resolves immediately when the predicate is truthy on the first call', async () => {
    // Arrange
    const predicate = vi.fn().mockResolvedValue('done')

    // Act
    const result = await pollUntil(predicate)

    // Assert
    expect(result).toBe('done')
    expect(predicate).toHaveBeenCalledTimes(1)
  })

  it('retries on the interval until the predicate succeeds', async () => {
    // Arrange
    const predicate = vi
      .fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false)
      .mockResolvedValue(true)

    // Act
    const pending = pollUntil(predicate, { intervalMs: 100, timeoutMs: 1000 })
    await vi.advanceTimersByTimeAsync(250)
    const result = await pending

    // Assert
    expect(result).toBe(true)
    expect(predicate).toHaveBeenCalledTimes(3)
  })

  it('returns the last falsy result once the timeout elapses', async () => {
    // Arrange
    const predicate = vi.fn().mockResolvedValue(0)

    // Act
    const pending = pollUntil(predicate, { intervalMs: 100, timeoutMs: 350 })
    await vi.advanceTimersByTimeAsync(500)
    const result = await pending

    // Assert
    expect(result).toBe(0)
    expect(predicate.mock.calls.length).toBeGreaterThanOrEqual(3)
  })
})
