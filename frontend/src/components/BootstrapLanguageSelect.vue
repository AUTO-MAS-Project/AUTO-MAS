<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, type AppLocale } from '@/i18n'
import { useLocale } from '@/composables/useLocale'

const { t } = useI18n()
const { locale, setLocale, switching } = useLocale()
</script>

<template>
  <a-select
    :value="locale"
    :loading="switching"
    :aria-label="t('bootstrap.i18n.language')"
    @change="(value: AppLocale) => setLocale(value)"
  >
    <a-select-option v-for="item in SUPPORTED_LOCALES" :key="item" :value="item">
      {{ t(`bootstrap.locale.${item}`) }}
    </a-select-option>
  </a-select>
</template>
