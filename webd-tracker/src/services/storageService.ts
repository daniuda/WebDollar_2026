import type { TrackerEntry } from '../types'

const STORAGE_KEY = 'webd-tracker-entries'
const INTERVAL_KEY = 'webd-tracker-refresh-interval'

export function getEntries(): TrackerEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as TrackerEntry[]) : []
  } catch {
    return []
  }
}

export function saveEntry(entry: TrackerEntry): void {
  const entries = getEntries()
  const idx = entries.findIndex((e) => e.address === entry.address)
  if (idx >= 0) {
    entries[idx] = entry
  } else {
    entries.push(entry)
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
}

export function deleteEntry(address: string): void {
  const entries = getEntries().filter((e) => e.address !== address)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
}

export function clearAll(): void {
  localStorage.removeItem(STORAGE_KEY)
}

export function getRefreshInterval(): number {
  return Number(localStorage.getItem(INTERVAL_KEY) ?? '15')
}

export function setRefreshInterval(minutes: number): void {
  localStorage.setItem(INTERVAL_KEY, String(minutes))
}
