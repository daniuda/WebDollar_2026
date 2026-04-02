import { contextBridge, ipcRenderer } from 'electron'

type AppConfig = {
  poolUrl: string
  walletAddress: string
  poolKey: string
  threadCount: number
  autoStart: boolean
}

contextBridge.exposeInMainWorld('desktopApi', {
  getMeta: () => ipcRenderer.invoke('app:get-meta') as Promise<{ version: string; platform: string }>,
  loadConfig: () => ipcRenderer.invoke('config:load') as Promise<AppConfig>,
  saveConfig: (config: Partial<AppConfig>) => ipcRenderer.invoke('config:save', config) as Promise<AppConfig>,
})
