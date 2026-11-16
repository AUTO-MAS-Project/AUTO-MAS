<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { emulatorTabTitle } from './emulatorTabTitle'
defineProps<{ info: { name: string; path: string } }>()
const { t } = useI18n()
</script>

<template>
  <span class="tab-title" :title="info.name">{{
    emulatorTabTitle(info.name || t('core.emulator.unnamed'), info.path)
  }}</span>
</template>
