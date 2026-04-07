<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  decryptDesktopSecret,
  encryptDesktopSecret,
  generateDesktopWallet,
  getDesktopMeta,
  importDesktopWalletRaw,
  loadDesktopConfig,
  saveDesktopLegacyWalletFile,
  selectDesktopWalletFileRaw,
  saveDesktopConfig,
} from './services/desktopApi'
import { fetchPoolAddressReward, fetchPoolStats } from './services/poolApi'
import { mineRange } from './services/hashEngine'
import { authWorker, fetchWorkerJob, fetchWorkerStats, submitWorkerShare } from './services/workerApi'
import { getDefaultPoolAddress, resolvePoolApiBase } from './services/poolAddress'
import type { AppMeta, AuthResult, DesktopAppConfig, GeneratedWallet, MiningJob, PoolAddressReward, PoolStats, ShareResult, WorkerStats } from './types/miner'

const WEBD_UNITS = 10_000
const POOL_MIN_PAYOUT_WEBD = 20

function isLegacyPoolUrl(poolUrl: string): boolean {
  return poolUrl.trim().startsWith('pool/')
}

function unitsToWebd(units: number): number {
  return units / WEBD_UNITS
}

const config = reactive<DesktopAppConfig>({
  poolUrl: getDefaultPoolAddress(),
  walletAddress: '',
  walletEncrypted: '',
  poolKey: '',
  threadCount: 1,
  autoStart: false,
  simpleMode: false,
  payoutTarget: 1,
})

const meta = ref<AppMeta>({ version: '0.0.2', platform: 'win32' })
const stats = ref<PoolStats | null>(null)
const currentWallet = ref<GeneratedWallet | null>(null)
const authResult = ref<AuthResult | null>(null)
const currentJob = ref<MiningJob | null>(null)
const workerStats = ref<WorkerStats | null>(null)
const poolAddressReward = ref<PoolAddressReward | null>(null)
const lastShareResult = ref<ShareResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const lastUpdated = ref('')
const walletPassword = ref('')
const walletUnlockPassword = ref('')
const miningRunning = ref(false)
const miningStatus = ref('Idle')
const miningHashrate = ref(0)
const miningAccepted = ref(0)
const miningRejected = ref(0)
const miningStale = ref(0)
const miningLastResult = ref('-')
const hashCounter = ref(0)
const showTechDetails = ref(false)
const lastLoggedJobKey = ref('')
const lastLoggedProtocolEntry = ref('')
const watchdogWarning = ref('')
const lastJobReceivedAt = ref(0)
let workerStatsTimer: ReturnType<typeof setInterval> | null = null
let watchdogTimer: ReturnType<typeof setInterval> | null = null
let poolRewardTimer: ReturnType<typeof setInterval> | null = null
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

const walletValueCards = computed(() => {
  const pendingSession = unitsToWebd(Number(workerStats.value?.rewardPending ?? authResult.value?.reward ?? 0))
  const confirmedSession = unitsToWebd(Number(workerStats.value?.rewardConfirmed ?? authResult.value?.confirmed ?? 0))

  // Prefer cumulative pool values when available.
  const pending = poolAddressReward.value?.rewardTotalWebd ?? pendingSession
  const confirmed = poolAddressReward.value?.rewardConfirmedWebd ?? confirmedSession
  const sent = poolAddressReward.value?.rewardSentWebd ?? 0
  const totalWallet = poolAddressReward.value?.walletBalanceWebd ?? (pending + sent)

  const fmt = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 6 })
  return {
    pending: fmt(pending),
    confirmed: fmt(confirmed),
    total: fmt(totalWallet),
  }
})

const walletTotalsRaw = computed(() => {
  const pendingSession = unitsToWebd(Number(workerStats.value?.rewardPending ?? authResult.value?.reward ?? 0))
  const confirmedSession = unitsToWebd(Number(workerStats.value?.rewardConfirmed ?? authResult.value?.confirmed ?? 0))
  const pending = poolAddressReward.value?.rewardTotalWebd ?? pendingSession
  const confirmed = poolAddressReward.value?.rewardConfirmedWebd ?? confirmedSession
  const sent = poolAddressReward.value?.rewardSentWebd ?? 0
  return {
    pending,
    confirmed,
    total: pending + sent,
  }
})

