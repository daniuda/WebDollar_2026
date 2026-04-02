import axios from 'axios'
import type { PoolStats } from '../types/miner'
import { resolvePoolApiCandidates } from './poolAddress'

export async function fetchPoolStats(baseUrl: string): Promise<PoolStats> {
  const candidates = resolvePoolApiCandidates(baseUrl)
  let lastError: unknown = null
  let response: { data?: any } | null = null

  for (const candidate of candidates) {
    try {
      response = await axios.get(`${candidate}/pool/stats`, {
        timeout: 10_000,
      })
      break
    } catch (err) {
      lastError = err
    }
  }

  if (!response) {
    throw lastError instanceof Error ? lastError : new Error('Cannot fetch pool stats')
  }

  return {
    workersTotal: response.data?.workersTotal ?? 0,
    workersOnline: response.data?.workersOnline ?? 0,
    totalShares: response.data?.totalShares ?? 0,
    poolName: response.data?.poolName ?? 'Unknown pool',
    height: response.data?.height ?? 0,
    keyRequired: response.data?.keyRequired ?? false,
  }
}
