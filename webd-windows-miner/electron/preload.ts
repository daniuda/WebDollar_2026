import { contextBridge, ipcRenderer } from 'electron'

type AppConfig = {
  poolUrl: string
  walletAddress: string
  walletEncrypted: string
  poolKey: string
  threadCount: number
  autoStart: boolean
}

type GeneratedWallet = {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

contextBridge.exposeInMainWorld('desktopApi', {
  getMeta: () => ipcRenderer.invoke('app:get-meta') as Promise<{ version: string; platform: string }>,
  loadConfig: () => ipcRenderer.invoke('config:load') as Promise<AppConfig>,
  saveConfig: (config: Partial<AppConfig>) => ipcRenderer.invoke('config:save', config) as Promise<AppConfig>,
  generateWallet: () => ipcRenderer.invoke('wallet:generate') as Promise<GeneratedWallet>,
  importWalletRaw: (raw: string) => ipcRenderer.invoke('wallet:import-raw', raw) as Promise<GeneratedWallet>,
  exportLegacyWallet: (secretHex: string) => ipcRenderer.invoke('wallet:export-legacy', secretHex) as Promise<string>,
  encryptSecret: (secretHex: string, passphrase: string) => ipcRenderer.invoke('wallet:encrypt-secret', secretHex, passphrase) as Promise<string>,
  decryptSecret: (envelopeJson: string, passphrase: string) => ipcRenderer.invoke('wallet:decrypt-secret', envelopeJson, passphrase) as Promise<string>,
})
