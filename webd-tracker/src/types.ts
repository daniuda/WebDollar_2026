export interface TrackerEntry {
  address: string
  label: string
  balance: number | null
  lastBlock: number
  lastUpdated: string
  error?: boolean
}

export type RefreshInterval = 0 | 5 | 15 | 30 | 60
