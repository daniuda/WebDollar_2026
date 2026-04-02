import { app, BrowserWindow, ipcMain } from 'electron'
import type { IpcMainInvokeEvent } from 'electron'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const isDev = !app.isPackaged
const appVersion = app.getVersion()
const defaultConfig = {
  poolUrl: 'http://127.0.0.1:3001',
  walletAddress: '',
  poolKey: '',
  threadCount: 1,
  autoStart: false,
}

type AppConfig = typeof defaultConfig

async function getConfigPath() {
  const dir = app.getPath('userData')
  await mkdir(dir, { recursive: true })
  return join(dir, 'miner-config.json')
}

async function loadConfig(): Promise<AppConfig> {
  const configPath = await getConfigPath()

  try {
    const raw = await readFile(configPath, 'utf8')
    const parsed = JSON.parse(raw) as Partial<AppConfig>
    return { ...defaultConfig, ...parsed }
  } catch {
    return { ...defaultConfig }
  }
}

async function saveConfig(config: Partial<AppConfig>): Promise<AppConfig> {
  const nextConfig = { ...(await loadConfig()), ...config }
  const configPath = await getConfigPath()
  await writeFile(configPath, JSON.stringify(nextConfig, null, 2), 'utf8')
  return nextConfig
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: '#061019',
    title: 'WebDollar Windows Miner',
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    void win.loadURL('http://127.0.0.1:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    void win.loadFile(join(__dirname, '../dist/index.html'))
  }
}

app.whenReady().then(() => {
  ipcMain.handle('app:get-meta', () => ({
    version: appVersion,
    platform: process.platform,
  }))

  ipcMain.handle('config:load', async () => loadConfig())
  ipcMain.handle('config:save', async (_event: IpcMainInvokeEvent, config: Partial<AppConfig>) => saveConfig(config))

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
