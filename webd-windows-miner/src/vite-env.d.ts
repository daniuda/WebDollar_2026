/// <reference types="vite/client" />

interface DesktopAppConfig {
  poolUrl: string
  walletAddress: string
  poolKey: string
  threadCount: number
  autoStart: boolean
}

interface Window {
  desktopApi: {
    getMeta: () => Promise<{ version: string; platform: string }>
    loadConfig: () => Promise<DesktopAppConfig>
    saveConfig: (config: Partial<DesktopAppConfig>) => Promise<DesktopAppConfig>
  }
}
