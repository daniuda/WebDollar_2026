import { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage } from 'electron'
import type { IpcMainInvokeEvent } from 'electron'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { decryptSecret, encryptSecret, exportLegacyWallet, generateWallet, importWalletRaw } from './wallet.js'
import { LegacyPoolBridge } from './legacyPool.js'

const isDev = !app.isPackaged
const appVersion = app.getVersion()
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false
const legacyPool = new LegacyPoolBridge()
const defaultConfig = {
  poolUrl: 'pool/1/1/1/SpyClub/0.0001/374d24d549e73f05280b239d96d7c6b28f15aabb5d41e89818b660a9ebc3276e/https:$$node.spyclub.ro:8080',
  walletAddress: '',
  walletEncrypted: '',
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
      // main.js and preload.js are emitted side-by-side in dist-electron.
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    const devUrl = 'http://localhost:5173'
    let retries = 0

    const tryLoad = () => {
      void win.loadURL(devUrl)
    }

    win.webContents.on('did-fail-load', (_event, errorCode, _errorDesc, validatedUrl) => {
      // Retry only for the dev server URL while Vite is still booting.
      if (validatedUrl.startsWith(devUrl) && errorCode === -102 && retries < 25) {
        retries += 1
        setTimeout(tryLoad, 300)
      }
    })

    tryLoad()
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    void win.loadFile(join(__dirname, '..', 'dist', 'index.html'))
  }

  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      win.hide()
    }
  })

  win.on('closed', () => {
    mainWindow = null
  })

  mainWindow = win
}

function createTray() {
  if (tray) return

  try {
    const iconPath = join(app.getAppPath(), 'build', 'tray.png')
    const image = nativeImage.createFromPath(iconPath)

    if (image.isEmpty()) {
      // Don't crash if tray icon is missing in dev.
      return
    }

    tray = new Tray(image)
  } catch {
    // Don't crash if tray creation fails in dev environments.
    return
  }

  tray.setToolTip('WebDollar Windows Miner')

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open',
      click: () => {
        if (!mainWindow) {
          createWindow()
          return
        }

        mainWindow.show()
        mainWindow.focus()
      },
    },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true
        app.quit()
      },
    },
  ])

  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => {
    if (!mainWindow) {
      createWindow()
      return
    }

    mainWindow.show()
    mainWindow.focus()
  })
}

app.whenReady().then(() => {
  ipcMain.handle('app:get-meta', () => ({
    version: appVersion,
    platform: process.platform,
  }))

  ipcMain.handle('wallet:generate', () => generateWallet())
  ipcMain.handle('wallet:import-raw', async (_event: IpcMainInvokeEvent, raw: string) => importWalletRaw(raw))
  ipcMain.handle('wallet:export-legacy', async (_event: IpcMainInvokeEvent, secretHex: string) => exportLegacyWallet(secretHex))
  ipcMain.handle('wallet:encrypt-secret', async (_event: IpcMainInvokeEvent, secretHex: string, passphrase: string) => encryptSecret(secretHex, passphrase))
  ipcMain.handle('wallet:decrypt-secret', async (_event: IpcMainInvokeEvent, envelopeJson: string, passphrase: string) => decryptSecret(envelopeJson, passphrase))

  ipcMain.handle('legacy:connect', async (_event: IpcMainInvokeEvent, poolAddress: string, walletAddress: string) => {
    return legacyPool.connect(poolAddress, walletAddress)
  })
  ipcMain.handle('legacy:get-job', async (_event: IpcMainInvokeEvent, token: string) => legacyPool.getJob(token))
  ipcMain.handle('legacy:submit-share', async (_event: IpcMainInvokeEvent, token: string, jobId: string, nonce: number, hashHex: string) => {
    return legacyPool.submitShare(token, jobId, nonce, hashHex)
  })
  ipcMain.handle('legacy:get-worker-stats', async (_event: IpcMainInvokeEvent, token: string) => legacyPool.getWorkerStats(token))
  ipcMain.handle('legacy:get-pool-stats', async () => legacyPool.getPoolStats())

  ipcMain.handle('config:load', async () => loadConfig())
  ipcMain.handle('config:save', async (_event: IpcMainInvokeEvent, config: Partial<AppConfig>) => saveConfig(config))

  createWindow()
  createTray()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  // Keep app alive in tray until explicit Quit.
})

app.on('before-quit', () => {
  isQuitting = true
})
