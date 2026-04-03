/// <reference types="vite/client" />

interface DesktopAppConfig {
  poolUrl: string
  walletAddress: string
  walletEncrypted: string
  poolKey: string
  threadCount: number
  autoStart: boolean
  simpleMode: boolean
  payoutTarget: number
}

interface GeneratedWallet {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

interface Window {
  desktopApi?: {
    getMeta: () => Promise<{ version: string; platform: string }>
    loadConfig: () => Promise<DesktopAppConfig>
    saveConfig: (config: Partial<DesktopAppConfig>) => Promise<DesktopAppConfig>
    generateWallet: () => Promise<GeneratedWallet>
    importWalletRaw: (raw: string) => Promise<GeneratedWallet>
    selectWalletFileRaw: () => Promise<string | null>
    exportLegacyWallet: (secretHex: string) => Promise<string>
    encryptSecret: (secretHex: string, passphrase: string) => Promise<string>
    decryptSecret: (envelopeJson: string, passphrase: string) => Promise<string>
    legacyConnect: (poolAddress: string, walletAddress: string, wallet?: GeneratedWallet) => Promise<{ token: string; workerId: string; poolName: string; poolFee: number }>
    legacyGetJob: (token: string) => Promise<{ jobId: string; height: number; target: string; blockHeader: string; nonceStart: number; nonceEnd: number; expireAt: number }>
    legacySubmitShare: (token: string, jobId: string, nonce: number, hashHex: string, hashes?: number, timeDiff?: number) => Promise<{ result: string; message: string }>
    legacyGetWorkerStats: (token: string) => Promise<any>
    legacyGetPoolStats: () => Promise<any>
  }
}
