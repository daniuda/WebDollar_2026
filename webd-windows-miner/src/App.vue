<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  decryptDesktopSecret,
  encryptDesktopSecret,
  exportDesktopLegacyWallet,
  generateDesktopWallet,
  getDesktopMeta,
  importDesktopWalletRaw,
  loadDesktopConfig,
  saveDesktopConfig,
} from './services/desktopApi'
import { fetchPoolStats } from './services/poolApi'
import { mineRange } from './services/hashEngine'
import { authWorker, fetchWorkerJob, fetchWorkerStats, submitWorkerShare } from './services/workerApi'
import { getDefaultPoolAddress, resolvePoolApiBase } from './services/poolAddress'
import type { AppMeta, AuthResult, DesktopAppConfig, GeneratedWallet, MiningJob, PoolStats, ShareResult, WorkerStats } from './types/miner'

const config = reactive<DesktopAppConfig>({
  poolUrl: getDefaultPoolAddress(),
  walletAddress: '',
  walletEncrypted: '',
  poolKey: '',
  threadCount: 1,
  autoStart: false,
})

const meta = ref<AppMeta>({ version: '0.001', platform: 'win32' })
const stats = ref<PoolStats | null>(null)
const currentWallet = ref<GeneratedWallet | null>(null)
const authResult = ref<AuthResult | null>(null)
const currentJob = ref<MiningJob | null>(null)
const workerStats = ref<WorkerStats | null>(null)
const lastShareResult = ref<ShareResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const lastUpdated = ref('')
const walletImportInput = ref('')
const walletExportOutput = ref('')
const walletPassword = ref('')
const walletUnlockPassword = ref('')
const manualNonce = ref('0')
const manualHash = ref('')
const miningRunning = ref(false)
const miningStatus = ref('Idle')
const miningHashrate = ref(0)
const miningAccepted = ref(0)
const miningRejected = ref(0)
const miningStale = ref(0)
const miningLastResult = ref('-')
const hashCounter = ref(0)
let miningStopRequested = false
let hashrateTimer: ReturnType<typeof setInterval> | null = null
const activityLog = ref<string[]>([
  'Bootstrap Windows miner: config persistence ready.',
  'Pool stats fetch will validate backend connectivity.',
])

const summaryCards = computed<Array<{ label: string; value: string }>>(() => {
  if (!stats.value) {
    return [
      { label: 'Pool', value: 'n/a' },
      { label: 'Height', value: '-' },
      { label: 'Workers online', value: '-' },
      { label: 'Total shares', value: '-' },
    ]
  }

  return [
    { label: 'Pool', value: stats.value.poolName },
    { label: 'Height', value: stats.value.height.toLocaleString('en-US') },
    { label: 'Workers online', value: `${stats.value.workersOnline} / ${stats.value.workersTotal}` },
    { label: 'Total shares', value: stats.value.totalShares.toLocaleString('en-US') },
  ]
})

function pushLog(message: string) {
  activityLog.value = [message, ...activityLog.value].slice(0, 10)
}

const walletSummary = computed(() => {
  if (!currentWallet.value) {
    return {
      address: config.walletAddress || '-',
      publicKey: '-',
      secret: config.walletEncrypted ? 'Encrypted locally' : '-',
    }
  }

  return {
    address: currentWallet.value.address,
    publicKey: currentWallet.value.publicKeyHex,
    secret: `${currentWallet.value.secretHex.slice(0, 16)}...`,
  }
})

