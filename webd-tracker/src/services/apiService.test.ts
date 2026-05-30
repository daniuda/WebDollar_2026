import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchCurrentBlock, fetchBatchBalances } from './apiService'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchCurrentBlock', () => {
  it('returns height from chain response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ height: 5777721 }),
    } as Response)

    const block = await fetchCurrentBlock()
    expect(block).toBe(5777721)
  })

  it('returns null on network error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network'))
    const block = await fetchCurrentBlock()
    expect(block).toBeNull()
  })
})

describe('fetchBatchBalances', () => {
  it('returns array of {address, balance, lastBlock} for given addresses', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { address: 'WEBD$abc', balance: 1000, lastBlock: 5777721 },
      ],
    } as Response)

    const results = await fetchBatchBalances(['WEBD$abc'])
    expect(results).toHaveLength(1)
    expect(results[0].balance).toBe(1000)
  })

  it('returns empty array on error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('fail'))
    const results = await fetchBatchBalances(['WEBD$abc'])
    expect(results).toEqual([])
  })

  it('returns empty array for empty input', async () => {
    const results = await fetchBatchBalances([])
    expect(results).toEqual([])
  })
})
