<template>
  <div class="app">
    <header class="app-header">
      <div class="header-left">
        <h1>WEBD Tracker</h1>
        <span class="block-info" v-if="currentBlock">
          Bloc: {{ currentBlock.toLocaleString() }}
        </span>
        <span class="block-info error" v-else-if="apiError">⚠ API offline</span>
      </div>
      <div class="header-right">
        <button @click="refresh" :disabled="refreshing" class="btn-refresh">
          {{ refreshing ? '...' : '↻ Refresh' }}
        </button>
        <button @click="showAdd = true" class="btn-add">+ Add</button>
      </div>
    </header>

    <main class="entries-list">
      <div v-if="entries.length === 0" class="empty-state">
        Nicio adresă adăugată. Apasă "+ Add" pentru a începe.
      </div>
      <AddressCard
        v-for="entry in entries"
        :key="entry.address"
        :entry="entry"
        :currentBlock="currentBlock"
        @delete="removeEntry"
      />
    </main>

    <footer>
      <SettingsBar v-model="refreshInterval" />
      <button @click="exportJson" class="btn-export">Export JSON</button>
    </footer>

    <AddDialog
      v-if="showAdd"
      @add="addEntry"
      @close="showAdd = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { TrackerEntry } from './types'
import {
  getEntries, saveEntry, deleteEntry, getRefreshInterval, setRefreshInterval,
} from './services/storageService'
import { fetchCurrentBlock, fetchBatchBalances } from './services/apiService'
import AddressCard from './components/AddressCard.vue'
import AddDialog from './components/AddDialog.vue'
import SettingsBar from './components/SettingsBar.vue'

const entries = ref<TrackerEntry[]>(getEntries())
const currentBlock = ref<number | null>(null)
const showAdd = ref(false)
const refreshing = ref(false)
const apiError = ref(false)
const refreshInterval = ref(getRefreshInterval())

let intervalId: ReturnType<typeof setInterval> | null = null

async function refresh() {
  refreshing.value = true
  apiError.value = false
  try {
    const block = await fetchCurrentBlock()
    if (block === null) { apiError.value = true; return }
    currentBlock.value = block

    const stale = entries.value.filter((e) => e.lastBlock < block)
    if (stale.length === 0) return

    const results = await fetchBatchBalances(stale.map((e) => e.address))
    const now = new Date().toISOString()

    for (const result of results) {
      const entry = entries.value.find((e) => e.address === result.address)
      if (!entry) continue
      const updated: TrackerEntry = {
        ...entry,
        balance: result.balance,
        lastBlock: result.lastBlock ?? block,
        lastUpdated: now,
        error: result.balance === null,
      }
      saveEntry(updated)
    }
    entries.value = getEntries()
  } finally {
    refreshing.value = false
  }
}

function addEntry(address: string, label: string) {
  const entry: TrackerEntry = {
    address,
    label,
    balance: null,
    lastBlock: 0,
    lastUpdated: '',
  }
  saveEntry(entry)
  entries.value = getEntries()
  showAdd.value = false
  refresh()
}

function removeEntry(address: string) {
  deleteEntry(address)
  entries.value = getEntries()
}

function exportJson() {
  const blob = new Blob([JSON.stringify(entries.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'webd-tracker-backup.json'
  a.click()
  URL.revokeObjectURL(url)
}

function startAutoRefresh() {
  if (intervalId) clearInterval(intervalId)
  if (refreshInterval.value > 0) {
    intervalId = setInterval(refresh, refreshInterval.value * 60 * 1000)
  }
}

watch(refreshInterval, (val) => {
  setRefreshInterval(val)
  startAutoRefresh()
})

onMounted(() => {
  refresh()
  startAutoRefresh()
})

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>