async function hydrate() {
  loading.value = true
  error.value = ''

  try {
    const [savedConfig, appMeta] = await Promise.all([
      loadDesktopConfig(),
      getDesktopMeta(),
    ])

    Object.assign(config, savedConfig)
    if (!config.poolUrl.trim()) {
      config.poolUrl = getDefaultPoolAddress()
    }

    meta.value = appMeta
    pushLog(`Loaded local config for ${appMeta.platform} v${appMeta.version}.`)
    await refreshPoolStats()

    // Auto-connect to configured/default pool when wallet exists.
    if (config.walletAddress) {
      pushLog(`Auto-connect to pool: ${resolvePoolApiBase(config.poolUrl)}`)
      await runWorkerAuth()
      if (authResult.value?.token) {
        await loadWorkerJob()
        await loadWorkerStats()
        if (config.autoStart && !miningRunning.value) {
          void startMiningLoop()
        }
      }
    } else {
      pushLog('Auto-connect skipped: wallet address is empty.')
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Cannot load desktop state.'
    pushLog(`Hydration failed: ${error.value}`)
  } finally {
    loading.value = false
  }
}

async function persistConfig() {
  saving.value = true
  error.value = ''
  success.value = ''

  try {
    const saved = await saveDesktopConfig({ ...config })
    Object.assign(config, saved)
    success.value = 'Config saved locally.'
    pushLog(`Saved config for pool ${saved.poolUrl}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Cannot save config.'
    pushLog(`Save failed: ${error.value}`)
  } finally {
    saving.value = false
  }
}

function applyWallet(wallet: GeneratedWallet, source: string) {
  currentWallet.value = wallet
  config.walletAddress = wallet.address
  walletExportOutput.value = ''
  pushLog(`Wallet loaded from ${source}: ${wallet.address}`)
}

async function generateWallet() {
  error.value = ''
  success.value = ''

  try {
    const wallet = await generateDesktopWallet()
    applyWallet(wallet, 'generator')
    success.value = 'Wallet nou generat.'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet generation failed.'
  }
}

async function importWallet() {
  error.value = ''
  success.value = ''

  try {
    const wallet = await importDesktopWalletRaw(walletImportInput.value)
    applyWallet(wallet, 'import')
    success.value = 'Wallet importat cu succes.'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet import failed.'
  }
}

async function exportWallet() {
  if (!currentWallet.value) {
    error.value = 'Nu exista wallet incarcat pentru export.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    walletExportOutput.value = await exportDesktopLegacyWallet(currentWallet.value.secretHex)
    success.value = 'Export .webd pregatit.'
    pushLog('Generated legacy .webd export preview.')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet export failed.'
  }
}

async function encryptWallet() {
  if (!currentWallet.value) {
    error.value = 'Nu exista wallet incarcat pentru criptare.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    const envelope = await encryptDesktopSecret(currentWallet.value.secretHex, walletPassword.value)
    const saved = await saveDesktopConfig({
      walletAddress: currentWallet.value.address,
      walletEncrypted: envelope,
    })
    Object.assign(config, saved)
    walletPassword.value = ''
    success.value = 'Wallet criptat si salvat local.'
    pushLog('Encrypted local wallet saved into desktop config.')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet encryption failed.'
  }
}

async function unlockWallet() {
  if (!config.walletEncrypted) {
    error.value = 'Nu exista wallet criptat local.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    const secretHex = await decryptDesktopSecret(config.walletEncrypted, walletUnlockPassword.value)
    const wallet = await importDesktopWalletRaw(secretHex)
    applyWallet(wallet, 'encrypted local storage')
    walletUnlockPassword.value = ''
    success.value = 'Wallet local decriptat cu succes.'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet unlock failed.'
  }
}

async function refreshPoolStats() {
  error.value = ''
  success.value = ''

  try {
    const nextStats = await fetchPoolStats(config.poolUrl)
    stats.value = nextStats
    lastUpdated.value = new Date().toLocaleString('ro-RO')
    pushLog(`Pool stats refreshed from ${config.poolUrl}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Cannot fetch pool stats.'
    pushLog(`Pool refresh failed: ${error.value}`)
  }
}

async function runWorkerAuth() {
  if (!config.walletAddress) {
    error.value = 'Seteaza sau incarca un wallet inainte de auth.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    authResult.value = await authWorker(config.poolUrl, config.walletAddress, config.poolKey, authResult.value?.workerId ?? '')
    success.value = `Worker auth reusit: ${authResult.value.workerId}`
    pushLog(`Worker authenticated against ${config.poolUrl}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Worker auth failed.'
    pushLog(`Worker auth failed: ${error.value}`)
  }
}

async function loadWorkerJob() {
  if (!authResult.value?.token) {
    error.value = 'Fa auth mai intai pentru a cere job.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    currentJob.value = await fetchWorkerJob(config.poolUrl, authResult.value.token)
    manualNonce.value = String(currentJob.value.nonceStart)
    success.value = `Job primit: ${currentJob.value.jobId}`
    pushLog(`Fetched job ${currentJob.value.jobId} at height ${currentJob.value.height}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Fetch job failed.'
    pushLog(`Fetch job failed: ${error.value}`)
  }
}

async function loadWorkerStats() {
  if (!authResult.value?.token) {
    error.value = 'Fa auth mai intai pentru a citi worker stats.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    workerStats.value = await fetchWorkerStats(config.poolUrl, authResult.value.token)
    success.value = 'Worker stats actualizate.'
    pushLog(`Worker stats refreshed for ${workerStats.value.workerId}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Fetch worker stats failed.'
    pushLog(`Worker stats failed: ${error.value}`)
  }
}

async function submitShare() {
  if (!authResult.value?.token || !currentJob.value?.jobId) {
    error.value = 'Ai nevoie de auth si job activ inainte de submit.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    lastShareResult.value = await submitWorkerShare(
      config.poolUrl,
      authResult.value.token,
      currentJob.value.jobId,
      Number(manualNonce.value),
      manualHash.value,
    )
    success.value = `Share submit: ${lastShareResult.value.result}`
    pushLog(`Manual share submit returned ${lastShareResult.value.result}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Share submit failed.'
    pushLog(`Share submit failed: ${error.value}`)
  }
}

function startHashrateMeter() {
  stopHashrateMeter()
  hashrateTimer = setInterval(() => {
    miningHashrate.value = hashCounter.value
    hashCounter.value = 0
  }, 1000)
}

function stopHashrateMeter() {
  if (hashrateTimer) {
    clearInterval(hashrateTimer)
    hashrateTimer = null
  }
}

async function ensureAuthAndJob(): Promise<boolean> {
  if (!authResult.value?.token) {
    await runWorkerAuth()
  }

  if (!authResult.value?.token) {
    return false
  }

  if (!currentJob.value || Date.now() > currentJob.value.expireAt) {
    await loadWorkerJob()
  }

  return !!currentJob.value && !!authResult.value?.token
}

async function startMiningLoop() {
  if (miningRunning.value) return
  if (!config.walletAddress) {
    error.value = 'Trebuie wallet address inainte de start mining.'
    return
  }

  miningStopRequested = false
  miningRunning.value = true
  miningStatus.value = 'Starting...'
  error.value = ''
  success.value = ''
  startHashrateMeter()
  pushLog('Mining loop started.')

  try {
    while (!miningStopRequested) {
      const ready = await ensureAuthAndJob()
      if (!ready) {
        miningStatus.value = 'Waiting auth/job...'
        await new Promise((resolve) => setTimeout(resolve, 1500))
        continue
      }

      if (!currentJob.value || !authResult.value?.token) {
        await new Promise((resolve) => setTimeout(resolve, 500))
        continue
      }

      miningStatus.value = `Mining height ${currentJob.value.height}`
      const found = await mineRange(
        currentJob.value,
        () => { hashCounter.value += 1 },
        () => miningStopRequested,
      )

      if (miningStopRequested) break

      if (!found) {
        currentJob.value = null
        continue
      }

      const submit = await submitWorkerShare(
        config.poolUrl,
        authResult.value.token,
        currentJob.value.jobId,
        found.nonce,
        found.hashHex,
      )

      lastShareResult.value = submit
      miningLastResult.value = submit.result

      if (submit.result === 'accepted') miningAccepted.value += 1
      else if (submit.result === 'stale') miningStale.value += 1
      else miningRejected.value += 1

      pushLog(`Auto share ${submit.result} (nonce ${found.nonce}).`)
      await loadWorkerStats()
      currentJob.value = null
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Mining loop failed.'
    error.value = msg
    miningStatus.value = 'Error'
    pushLog(`Mining error: ${msg}`)
  } finally {
    miningRunning.value = false
    miningStatus.value = 'Stopped'
    stopHashrateMeter()
    miningHashrate.value = 0
    hashCounter.value = 0
  }
}

function stopMiningLoop() {
  miningStopRequested = true
  miningStatus.value = 'Stopping...'
  pushLog('Stop requested for mining loop.')
}

onBeforeUnmount(() => {
  stopMiningLoop()
  stopHashrateMeter()
})

onMounted(() => {
  void hydrate()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-block">
        <p class="eyebrow">Desktop prototype</p>
        <h1>WebDollar Windows Miner</h1>
        <p class="sidebar-copy">
          Primul MVP desktop pentru validarea flow-ului wallet, pool si mining inainte de revenirea pe Android.
        </p>
      </div>

      <div class="sidebar-panel">
        <p class="panel-label">Runtime</p>
        <p class="panel-value">{{ meta.platform }}</p>
        <p class="panel-meta">Version {{ meta.version }}</p>
      </div>

      <div class="sidebar-panel">
        <p class="panel-label">Status MVP</p>
        <ul class="status-list">
          <li>Electron shell</li>
          <li>Config persistence</li>
          <li>Pool stats connectivity</li>
        </ul>
      </div>
    </aside>

    <main class="content">
      <header class="hero">
        <div>
          <p class="eyebrow">Phase 1 running</p>
          <h2>Desktop control surface</h2>
          <p class="hero-copy">
            Baza de lucru este pornibila si pregatita pentru urmatorul pas: auth, job fetch, share submit si mining loop.
          </p>
        </div>

        <div class="hero-actions">
          <button class="ghost-btn" :disabled="loading" @click="refreshPoolStats">Refresh pool</button>
          <button class="primary-btn" :disabled="saving" @click="persistConfig">{{ saving ? 'Saving...' : 'Save config' }}</button>
        </div>
      </header>

      <p v-if="error" class="banner error-banner">{{ error }}</p>
      <p v-if="success" class="banner success-banner">{{ success }}</p>

      <section class="metrics-grid">
        <article v-for="card in summaryCards" :key="card.label" class="metric-card">
          <p class="metric-label">{{ card.label }}</p>
          <p class="metric-value">{{ card.value }}</p>
        </article>
      </section>

      <section class="layout-grid">
        <article class="panel form-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Local config</p>
              <h3>Pool and worker setup</h3>
            </div>
            <p class="panel-meta">Stored under Electron userData.</p>
          </div>

          <label class="field">
            <span>Pool API URL</span>
            <input v-model="config.poolUrl" class="field-input" type="text" placeholder="pool/1/1/1/.../https:$$host:port" />
          </label>

          <label class="field">
            <span>Wallet address</span>
            <input v-model="config.walletAddress" class="field-input" type="text" placeholder="WEBD$..." />
          </label>

          <label class="field">
            <span>Pool key</span>
            <input v-model="config.poolKey" class="field-input" type="text" placeholder="Optional" />
          </label>

          <div class="field-row">
            <label class="field compact-field">
              <span>Threads</span>
              <input v-model.number="config.threadCount" class="field-input" type="number" min="1" max="64" />
            </label>

            <label class="toggle-field">
              <input v-model="config.autoStart" type="checkbox" />
              <span>Auto-start desktop miner</span>
            </label>
          </div>
        </article>

        <article class="panel diagnostics-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Diagnostics</p>
              <h3>Pool visibility</h3>
            </div>
            <p class="panel-meta">Last refresh: {{ lastUpdated || '-' }}</p>
          </div>

          <div class="diagnostics-grid">
            <div>
              <p class="metric-label">Key required</p>
              <p class="metric-value small-value">{{ stats?.keyRequired ? 'Yes' : 'No' }}</p>
            </div>
            <div>
              <p class="metric-label">Worker API</p>
              <p class="metric-value small-value">{{ config.poolUrl }}</p>
            </div>
          </div>

          <div class="timeline">
            <p class="metric-label">Activity log</p>
            <ul class="timeline-list">
              <li v-for="entry in activityLog" :key="entry">{{ entry }}</li>
            </ul>
          </div>
        </article>
      </section>

      <section class="layout-grid wallet-grid">
        <article class="panel form-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Wallet compatibility</p>
              <h3>Legacy .webd operations</h3>
            </div>
            <p class="panel-meta">Android-compatible format bridge.</p>
          </div>

          <div class="hero-actions wallet-actions">
            <button class="primary-btn" @click="generateWallet">Generate wallet</button>
            <button class="ghost-btn" @click="importWallet">Import raw</button>
            <button class="ghost-btn" @click="exportWallet">Export .webd</button>
          </div>

          <label class="field">
            <span>Import source (.webd JSON / 64 hex / 138 hex / WIF)</span>
            <textarea v-model="walletImportInput" class="field-input field-textarea" rows="7" placeholder='{"version":"0.1",...}' />
          </label>

          <div class="wallet-summary-grid">
            <div>
              <p class="metric-label">Address</p>
              <p class="metric-value small-value">{{ walletSummary.address }}</p>
            </div>
            <div>
              <p class="metric-label">Public key</p>
              <p class="metric-value small-value">{{ walletSummary.publicKey }}</p>
            </div>
            <div>
              <p class="metric-label">Secret status</p>
              <p class="metric-value small-value">{{ walletSummary.secret }}</p>
            </div>
          </div>

          <label class="field">
            <span>Legacy .webd export preview</span>
            <textarea v-model="walletExportOutput" class="field-input field-textarea" rows="8" readonly placeholder="Exportul .webd va aparea aici" />
          </label>
        </article>

        <article class="panel diagnostics-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Encrypted storage</p>
              <h3>Local wallet vault</h3>
            </div>
            <p class="panel-meta">AES-GCM + PBKDF2, compatibil cu flow-ul Android.</p>
          </div>

          <label class="field">
            <span>Password for local encryption</span>
            <input v-model="walletPassword" class="field-input" type="password" placeholder="Minimum 8 characters" />
          </label>

          <button class="primary-btn full-btn" @click="encryptWallet">Encrypt and save locally</button>

          <div class="diagnostics-grid encrypted-grid">
            <div>
              <p class="metric-label">Encrypted wallet saved</p>
              <p class="metric-value small-value">{{ config.walletEncrypted ? 'Yes' : 'No' }}</p>
            </div>
            <div>
              <p class="metric-label">Saved address</p>
              <p class="metric-value small-value">{{ config.walletAddress || '-' }}</p>
            </div>
          </div>

          <label class="field">
            <span>Password for unlock</span>
            <input v-model="walletUnlockPassword" class="field-input" type="password" placeholder="Unlock local wallet" />
          </label>

          <button class="ghost-btn full-btn" @click="unlockWallet">Unlock saved wallet</button>
        </article>
      </section>

      <section class="layout-grid worker-grid">
        <article class="panel form-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Worker protocol</p>
              <h3>Auth, job and share flow</h3>
            </div>
            <p class="panel-meta">HTTP worker API validation before mining automation.</p>
          </div>

          <div class="hero-actions wallet-actions">
            <button class="primary-btn" @click="runWorkerAuth">Auth worker</button>
            <button class="ghost-btn" @click="loadWorkerJob">Get job</button>
            <button class="ghost-btn" @click="loadWorkerStats">Worker stats</button>
          </div>

          <div class="hero-actions wallet-actions">
            <button class="primary-btn" :disabled="miningRunning" @click="startMiningLoop">Start auto mining</button>
            <button class="ghost-btn" :disabled="!miningRunning" @click="stopMiningLoop">Stop mining</button>
          </div>

          <div class="wallet-summary-grid">
            <div>
              <p class="metric-label">Mining status</p>
              <p class="metric-value small-value">{{ miningStatus }}</p>
            </div>
            <div>
              <p class="metric-label">Hashrate</p>
              <p class="metric-value small-value">{{ miningHashrate }} H/s</p>
            </div>
            <div>
              <p class="metric-label">Last result</p>
              <p class="metric-value small-value">{{ miningLastResult }}</p>
            </div>
            <div>
              <p class="metric-label">Accepted</p>
              <p class="metric-value small-value">{{ miningAccepted }}</p>
            </div>
            <div>
              <p class="metric-label">Rejected</p>
              <p class="metric-value small-value">{{ miningRejected }}</p>
            </div>
            <div>
              <p class="metric-label">Stale</p>
              <p class="metric-value small-value">{{ miningStale }}</p>
            </div>
          </div>

          <div class="wallet-summary-grid">
            <div>
              <p class="metric-label">Token</p>
              <p class="metric-value small-value">{{ authResult?.token || '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Worker ID</p>
              <p class="metric-value small-value">{{ authResult?.workerId || '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Pool name</p>
              <p class="metric-value small-value">{{ authResult?.poolName || '-' }}</p>
            </div>
          </div>

          <div class="wallet-summary-grid">
            <div>
              <p class="metric-label">Current job</p>
              <p class="metric-value small-value">{{ currentJob?.jobId || '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Height</p>
              <p class="metric-value small-value">{{ currentJob?.height ?? '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Nonce range</p>
              <p class="metric-value small-value">{{ currentJob ? `${currentJob.nonceStart} - ${currentJob.nonceEnd}` : '-' }}</p>
            </div>
          </div>
        </article>

        <article class="panel diagnostics-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Manual submit</p>
              <h3>Share diagnostics</h3>
            </div>
            <p class="panel-meta">For endpoint validation before auto-mining.</p>
          </div>

          <label class="field">
            <span>Nonce</span>
            <input v-model="manualNonce" class="field-input" type="number" min="0" />
          </label>

          <label class="field">
            <span>Hash</span>
            <input v-model="manualHash" class="field-input" type="text" placeholder="hex share hash" />
          </label>

          <button class="primary-btn full-btn" @click="submitShare">Submit share</button>

          <div class="diagnostics-grid encrypted-grid">
            <div>
              <p class="metric-label">Last submit result</p>
              <p class="metric-value small-value">{{ lastShareResult?.result || '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Last submit message</p>
              <p class="metric-value small-value">{{ lastShareResult?.message || '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Worker accepted</p>
              <p class="metric-value small-value">{{ workerStats?.sharesAccepted ?? '-' }}</p>
            </div>
            <div>
              <p class="metric-label">Worker rejected/stale</p>
              <p class="metric-value small-value">{{ workerStats ? `${workerStats.sharesRejected} / ${workerStats.sharesStale}` : '-' }}</p>
            </div>
          </div>
        </article>
      </section>
    </main>
  </div>
</template>
