const BASE = 'https://webdollar.cloudns.nz'

export async function fetchCurrentBlock(): Promise<number | null> {
  try {
    const resp = await fetch(`${BASE}/api/chain`)
    if (!resp.ok) return null
    const data = await resp.json() as { height?: number }
    return typeof data.height === 'number' ? data.height : null
  } catch {
    return null
  }
}

export interface BatchResult {
  address: string
  balance: number | null
  lastBlock: number | null
}

export async function fetchBatchBalances(addresses: string[]): Promise<BatchResult[]> {
  if (addresses.length === 0) return []
  try {
    const addrs = addresses.map(encodeURIComponent).join(',')
    const resp = await fetch(`${BASE}/api/addresses/batch?addrs=${addrs}`)
    if (!resp.ok) return []
    return await resp.json() as BatchResult[]
  } catch {
    return []
  }
}
