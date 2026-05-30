<template>
  <div class="settings-bar">
    <span>Auto-refresh:</span>
    <select :value="modelValue" @change="onChange" class="select-interval">
      <option :value="0">Off</option>
      <option :value="5">5 min</option>
      <option :value="15">15 min</option>
      <option :value="30">30 min</option>
      <option :value="60">60 min</option>
    </select>
  </div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: number): void }>()
function onChange(e: Event) {
  emit('update:modelValue', Number((e.target as HTMLSelectElement).value))
}
</script>
