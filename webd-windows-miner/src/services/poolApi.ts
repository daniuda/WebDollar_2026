import axios from 'axios'
import type { PoolAddressReward, PoolStats } from '../types/miner'
import { resolvePoolApiBase, resolvePoolApiCandidates } from './poolAddress'

const WEBD_UNITS = 10_000

function unitsToWebd(units: number): number {
  return units / WEBD_UNITS
}

function toNumber(value: unknown): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  if (typeof value === 'string') {
    const normalized = value.trim().replace(/,/g, '')
    const n = Number(normalized)
    return Number.isFinite(n) ? n : 0
  }

  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function normalizeAddress(value: unknown): string {
  return String(value ?? '')
    .trim()
    // decode pool encoding: $ → /, # → O, @ → l
    .replace(/#/g, 'O')
    .replace(/\$/g, '/')
    .replace(/@/g, 'l')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

function getEntryAddress(entry: any): string {
  return String(
    entry?.address
    ?? entry?.minerAddress
    ?? entry?.walletAddress
    ?? entry?.wallet
    ?? '',
  )
}

function extractMinerList(payload: any): any[] {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.miners)) return payload.miners
  if (Array.isArray(payload?.data?.miners)) return payload.data.miners
  if (Array.isArray(payload?.data)) return payload.data
  // Sometimes pool returns single miner object directly (e.g., /pools/miners endpoint with address header)
  if (payload && typeof payload === 'object' && (payload.address || payload.minerAddress || payload.walletAddress)) {
    return [payload]
  }
  return []
}

function mapEntryToReward(entry: any, address: string, source: string): PoolAddressReward {
  const rewardTotalUnits = toNumber(entry?.reward_total ?? entry?.rewardTotal ?? entry?.reward)
  const rewardConfirmedUnits = toNumber(entry?.reward_confirmed ?? entry?.rewardConfirmed ?? entry?.confirmed)
  const rewardSentUnits = toNumber(entry?.reward_sent ?? entry?.rewardSent ?? entry?.sent)
  const walletBalanceUnitsPrimary = toNumber(
    entry?.totalPOSBalance
    ?? entry?.total_pos_balance
    ?? entry?.totalPOSBalanceUnits,
  )
  const walletBalanceUnitsFallback = toNumber(
    entry?.balance
    ?? entry?.balance_total
    ?? entry?.balanceTotal
    ?? entry?.wallet_balance
    ?? entry?.walletBalance
    ?? entry?.amount
    ?? entry?.stake,
  )
  const walletBalanceWebdDirect = toNumber(
    entry?.balanceWebd
    ?? entry?.walletBalanceWebd,
  )
  const walletBalanceUnits = walletBalanceUnitsPrimary > 0 ? walletBalanceUnitsPrimary : walletBalanceUnitsFallback
  const walletBalanceUnitsFromWebdDirect = walletBalanceWebdDirect > 0
    ? Math.round(walletBalanceWebdDirect * WEBD_UNITS)
    : walletBalanceUnits

  return {
    address,
    rewardTotalUnits,
    rewardConfirmedUnits,
    rewardSentUnits,
    walletBalanceUnits,
    rewardTotalWebd: unitsToWebd(rewardTotalUnits),
    rewardConfirmedWebd: unitsToWebd(rewardConfirmedUnits),
    rewardSentWebd: unitsToWebd(rewardSentUnits),
    walletBalanceWebd: unitsToWebd(walletBalanceUnitsFromWebdDirect),
    source,
  }
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

  // Public miner stats must always be requested from the remote pool host,
  // never from local fallback API.
  const candidates = [resolvePoolApiBase(baseUrl)]
  const normalizedTarget = normalizeAddress(address)
  // Prefer the pool miners endpoint for wallet totals (e.g. totalPOSBalance).
  // Some pools may return single miner directly, others return lists.
  const endpointPaths = ['/pools/miners', '/pools/all-miners']
  let lastError: unknown = null

  for (const candidate of candidates) {
    for (const endpointPath of endpointPaths) {
      try {
        const response = await axios.get(`${candidate}${endpointPath}`, {
          timeout: 10_000,
        })

        const list = extractMinerList(response.data)
        const found = list.find((entry: any) => normalizeAddress(getEntryAddress(entry)) === normalizedTarget)
        if (!found) {
          continue
        }

        return mapEntryToReward(found, address, `${candidate}${endpointPath}`)
      } catch (err) {
        lastError = err
      }
    }
  }

  if (lastError) {
    throw lastError instanceof Error ? lastError : new Error('Cannot fetch pool address rewards')
  }

  return null
}