const poolPayoutCards = computed(() => {
  const fmt = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 6 })

  if (!poolAddressReward.value) {
    const fallbackPending = walletTotalsRaw.value.pending
    const fallbackConfirmed = walletTotalsRaw.value.confirmed
    const fallbackSent = Math.max(0, walletTotalsRaw.value.total - fallbackPending)

    return {
      pending: fmt(fallbackPending),
      confirmed: fmt(fallbackConfirmed),
      sent: fmt(fallbackSent),
      source: 'worker-session fallback',
    }
  }

  return {
    pending: fmt(poolAddressReward.value.rewardTotalWebd),
    confirmed: fmt(poolAddressReward.value.rewardConfirmedWebd),
    sent: fmt(poolAddressReward.value.rewardSentWebd),
    source: poolAddressReward.value.source,
  }
})

const payoutThresholdInfo = computed(() => {
  if (!poolAddressReward.value) {
    return {
      thresholdWebd: POOL_MIN_PAYOUT_WEBD,
      confirmedWebd: 0,
      remainingWebd: POOL_MIN_PAYOUT_WEBD,
      progressPercent: 0,
      statusLabel: 'Astept date payout din pool...',
    }
  }

  const confirmedWebd = poolAddressReward.value.rewardConfirmedWebd
  const remainingWebd = Math.max(0, POOL_MIN_PAYOUT_WEBD - confirmedWebd)
  const progressPercent = Math.max(0, Math.min(100, (confirmedWebd / POOL_MIN_PAYOUT_WEBD) * 100))
  const statusLabel = remainingWebd <= 0
    ? 'Prag payout atins.'
    : `Mai sunt ~${remainingWebd.toLocaleString('en-US', { maximumFractionDigits: 6 })} WEBD pana la prag.`

  return {
    thresholdWebd: POOL_MIN_PAYOUT_WEBD,
    confirmedWebd,
    remainingWebd,
    progressPercent,
    statusLabel,
  }
})

const miningHashrateDisplay = computed(() => {
  if (!miningRunning.value) return 0
  return Math.max(1, miningHashrate.value)
})

function pushLog(message: string) {
  // Avoid inserting the same message repeatedly at the top of the activity log.
  if (activityLog.value[0] === message) return
  activityLog.value = [message, ...activityLog.value].slice(0, 10)
}

function startWorkerStatsTimer() {
  stopWorkerStatsTimer()
  workerStatsTimer = setInterval(() => {
    if (miningRunning.value && authResult.value?.token) {
      void loadWorkerStats()
    }
  }, 30_000)
}

function stopWorkerStatsTimer() {
  if (workerStatsTimer) {
    clearInterval(workerStatsTimer)
    workerStatsTimer = null
  }
}

function startWatchdogTimer() {
  stopWatchdogTimer()
  watchdogTimer = setInterval(() => {
    if (!miningRunning.value) return

    if (!lastJobReceivedAt.value || Date.now() - lastJobReceivedAt.value > 45_000) {
      if (!watchdogWarning.value) {
        watchdogWarning.value = 'Nu au mai venit joburi noi in ultimele 45 secunde.'
        pushLog(watchdogWarning.value)
      }
    } else {
      watchdogWarning.value = ''
    }
  }, 10_000)
}

function stopWatchdogTimer() {
  if (watchdogTimer) {
    clearInterval(watchdogTimer)
    watchdogTimer = null
  }
}

function startPoolRewardTimer() {
  stopPoolRewardTimer()
  poolRewardTimer = setInterval(() => {
    if (!config.walletAddress.trim()) {
      poolAddressReward.value = null
      return
    }
    void refreshPoolAddressReward()
  }, 20_000)
}

function stopPoolRewardTimer() {
  if (poolRewardTimer) {
    clearInterval(poolRewardTimer)
    poolRewardTimer = null
  }
}

