import axios from 'axios'
import type { PoolStats } from '../types/miner'
import { resolvePoolApiBase } from './poolAddress'

export async function fetchPoolStats(baseUrl: string): Promise<PoolStats> {
  const normalized = resolvePoolApiBase(baseUrl)
  const response = await axios.get(`${normalized}/pool/stats`, {
    timeout: 10_000,
  })

  return {
    workersTotal: response.data?.workersTotal ?? 0,
    workersOnline: response.data?.workersOnline ?? 0,
    totalShares: response.data?.totalShares ?? 0,
    poolName: response.data?.poolName ?? 'Unknown pool',
    height: response.data?.height ?? 0,
    keyRequired: response.data?.keyRequired ?? false,
  }
}
