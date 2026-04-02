import type { AppMeta, DesktopAppConfig } from '../types/miner'

export function getDesktopMeta(): Promise<AppMeta> {
  return window.desktopApi.getMeta()
}

export function loadDesktopConfig(): Promise<DesktopAppConfig> {
  return window.desktopApi.loadConfig()
}

export function saveDesktopConfig(config: Partial<DesktopAppConfig>): Promise<DesktopAppConfig> {
  return window.desktopApi.saveConfig(config)
}
