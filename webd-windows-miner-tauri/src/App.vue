<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { open } from '@tauri-apps/plugin-dialog'

type Lang = 'ro' | 'en'

const translations: Record<Lang, Record<string, string>> = {
  ro: {
    title: 'WebDollar Miner',
    walletLabel: 'Portofel (.webd)',
    browse: 'Răsfoiește…',
    passwordLabel: 'Parolă portofel (doar dacă e criptat — lasă gol altfel)',
    poolUrlLabel: 'Pool — URL',
    poolKeyLabel: 'Pool — cheie publică',
    start: 'Start minerit',
    stop: 'Stop',
    connected: 'Conectat',
    disconnected: 'Deconectat',
    height: 'Înălțime',
    heartbeats: 'Heartbeats',
    realMatches: 'Potriviri reale',
    reward: 'Reward',
    confirmed: 'Confirmed',
    walletFilter: 'Portofel WebDollar',
    errStart: 'nu am putut porni minerul',
    errStop: 'nu am putut opri minerul',
    processExited: 'proces terminat, cod',
    unknown: 'necunoscut',
  },
  en: {
    title: 'WebDollar Miner',
    walletLabel: 'Wallet (.webd)',
    browse: 'Browse…',
    passwordLabel: 'Wallet password (only if encrypted — leave empty otherwise)',
    poolUrlLabel: 'Pool — URL',
    poolKeyLabel: 'Pool — public key',
    start: 'Start mining',
    stop: 'Stop',
    connected: 'Connected',
    disconnected: 'Disconnected',
    height: 'Height',
    heartbeats: 'Heartbeats',
    realMatches: 'Real matches',
    reward: 'Reward',
    confirmed: 'Confirmed',
    walletFilter: 'WebDollar wallet',
    errStart: 'could not start the miner',
    errStop: 'could not stop the miner',
    processExited: 'process exited, code',
    unknown: 'unknown',
  },
}

const lang = ref<Lang>((localStorage.getItem('webd-miner-lang') as Lang) || 'ro')
function t(key: string) {
  return translations[lang.value][key] ?? key
}
function toggleLang() {
  lang.value = lang.value === 'ro' ? 'en' : 'ro'
  localStorage.setItem('webd-miner-lang', lang.value)
}

// pool predefinit — utilizatorul poate schimba, dar vine cu o valoare funcțională din start
const walletPath = ref('')
const poolUrl = ref('https://webdollar.run.place:443')
const poolPublicKeyHex = ref('3390ea93332ffb0e8c3ad00b043c9e3b6214394d9abd395bb5747094d739889e')
const password = ref('')

const running = ref(false)
const logLines = ref<string[]>([])
const logEl = ref<HTMLElement | null>(null)

const status = ref({
  connected: false,
  height: 0,
  heartbeats: 0,
  realMatches: 0,
  reward: 0,
  confirmed: 0,
})

let unlistenLog: UnlistenFn | null = null
let unlistenExit: UnlistenFn | null = null

const canStart = computed(() => walletPath.value.trim() !== '' && poolUrl.value.trim() !== '' && poolPublicKeyHex.value.trim() !== '' && !running.value)

async function pickWallet() {
  const selected = await open({
    multiple: false,
    filters: [{ name: t('walletFilter'), extensions: ['webd'] }],
  })
  if (typeof selected === 'string') walletPath.value = selected
}

