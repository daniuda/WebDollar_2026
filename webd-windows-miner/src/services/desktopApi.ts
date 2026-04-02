import type { AppMeta, DesktopAppConfig, GeneratedWallet } from '../types/miner'
import { getDefaultPoolAddress } from './poolAddress'

const CONFIG_KEY = 'webd_windows_miner_config'

const fallbackConfig: DesktopAppConfig = {
  poolUrl: getDefaultPoolAddress(),
  walletAddress: '',
  walletEncrypted: '',
  poolKey: '',
  threadCount: 1,
  autoStart: false,
}

function hasDesktopApi(): boolean {
  return typeof window !== 'undefined' && !!window.desktopApi
}

function getDesktopApi() {
  return typeof window !== 'undefined' ? window.desktopApi : undefined
}

function loadLocalConfig(): DesktopAppConfig {
  try {
    const raw = localStorage.getItem(CONFIG_KEY)
    if (!raw) return { ...fallbackConfig }
    const parsed = JSON.parse(raw) as Partial<DesktopAppConfig>
    return { ...fallbackConfig, ...parsed, threadCount: 1 }
  } catch {
    return { ...fallbackConfig }
  }
}

function saveLocalConfig(config: Partial<DesktopAppConfig>): DesktopAppConfig {
  const merged = { ...loadLocalConfig(), ...config, threadCount: 1 }
  localStorage.setItem(CONFIG_KEY, JSON.stringify(merged))
  return merged
}

export function getDesktopMeta(): Promise<AppMeta> {
  const api = getDesktopApi()
  if (api) return api.getMeta()
  return Promise.resolve({ version: '0.001', platform: 'web' })
}

export function loadDesktopConfig(): Promise<DesktopAppConfig> {
  const api = getDesktopApi()
  if (api) return api.loadConfig()
  return Promise.resolve(loadLocalConfig())
}

export function saveDesktopConfig(config: Partial<DesktopAppConfig>): Promise<DesktopAppConfig> {
  const api = getDesktopApi()
  if (api) return api.saveConfig(config)
  return Promise.resolve(saveLocalConfig(config))
}

export function generateDesktopWallet(): Promise<GeneratedWallet> {
  const api = getDesktopApi()
  if (!api) {
    return Promise.reject(new Error('Wallet operations require Electron runtime.'))
  }
  return api.generateWallet()
}

export function importDesktopWalletRaw(raw: string): Promise<GeneratedWallet> {
  const api = getDesktopApi()
  if (!api) {
    return Promise.reject(new Error('Wallet operations require Electron runtime.'))
  }
  return api.importWalletRaw(raw)
}

export function exportDesktopLegacyWallet(secretHex: string): Promise<string> {
  const api = getDesktopApi()
  if (!api) {
    return Promise.reject(new Error('Wallet operations require Electron runtime.'))
  }
  return api.exportLegacyWallet(secretHex)
}

export function encryptDesktopSecret(secretHex: string, passphrase: string): Promise<string> {
  const api = getDesktopApi()
  if (!api) {
    return Promise.reject(new Error('Wallet operations require Electron runtime.'))
  }
  return api.encryptSecret(secretHex, passphrase)
}

export function decryptDesktopSecret(envelopeJson: string, passphrase: string): Promise<string> {
  const api = getDesktopApi()
  if (!api) {
    return Promise.reject(new Error('Wallet operations require Electron runtime.'))
  }
  return api.decryptSecret(envelopeJson, passphrase)
}
