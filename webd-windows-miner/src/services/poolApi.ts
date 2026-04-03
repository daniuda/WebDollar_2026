import axios from 'axios'
import type { PoolAddressReward, PoolStats } from '../types/miner'
import { resolvePoolApiBase, resolvePoolApiCandidates } from './poolAddress'

const WEBD_UNITS = 10_000

function unitsToWebd(units: number): number {
  return units / WEBD_UNITS
}

export async function fetchPoolStats(baseUrl: string): Promise<PoolStats> {
  if (baseUrl.trim().startsWith('pool/') && typeof window !== 'undefined' && window.desktopApi?.legacyGetPoolStats) {
    const legacyStats = await window.desktopApi.legacyGetPoolStats()
    return {
      workersTotal: legacyStats?.workersTotal ?? 0,
      workersOnline: legacyStats?.workersOnline ?? 0,
      totalShares: legacyStats?.totalShares ?? 0,
      poolName: legacyStats?.poolName ?? 'Legacy pool',
      height: legacyStats?.height ?? 0,
      keyRequired: false,
    }
  }

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

export async function fetchPoolAddressReward(baseUrl: string, walletAddress: string): Promise<PoolAddressReward | null> {
  const address = walletAddress.trim()
  if (!address) return null

  const primary = resolvePoolApiBase(baseUrl)
  const candidates = [primary]
  let lastError: unknown = null

  for (const candidate of candidates) {
    try {
      const response = await axios.get(`${candidate}/pools/all-miners`, {
        timeout: 10_000,
      })

      const list = Array.isArray(response.data) ? response.data : []
      const found = list.find((entry: any) => String(entry?.address ?? '').trim() === address)
      if (!found) {
        continue
      }

      const rewardTotalUnits = Number(found?.reward_total ?? 0)
      const rewardConfirmedUnits = Number(found?.reward_confirmed ?? 0)
      const rewardSentUnits = Number(found?.reward_sent ?? 0)

      return {
        address,
        rewardTotalUnits,
        rewardConfirmedUnits,
        rewardSentUnits,
        rewardTotalWebd: unitsToWebd(rewardTotalUnits),
        rewardConfirmedWebd: unitsToWebd(rewardConfirmedUnits),
        rewardSentWebd: unitsToWebd(rewardSentUnits),
        source: candidate,
      }
    } catch (err) {
      lastError = err
    }
  }

  if (lastError) {
    throw lastError instanceof Error ? lastError : new Error('Cannot fetch pool address rewards')
  }

  return null
}
