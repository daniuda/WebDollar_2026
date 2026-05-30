<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>Adaugă adresă WEBD</h3>
      <input
        v-model="address"
        placeholder="WEBD$..."
        class="input"
        @keyup.enter="submit"
      />
      <input
        v-model="label"
        placeholder="Label (opțional, ex: Wallet tipbot)"
        class="input"
        @keyup.enter="submit"
      />
      <div class="error-msg" v-if="error">{{ error }}</div>
      <div class="dialog-actions">
        <button @click="$emit('close')" class="btn-cancel">Anulează</button>
        <button @click="submit" class="btn-add">Adaugă</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  (e: 'add', address: string, label: string): void
  (e: 'close'): void
}>()

const address = ref('')
const label = ref('')
const error = ref('')

function submit() {
  const trimmed = address.value.trim()
  if (!trimmed) {
    error.value = 'Adresa nu poate fi goală'
    return
  }
  if (!trimmed.startsWith('WEBD$') && !trimmed.match(/^[0-9a-fA-F]{40}$/)) {
    error.value = 'Format adresă invalid (trebuie să înceapă cu WEBD$)'
    return
  }
  error.value = ''
  emit('add', trimmed, label.value.trim())
  address.value = ''
  label.value = ''
}
</script>
