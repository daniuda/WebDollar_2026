import axios from 'axios'
import type { AuthResult, MiningJob, ShareResult, WorkerStats } from '../types/miner'
import { resolvePoolApiCandidates } from './poolAddress'

function normalizeBaseUrl(baseUrl: string): string {
  return resolvePoolApiCandidates(baseUrl)[0]
}

function isLegacyPool(baseUrl: string): boolean {
  return baseUrl.trim().startsWith('pool/')
}

async function withBaseFallback<T>(baseUrl: string, call: (normalizedBase: string) => Promise<T>): Promise<T> {
  const candidates = resolvePoolApiCandidates(baseUrl)
  let lastError: unknown = null

  for (const candidate of candidates) {
    try {
      return await call(candidate)
    } catch (err) {
      lastError = err
    }
  }

  if (lastError instanceof Error) {
    if (baseUrl.trim().startsWith('pool/')) {
      throw new Error(`Pool legacy nu expune endpoint-urile REST /worker/* direct. Ruleaza backend-ul API local (ex: http://127.0.0.1:3001). Detalii: ${lastError.message}`)
    }
    throw lastError
  }

  throw new Error('Worker API request failed')
}

export async function authWorker(baseUrl: string, walletAddress: string, poolKey: string, existingWorkerId = ''): Promise<AuthResult> {
  if (isLegacyPool(baseUrl) && window.desktopApi?.legacyConnect) {
    const legacy = await window.desktopApi.legacyConnect(baseUrl, walletAddress)
    return {
      token: legacy.token,
      workerId: legacy.workerId,
      reward: 0,
      confirmed: 0,
      poolName: legacy.poolName,
      poolFee: legacy.poolFee,
      keyRequired: false,
    }
  }

  const response = await withBaseFallback(baseUrl, (normalizedBase) => axios.post(`${normalizedBase}/worker/auth`, {
    walletAddress,
    workerId: existingWorkerId || undefined,
    poolKey: poolKey || undefined,
  }, {
    timeout: 10_000,
  }))

  return {
    token: response.data?.token ?? '',
    workerId: response.data?.workerId ?? '',
    reward: response.data?.reward ?? 0,
    confirmed: response.data?.confirmed ?? 0,
    poolName: response.data?.poolName ?? '',
    poolFee: response.data?.poolFee ?? 0,
    keyRequired: response.data?.keyRequired ?? false,
  }
}

export async function fetchWorkerJob(baseUrl: string, token: string): Promise<MiningJob> {
  if (isLegacyPool(baseUrl) && window.desktopApi?.legacyGetJob) {
    return window.desktopApi.legacyGetJob(token)
  }

  const response = await withBaseFallback(baseUrl, (normalizedBase) => axios.get(`${normalizedBase}/worker/job`, {
    params: { token },
    timeout: 10_000,
  }))

  const job = response.data?.job ?? {}

  return {
    jobId: job.jobId ?? '',
    height: job.height ?? 0,
    target: job.target ?? '',
    blockHeader: job.blockHeader ?? '',
    nonceStart: job.nonceStart ?? 0,
    nonceEnd: job.nonceEnd ?? 0,
    expireAt: job.expireAt ?? 0,
  }
}

export async function submitWorkerShare(baseUrl: string, token: string, jobId: string, nonce: number, hash: string): Promise<ShareResult> {
  if (isLegacyPool(baseUrl) && window.desktopApi?.legacySubmitShare) {
    return window.desktopApi.legacySubmitShare(token, jobId, nonce, hash)
  }

  const response = await withBaseFallback(baseUrl, (normalizedBase) => axios.post(`${normalizedBase}/worker/share`, {
    token,
    jobId,
    nonce,
    hash,
  }, {
    timeout: 10_000,
  }))

  return {
    result: response.data?.result ?? 'invalid',
    message: response.data?.message ?? '',
  }
}

export async function fetchWorkerStats(baseUrl: string, token: string): Promise<WorkerStats> {
  if (isLegacyPool(baseUrl) && window.desktopApi?.legacyGetWorkerStats) {
    const legacy = await window.desktopApi.legacyGetWorkerStats(token)
    return {
      workerId: legacy?.workerId ?? '',
      walletAddress: legacy?.walletAddress ?? '',
      lastSeen: legacy?.lastSeen ?? Date.now(),
      online: legacy?.online ?? false,
      sharesAccepted: legacy?.sharesAccepted ?? 0,
      sharesRejected: legacy?.sharesRejected ?? 0,
      sharesStale: legacy?.sharesStale ?? 0,
      rewardPending: legacy?.rewardPending ?? 0,
      rewardConfirmed: legacy?.rewardConfirmed ?? 0,
    }
  }

  const response = await withBaseFallback(baseUrl, (normalizedBase) => axios.get(`${normalizedBase}/worker/stats`, {
    params: { token },
    timeout: 10_000,
  }))

  return {
    workerId: response.data?.workerId ?? '',
    walletAddress: response.data?.walletAddress ?? '',
    lastSeen: response.data?.lastSeen ?? 0,
    online: response.data?.online ?? false,
    sharesAccepted: response.data?.sharesAccepted ?? 0,
    sharesRejected: response.data?.sharesRejected ?? 0,
    sharesStale: response.data?.sharesStale ?? 0,
    rewardPending: response.data?.rewardPending ?? 0,
    rewardConfirmed: response.data?.rewardConfirmed ?? 0,
  }
}