const walletSummary = computed(() => {
  const rawAddress = currentWallet.value?.address || config.walletAddress || '-'
  const displayAddress = rawAddress === '-' ? '-' : rawAddress.replace(/\//g, '$')

  if (!currentWallet.value) {
    return {
      address: displayAddress,
    }
  }

  return {
    address: displayAddress,
  }
})

const localConfigWalletAddress = computed({
  get: () => config.walletAddress.replace(/\//g, '$'),
  set: (value: string) => {
    config.walletAddress = value.replace(/\$/g, '/')
  },
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
    config.threadCount = 1
    if (!config.poolUrl.trim()) {
      config.poolUrl = getDefaultPoolAddress()
    }

    meta.value = appMeta
    pushLog(`Loaded local config for ${appMeta.platform} v${appMeta.version}.`)
    await refreshPoolStats()

    // Auto-connect to configured/default pool when wallet exists.
    if (config.walletAddress) {
      if (isLegacyPoolUrl(config.poolUrl) && !currentWallet.value) {
        pushLog('Legacy PoS auto-connect skipped: wallet deblocat/importat necesar inainte de auth.')
        if (!config.autoStart) {
          error.value = 'Deblocheaza wallet-ul salvat pentru a te conecta la pool.'
        }
        return
      }

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
    config.threadCount = 1
    const saved = await saveDesktopConfig({ ...config, threadCount: 1 })
    Object.assign(config, saved)
    config.threadCount = 1
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
  pushLog(`Wallet loaded from ${source}: ${wallet.address}`)
}

function getWalletForAuth(): GeneratedWallet | undefined {
  if (!currentWallet.value) return undefined

  // Send a plain object through IPC (avoid Vue proxy clone failures).
  return {
    address: currentWallet.value.address,
    secretHex: currentWallet.value.secretHex,
    publicKeyHex: currentWallet.value.publicKeyHex,
    unencodedAddressHex: currentWallet.value.unencodedAddressHex,
  }
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

async function importWalletFromFile() {
  error.value = ''
  success.value = ''

  try {
    const walletRaw = await selectDesktopWalletFileRaw()
    if (!walletRaw) {
      success.value = 'Import wallet anulat.'
      return
    }

    const wallet = await importDesktopWalletRaw(walletRaw)
    applyWallet(wallet, '.webd file')
    success.value = 'Wallet .webd importat cu succes.'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet .webd import failed.'
  }
}

async function saveWalletToWebdFile() {
  if (!currentWallet.value) {
    error.value = 'Nu exista wallet incarcat pentru export.'
    return
  }

  error.value = ''
  success.value = ''

  try {
    const savedPath = await saveDesktopLegacyWalletFile(currentWallet.value.secretHex)
    if (!savedPath) {
      success.value = 'Salvarea wallet-ului a fost anulata.'
      return
    }

    success.value = `Wallet salvat in fisier .webd: ${savedPath}`
    pushLog(`Wallet exportat in fisier .webd: ${savedPath}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Wallet .webd export failed.'
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
    
    if (config.autoStart && !miningRunning.value) {
      success.value = 'Wallet deblocat. Minatul porneste automat...'
      await runWorkerAuth()
      if (authResult.value?.token) {
        await loadWorkerJob()
        void startMiningLoop()
      } else {
        error.value = 'Auth failed. Verifica conexiunea la pool.'
      }
    } else {
      success.value = 'Wallet local decriptat cu succes.'
    }
    error.value = ''
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
    await refreshPoolAddressReward()
    lastUpdated.value = new Date().toLocaleString('ro-RO')
    pushLog(`Pool stats refreshed from ${config.poolUrl}.`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Cannot fetch pool stats.'
    pushLog(`Pool refresh failed: ${error.value}`)
  }
}

async function refreshPoolAddressReward() {
  if (!config.walletAddress) {
    poolAddressReward.value = null
    return
  }

  try {
    poolAddressReward.value = await fetchPoolAddressReward(config.poolUrl, config.walletAddress)
  } catch {
    // Keep this silent; some pool endpoints may not expose all-miners.
  }
}

async function runWorkerAuth(silent = false) {
  if (!config.walletAddress) {
    error.value = 'Seteaza sau incarca un wallet inainte de auth.'
    return
  }

  error.value = ''
  if (!silent) success.value = ''

  try {
    const walletForAuth = getWalletForAuth()
    authResult.value = await authWorker(
      config.poolUrl,
      config.walletAddress,
      config.poolKey,
      authResult.value?.workerId ?? '',
      walletForAuth,
    )
    if (!silent) success.value = `Worker auth reusit: ${authResult.value.workerId}`
    pushLog(`Worker authenticated against ${config.poolUrl}.`)

    if (authResult.value?.token) {
      await loadWorkerStats(silent)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Worker auth failed.'
    pushLog(`Worker auth failed: ${error.value}`)
  }
}

async function loadWorkerJob(silent = false) {
  if (!authResult.value?.token) {
    error.value = 'Fa auth mai intai pentru a cere job.'
    return
  }

  error.value = ''
  if (!silent) success.value = ''

  try {
    currentJob.value = await fetchWorkerJob(config.poolUrl, authResult.value.token)
    lastJobReceivedAt.value = Date.now()
    watchdogWarning.value = ''
    if (!silent) success.value = `Job primit: ${currentJob.value.jobId}`
    const nextJobKey = `${currentJob.value.jobId}:${currentJob.value.height}`
    if (lastLoggedJobKey.value !== nextJobKey) {
      pushLog(`Fetched job ${currentJob.value.jobId} at height ${currentJob.value.height}.`)
      lastLoggedJobKey.value = nextJobKey
    }

    if (!workerStats.value) {
      await loadWorkerStats(silent)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Fetch job failed.'
    pushLog(`Fetch job failed: ${error.value}`)
  }
}

async function loadWorkerStats(silent = false) {
  if (!authResult.value?.token) {
    error.value = 'Fa auth mai intai pentru a citi worker stats.'
    return
  }

  error.value = ''
  if (!silent) success.value = ''

  try {
    workerStats.value = await fetchWorkerStats(config.poolUrl, authResult.value.token)
    await refreshPoolAddressReward()
    if (!silent) success.value = 'Worker stats actualizate.'
    const latestProtocolEntry = workerStats.value.protocolEvents[0]
    if (latestProtocolEntry && latestProtocolEntry !== lastLoggedProtocolEntry.value) {
      pushLog(`Protocol: ${latestProtocolEntry}`)
      lastLoggedProtocolEntry.value = latestProtocolEntry
    }
    if (!activityLog.value[0]?.includes(`Worker stats refreshed for ${workerStats.value.workerId}.`)) {
      pushLog(`Worker stats refreshed for ${workerStats.value.workerId}.`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Fetch worker stats failed.'
    pushLog(`Worker stats failed: ${error.value}`)
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

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function ensureAuthAndJob(): Promise<boolean> {
  if (!authResult.value?.token) {
    await runWorkerAuth(true)
  }

  if (!authResult.value?.token) {
    return false
  }

  if (!currentJob.value || Date.now() > currentJob.value.expireAt) {
    await loadWorkerJob(true)
  }

  return !!currentJob.value && !!authResult.value?.token
}

async function startMiningLoop() {
  if (miningRunning.value) return
  if (!config.walletAddress) {
    error.value = 'Trebuie wallet address inainte de start mining.'
    return
  }
  if (isLegacyPoolUrl(config.poolUrl) && !currentWallet.value) {
    error.value = 'Pentru pool legacy PoS trebuie sa deblochezi sau sa importi wallet-ul inainte de Start mining.'
    return
  }

  if (isLegacyPoolUrl(config.poolUrl)) {
    // Always start with a fresh legacy auth bound to the currently unlocked wallet.
    authResult.value = null
    currentJob.value = null
  }

  miningStopRequested = false
  miningRunning.value = true
  miningStatus.value = 'Starting...'
  error.value = ''
  success.value = ''
  startHashrateMeter()
  startWorkerStatsTimer()
  startWatchdogTimer()
  pushLog('Mining loop started.')

  try {
    while (!miningStopRequested) {
      try {
        const ready = await ensureAuthAndJob()
        if (!ready) {
          miningStatus.value = 'Waiting auth/job...'
          await sleep(1500)
          continue
        }

        if (!currentJob.value || !authResult.value?.token) {
          await sleep(500)
          continue
        }

        if (currentJob.value.nonceEnd <= currentJob.value.nonceStart) {
          miningStatus.value = `Submitting PoS work ${currentJob.value.height}`

          const submit = await submitWorkerShare(
            config.poolUrl,
            authResult.value.token,
            currentJob.value.jobId,
            0,
            '',
            0,
            0,
          )

          lastShareResult.value = submit
          miningLastResult.value = submit.result

          if (submit.result === 'accepted') miningAccepted.value += 1
          else if (submit.result === 'stale') miningStale.value += 1
          else miningRejected.value += 1

          pushLog(`PoS work ${submit.result} pentru job ${currentJob.value.jobId}.`)
          await loadWorkerStats()
          currentJob.value = null
          await sleep(1200)
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
          if (currentJob.value) {
            pushLog(`No valid share found for job ${currentJob.value.jobId} in nonce range ${currentJob.value.nonceStart}-${currentJob.value.nonceEnd}.`)
          }
          currentJob.value = null
          continue
        }

        const submit = await submitWorkerShare(
          config.poolUrl,
          authResult.value.token,
          currentJob.value.jobId,
          found.nonce,
          found.hashHex,
          found.hashesTried,
          found.timeDiffMs,
        )

        lastShareResult.value = submit
        miningLastResult.value = submit.result

        if (submit.result === 'accepted') miningAccepted.value += 1
        else if (submit.result === 'stale') miningStale.value += 1
        else miningRejected.value += 1

        pushLog(`Auto share ${submit.result} (nonce ${found.nonce}).`)
        await loadWorkerStats()
        currentJob.value = null
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Mining step failed.'
        error.value = msg
        miningStatus.value = 'Recovering...'
        pushLog(`Mining transient error: ${msg}`)

        // Drop session/job and retry automatically without forcing manual restart.
        authResult.value = null
        currentJob.value = null
        await sleep(1500)
      }
    }
  } finally {
    miningRunning.value = false
    miningStatus.value = 'Stopped'
    stopHashrateMeter()
    stopWorkerStatsTimer()
    stopWatchdogTimer()
    watchdogWarning.value = ''
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
  stopWorkerStatsTimer()
  stopWatchdogTimer()
  stopPoolRewardTimer()
})

onMounted(() => {
  startPoolRewardTimer()
  void hydrate()
})

watch(
  () => `${config.poolUrl}|${config.walletAddress}`,
  () => {
    if (!config.walletAddress.trim()) {
      poolAddressReward.value = null
      return
    }
    void refreshPoolAddressReward()
  },
)
</script>

<template>
  <div class="app-shell">
    <main class="content">
      <header class="hero">
        <div>
          <h2>WEBDOLLAR Windows Miner</h2>
        </div>

        <div class="hero-actions">
          <button class="ghost-btn" @click="showTechDetails = !showTechDetails">{{ showTechDetails ? 'Ascunde detalii' : 'Detalii tehnice' }}</button>
          <button class="ghost-btn" :disabled="loading" @click="refreshPoolStats">Refresh pool</button>
          <button class="primary-btn" :disabled="saving" @click="persistConfig">{{ saving ? 'Saving...' : 'Save config' }}</button>
        </div>
      </header>

      <p v-if="error" class="banner error-banner">{{ error }}</p>
      <p v-if="success" class="banner success-banner">{{ success }}</p>
      <p v-if="watchdogWarning" class="banner error-banner">{{ watchdogWarning }}</p>

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
            <input v-model="localConfigWalletAddress" class="field-input" type="text" placeholder="WEBD$..." />
          </label>

          <label class="toggle-field">
            <input v-model="config.autoStart" type="checkbox" />
            <span>Auto-start desktop miner</span>
          </label>
        </article>

      </section>

      <section class="layout-grid wallet-grid">
        <article class="panel form-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Wallet compatibility</p>
              <h3>Legacy .webd operations</h3>
            </div>
          </div>

          <div class="hero-actions wallet-actions">
            <button class="primary-btn" @click="generateWallet">Generate wallet</button>
            <button class="ghost-btn" @click="importWalletFromFile">Import .webd file</button>
            <button class="ghost-btn" :disabled="!currentWallet" @click="saveWalletToWebdFile">Save .webd file</button>
          </div>

          <div class="wallet-summary-grid">
            <div>
              <p class="metric-label">Wallet address</p>
              <p class="metric-value small-value">{{ walletSummary.address }}</p>
            </div>
            <div>
              <p class="metric-label">Wallet total portofel (balance pool)</p>
              <p class="metric-value small-value">{{ walletValueCards.total }} WEBD</p>
            </div>
          </div>
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
              <p class="eyebrow">Mining controls</p>
              <h3>Start and stop mining</h3>
            </div>
            <p class="panel-meta">Autentificarea si job-urile sunt gestionate automat la start.</p>
          </div>

          <div class="hero-actions wallet-actions">
            <button class="primary-btn" :disabled="miningRunning" @click="startMiningLoop">Start mining</button>
            <button class="ghost-btn" :disabled="!miningRunning" @click="stopMiningLoop">Stop mining</button>
          </div>

          <div class="wallet-summary-grid">
            <div>
              <p class="metric-label">Mining status</p>
              <p class="metric-value small-value">{{ miningStatus }}</p>
            </div>
            <div>
              <p class="metric-label">Hashrate</p>
              <p class="metric-value small-value">{{ miningHashrateDisplay }} H/s</p>
            </div>
          </div>

          <template v-if="showTechDetails">
            <div class="wallet-summary-grid">
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
          </template>
        </article>

      </section>
    </main>
  </div>
</template>