function pushLog(line: string) {
  logLines.value.push(line)
  if (logLines.value.length > 500) logLines.value.splice(0, logLines.value.length - 500)
  parseStatusLine(line)
  requestAnimationFrame(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

// liniile [status] produse de webd-miner-cli.js au un format fix — le parsăm
// ca să afișăm valorile ca indicatori vizuali, nu doar text brut în log.
function parseStatusLine(line: string) {
  if (!line.startsWith('[status]')) return
  const get = (key: string) => {
    const m = line.match(new RegExp(key + '=([^\\s]+)'))
    return m ? m[1] : undefined
  }
  const conectat = get('conectat')
  const inaltime = get('înălțime')
  const heartbeats = get('heartbeats')
  const potriviri = get('potriviri_reale')
  const reward = get('reward')
  const confirmed = get('confirmed')

  if (conectat !== undefined) status.value.connected = conectat === 'true'
  if (inaltime !== undefined) status.value.height = Number(inaltime) || 0
  if (heartbeats !== undefined) status.value.heartbeats = Number(heartbeats) || 0
  if (potriviri !== undefined) status.value.realMatches = Number(potriviri) || 0
  if (reward !== undefined) status.value.reward = Number(reward) || 0
  if (confirmed !== undefined) status.value.confirmed = Number(confirmed) || 0
}

async function startMining() {
  logLines.value = []
  status.value = { connected: false, height: 0, heartbeats: 0, realMatches: 0, reward: 0, confirmed: 0 }

  try {
    await invoke('start_miner', {
      walletPath: walletPath.value.trim(),
      poolUrl: poolUrl.value.trim(),
      poolPublicKeyHex: poolPublicKeyHex.value.trim(),
      password: password.value || null,
    })
    running.value = true
  } catch (err) {
    pushLog(`[error] ${t('errStart')}: ${String(err)}`)
  }
}

async function stopMining() {
  try {
    await invoke('stop_miner')
  } catch (err) {
    pushLog(`[error] ${t('errStop')}: ${String(err)}`)
  }
  running.value = false
}

onMounted(async () => {
  unlistenLog = await listen<string>('miner-log', (event) => pushLog(event.payload))
  unlistenExit = await listen<number | null>('miner-exit', (event) => {
    pushLog(`[${t('processExited')}: ${event.payload ?? t('unknown')}]`)
    running.value = false
  })
})

onUnmounted(() => {
  unlistenLog?.()
  unlistenExit?.()
})
</script>

<template>
  <main class="shell">
    <div class="header-row">
      <h1>{{ t('title') }}</h1>
      <button type="button" class="lang-toggle" @click="toggleLang">{{ lang === 'ro' ? 'EN' : 'RO' }}</button>
    </div>

    <section class="form">
      <label>
        {{ t('walletLabel') }}
        <div class="row">
          <input v-model="walletPath" :disabled="running" placeholder="D:\WEBD\portofelul-meu.webd" />
          <button type="button" @click="pickWallet" :disabled="running">{{ t('browse') }}</button>
        </div>
      </label>

      <label>
        {{ t('passwordLabel') }}
        <input v-model="password" :disabled="running" type="password" placeholder="••••••••" />
      </label>

      <label>
        {{ t('poolUrlLabel') }}
        <input v-model="poolUrl" :disabled="running" />
      </label>

      <label>
        {{ t('poolKeyLabel') }}
        <input v-model="poolPublicKeyHex" :disabled="running" />
      </label>

      <div class="actions">
        <button type="button" class="primary" :disabled="!canStart" @click="startMining">{{ t('start') }}</button>
        <button type="button" class="danger" :disabled="!running" @click="stopMining">{{ t('stop') }}</button>
      </div>
    </section>

    <section class="status">
      <div class="badge" :class="{ ok: status.connected }">{{ status.connected ? t('connected') : t('disconnected') }}</div>
      <div class="badge">{{ t('height') }}: {{ status.height }}</div>
      <div class="badge">{{ t('heartbeats') }}: {{ status.heartbeats }}</div>
      <div class="badge">{{ t('realMatches') }}: {{ status.realMatches }}</div>
      <div class="badge">{{ t('reward') }}: {{ status.reward }}</div>
      <div class="badge">{{ t('confirmed') }}: {{ status.confirmed }}</div>
    </section>

    <section class="log" ref="logEl">
      <div v-for="(line, i) in logLines" :key="i" class="log-line">{{ line }}</div>
    </section>
  </main>
</template>

<style>
:root {
  --bg: #0f1115;
  --panel: #171a21;
  --border: #2a2f3a;
  --text: #e6e8eb;
  --muted: #8b93a1;
  --accent: #3fa7ff;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: 'Segoe UI', system-ui, sans-serif;
}

.shell {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 40px;
}

h1 { font-size: 20px; margin: 0; }

.header-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.lang-toggle { padding: 4px 10px; font-size: 12px; }

.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--muted); }

input {
  background: #0d0f14;
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 14px;
}

.row { display: flex; gap: 8px; }
.row input { flex: 1; }

button {
  border: 1px solid var(--border);
  background: #20242e;
  color: var(--text);
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}
button:disabled { opacity: 0.4; cursor: not-allowed; }
button.primary { background: var(--accent); border-color: var(--accent); color: #06121f; }
button.danger { background: #3a1d1d; border-color: #5a2a2a; }

.actions { display: flex; gap: 8px; margin-top: 4px; }

.status { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.badge {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--muted);
}
.badge.ok { color: #6ee7a8; border-color: #245a3a; }

.log {
  background: #0a0b0e;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  height: 280px;
  overflow-y: auto;
  font-family: Consolas, monospace;
  font-size: 12px;
}
.log-line { color: var(--muted); white-space: pre-wrap; }
</style>
