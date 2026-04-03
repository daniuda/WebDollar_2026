export interface DesktopAppConfig {
  poolUrl: string
  walletAddress: string
  walletEncrypted: string
  poolKey: string
  threadCount: number
  autoStart: boolean
  simpleMode: boolean
  payoutTarget: number
}

export interface GeneratedWallet {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

export interface AuthResult {
  token: string
  workerId: string
  reward: number
  confirmed: number
  poolName: string
  poolFee: number
  keyRequired: boolean
}

export interface MiningJob {
  jobId: string
  height: number
  target: string
  blockHeader: string
  nonceStart: number
  nonceEnd: number
  expireAt: number
}

export interface MiningResult {
  nonce: number
  hashHex: string
  hashesTried: number
  timeDiffMs: number
}

export interface ShareResult {
  result: string
  message: string
}

export interface WorkerStats {
  workerId: string
  walletAddress: string
  lastSeen: number
  online: boolean
  sharesAccepted: number
  sharesRejected: number
  sharesStale: number
  rewardPending: number
  rewardConfirmed: number
  protocolEvents: string[]
}

export interface PoolStats {
  workersTotal: number
  workersOnline: number
  totalShares: number
  poolName: string
  height: number
  keyRequired: boolean
}

export interface PoolAddressReward {
  address: string
  rewardTotalUnits: number
  rewardConfirmedUnits: number
  rewardSentUnits: number
  rewardTotalWebd: number
  rewardConfirmedWebd: number
  rewardSentWebd: number
  source: string
}

export interface AppMeta {
  version: string
  platform: string
}
