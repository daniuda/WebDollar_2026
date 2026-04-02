import type { AppMeta, DesktopAppConfig, GeneratedWallet } from '../types/miner'

export function getDesktopMeta(): Promise<AppMeta> {
  return window.desktopApi.getMeta()
}

export function loadDesktopConfig(): Promise<DesktopAppConfig> {
  return window.desktopApi.loadConfig()
}

export function saveDesktopConfig(config: Partial<DesktopAppConfig>): Promise<DesktopAppConfig> {
  return window.desktopApi.saveConfig(config)
}

export function generateDesktopWallet(): Promise<GeneratedWallet> {
  return window.desktopApi.generateWallet()
}

export function importDesktopWalletRaw(raw: string): Promise<GeneratedWallet> {
  return window.desktopApi.importWalletRaw(raw)
}

export function exportDesktopLegacyWallet(secretHex: string): Promise<string> {
  return window.desktopApi.exportLegacyWallet(secretHex)
}

export function encryptDesktopSecret(secretHex: string, passphrase: string): Promise<string> {
  return window.desktopApi.encryptSecret(secretHex, passphrase)
}

export function decryptDesktopSecret(envelopeJson: string, passphrase: string): Promise<string> {
  return window.desktopApi.decryptSecret(envelopeJson, passphrase)
}
