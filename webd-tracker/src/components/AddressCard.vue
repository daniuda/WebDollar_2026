<template>
  <div class="card" :class="statusClass">
    <div class="card-header">
      <span class="status-dot">{{ statusIcon }}</span>
      <span class="label">{{ entry.label || 'Fără label' }}</span>
      <button class="delete-btn" @click="$emit('delete', entry.address)">✕</button>
    </div>
    <div class="address">{{ shortAddress }}</div>
    <div class="balance" v-if="entry.balance !== null">
      {{ formatBalance(entry.balance) }} WEBD
    </div>
    <div class="balance error" v-else-if="entry.error">Eroare la interogare</div>
    <div class="balance loading" v-else>Se încarcă...</div>
    <div class="meta">
      bloc {{ entry.lastBlock > 0 ? entry.lastBlock.toLocaleString() : '—' }}
      <span v-if="entry.lastUpdated"> · {{ timeAgo(entry.lastUpdated) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TrackerEntry } from '../types'

const props = defineProps<{ entry: TrackerEntry; currentBlock: number | null }>()
defineEmits<{ (e: 'delete', address: string): void }>()

const shortAddress = computed(() => {
  const a = props.entry.address
  return a.length > 20 ? a.slice(0, 12) + '...' + a.slice(-6) : a
})

const statusClass = computed(() => {
  if (props.entry.error) return 'status-red'
  if (props.entry.balance === null) return 'status-gray'
  if (props.currentBlock && props.entry.lastBlock >= props.currentBlock) return 'status-green'
  if (props.currentBlock && props.currentBlock - props.entry.lastBlock < 100) return 'status-yellow'
  return 'status-red'
})

const statusIcon = computed(() => {
  if (statusClass.value === 'status-green') return '🟢'
  if (statusClass.value === 'status-yellow') return '🟡'
  if (statusClass.value === 'status-gray') return '⚪'
  return '🔴'
})

function formatBalance(b: number): string {
  return b.toLocaleString('ro-RO')
}

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}min`
  return `${Math.floor(diff / 3600)}h`
}
</script>
