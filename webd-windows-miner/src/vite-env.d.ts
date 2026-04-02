/// <reference types="vite/client" />

interface DesktopAppConfig {
  poolUrl: string
  walletAddress: string
  walletEncrypted: string
  poolKey: string
  threadCount: number
  autoStart: boolean
}

interface GeneratedWallet {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

interface Window {
  desktopApi: {
    getMeta: () => Promise<{ version: string; platform: string }>
    loadConfig: () => Promise<DesktopAppConfig>
    saveConfig: (config: Partial<DesktopAppConfig>) => Promise<DesktopAppConfig>
    generateWallet: () => Promise<GeneratedWallet>
    importWalletRaw: (raw: string) => Promise<GeneratedWallet>
    exportLegacyWallet: (secretHex: string) => Promise<string>
    encryptSecret: (secretHex: string, passphrase: string) => Promise<string>
    decryptSecret: (envelopeJson: string, passphrase: string) => Promise<string>
  }
}
