<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { handleExternalLink } from '@/utils/openExternal'

const { t } = useI18n()
const { loading, error, getSettings, updateSettings } = useSettingsApi()
const enabled = ref(false)
const loaded = ref(false)

const load = async () => {
  loaded.value = false
  const settings = await getSettings()
  if (!settings) return
  enabled.value = settings.Function?.IfAgreeBilibili === true
  loaded.value = true
}

const toggle = async (checked: boolean | string | number) => {
  const next = checked === true
  if (!loaded.value || loading.value || next === enabled.value) return
  if (await updateSettings({ Function: { IfAgreeBilibili: next } })) {
    enabled.value = next
  }
}

onMounted(load)
</script>

<template>
  <a-card :title="t('core.setting.func.biliPolicy')">
    <p>{{ t('core.setting.func.biliIntro') }}</p>
    <ul>
      <li>
        <a href="https://www.bilibili.com/protocal/licence.html" @click="handleExternalLink">
          {{ t('core.setting.func.biliTerms') }}
        </a>
      </li>
      <li>
        <a href="https://www.bilibili.com/blackboard/privacy-pc.html" @click="handleExternalLink">
          {{ t('core.setting.func.biliPrivacy') }}
        </a>
      </li>
      <li>
        <a href="https://game.bilibili.com/yhxy" @click="handleExternalLink">
          {{ t('core.setting.func.biliGame') }}
        </a>
      </li>
    </ul>
    <a-space direction="vertical">
      <a-switch
        :checked="enabled"
        :loading="loading"
        :disabled="!loaded"
        :aria-label="t('core.setting.func.biliPolicy')"
        @change="toggle"
      />
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-button v-if="!loaded && !loading" @click="load">{{ t('core.mystery.retry') }}</a-button>
    </a-space>
  </a-card>
</template>
