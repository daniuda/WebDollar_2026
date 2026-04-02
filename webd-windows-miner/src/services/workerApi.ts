import axios from 'axios'
import type { AuthResult, MiningJob, ShareResult, WorkerStats } from '../types/miner'
import { resolvePoolApiCandidates } from './poolAddress'

function normalizeBaseUrl(baseUrl: string): string {
  return resolvePoolApiCandidates(baseUrl)[0]
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