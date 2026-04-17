import { resolvePoolApiBase } from './poolAddress'

export type TxNetworkStatus = 'unknown' | 'propagated' | 'confirmed'

function resolveTxGetUrl(poolUrl: string, txId: string): string {
  const base = resolvePoolApiBase(poolUrl)
  return `${base}/transactions/get/${encodeURIComponent(txId)}`
}

function resolveTxExistsUrl(poolUrl: string, txId: string): string {
  const base = resolvePoolApiBase(poolUrl)
  return `${base}/transactions/exists/${encodeURIComponent(txId)}`
}

function resolveTxPendingUrl(poolUrl: string): string {
  const base = resolvePoolApiBase(poolUrl)
  return `${base}/transactions/pending/object`
}

function resolveTxPendingListUrl(poolUrl: string): string {
  const base = resolvePoolApiBase(poolUrl)
  return `${base}/transactions/pending`
}

function isJsonResponse(resp: Response): boolean {
  return (resp.headers.get('content-type') || '').toLowerCase().includes('application/json')
}

function pendingContainsTx(data: unknown, txId: string): boolean {
  if (!data) return false

  if (typeof data === 'string') {
    const normalized = data.toLowerCase().replace(/^0x/, '')
    return normalized === txId.toLowerCase()
  }

  if (Array.isArray(data)) {
    return data.some((item) => pendingContainsTx(item, txId))
  }

  if (typeof data === 'object') {
    const record = data as Record<string, unknown>

    // Node-WebDollar may serialize Buffer fields as { type: 'Buffer', data: number[] }
    if (
      record.type === 'Buffer'
      && Array.isArray(record.data)
      && record.data.every((value) => typeof value === 'number')
    ) {
      const hex = (record.data as number[])
        .map((value) => value.toString(16).padStart(2, '0'))
        .join('')
      return hex.toLowerCase() === txId.toLowerCase()
    }

    if (typeof record.txId === 'string' && record.txId.toLowerCase() === txId.toLowerCase()) {
      return true
    }

    if (typeof record.hash === 'string' && record.hash.toLowerCase() === txId.toLowerCase()) {
      return true
    }

    return Object.entries(record).some(([key, value]) => {
      if (key.toLowerCase() === txId.toLowerCase()) return true
      return pendingContainsTx(value, txId)
    })
  }

  return false
}

export function explorerTxUrl(poolUrl: string, txId: string): string {
  return resolveTxGetUrl(poolUrl, txId)
}

export async function checkTxConfirmed(poolUrl: string, txId: string): Promise<boolean> {
  try {
    const resp = await fetch(resolveTxExistsUrl(poolUrl, txId), { signal: AbortSignal.timeout(8000) })
    if (!resp.ok || !isJsonResponse(resp)) return false
    const data = await resp.json()
    return !!(data?.result || data?.exists || data?.height)
  } catch {
    return false
  }
}

export async function checkTxPropagated(poolUrl: string, txId: string): Promise<boolean> {
  try {
    const pendingObjectResp = await fetch(resolveTxPendingUrl(poolUrl), { signal: AbortSignal.timeout(8000) })
    if (pendingObjectResp.ok && isJsonResponse(pendingObjectResp)) {
      const pendingObjectData = await pendingObjectResp.json()
      if (pendingContainsTx(pendingObjectData, txId)) return true
    }

    const pendingListResp = await fetch(resolveTxPendingListUrl(poolUrl), { signal: AbortSignal.timeout(8000) })
    if (pendingListResp.ok && isJsonResponse(pendingListResp)) {
      const pendingListData = await pendingListResp.json()
      if (pendingContainsTx(pendingListData, txId)) return true
    }

    return false
  } catch {
    return false
  }
}

export async function getTxNetworkStatus(poolUrl: string, txId: string): Promise<TxNetworkStatus> {
  if (await checkTxConfirmed(poolUrl, txId)) {
    return 'confirmed'
  }

  if (await checkTxPropagated(poolUrl, txId)) {
    return 'propagated'
  }

  return 'unknown'
}

export function pollTxConfirmed(
  poolUrl: string,
  txId: string,
  onStatus: (status: TxNetworkStatus, done?: boolean, attempts?: number) => void,
  intervalMs = 10_000,
  maxAttempts = 18, // ~3 minutes
): () => void {
  let attempts = 0
  let stopped = false

  const stop = () => {
    stopped = true
    clearInterval(timer)
  }

  const checkOnce = async () => {
    if (stopped) return
    attempts++
    const status = await getTxNetworkStatus(poolUrl, txId)
    const done = status === 'confirmed' || attempts >= maxAttempts
    onStatus(status, done, attempts)
    if (status === 'confirmed' || attempts >= maxAttempts) {
      stop()
    }
  }

  // Run an immediate first check, then continue by interval.
  void checkOnce()
  const timer = setInterval(() => {
    void checkOnce()
  }, intervalMs)

  return stop
}
