<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
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
import type { AppMeta, DesktopAppConfig, GeneratedWallet, PoolStats } from './types/miner'

const config = reactive<DesktopAppConfig>({
  poolUrl: 'http://127.0.0.1:3001',
  walletAddress: '',
  walletEncrypted: '',
  poolKey: '',
  threadCount: 1,
  autoStart: false,
})

const meta = ref<AppMeta>({ version: '0.001', platform: 'win32' })
const stats = ref<PoolStats | null>(null)
const currentWallet = ref<GeneratedWallet | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const lastUpdated = ref('')
const walletImportInput = ref('')
const walletExportOutput = ref('')
const walletPassword = ref('')
const walletUnlockPassword = ref('')
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
    meta.value = appMeta
    pushLog(`Loaded local config for ${appMeta.platform} v${appMeta.version}.`)
    await refreshPoolStats()
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
            <input v-model="config.poolUrl" class="field-input" type="text" placeholder="http://127.0.0.1:3001" />
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
    </main>
  </div>
</template>
