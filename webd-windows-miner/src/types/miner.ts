export interface DesktopAppConfig {
  poolUrl: string
  walletAddress: string
  walletEncrypted: string
  poolKey: string
  threadCount: number
  autoStart: boolean
}

export interface GeneratedWallet {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

export interface PoolStats {
  workersTotal: number
  workersOnline: number
  totalShares: number
  poolName: string
  height: number
  keyRequired: boolean
}

export interface AppMeta {
  version: string
  platform: string
}
