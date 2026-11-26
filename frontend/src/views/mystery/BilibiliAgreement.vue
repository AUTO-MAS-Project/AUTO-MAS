<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { SectionCard } from '@/components/ui'
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
  <SectionCard :title="t('core.setting.func.biliPolicy')" style="margin-bottom: 0">
    <template #actions>
      <a-switch
        :checked="enabled"
        :loading="loading"
        :disabled="!loaded"
        :aria-label="t('core.setting.func.biliPolicy')"
        @change="toggle"
      />
    </template>
    <p>{{ t('core.setting.func.biliIntro') }}</p>
    <ul>
      <li
        v-for="(label, href) in {
          'https://www.bilibili.com/protocal/licence.html': t('core.setting.func.biliTerms'),
          'https://www.bilibili.com/blackboard/privacy-pc.html': t('core.setting.func.biliPrivacy'),
          'https://game.bilibili.com/yhxy': t('core.setting.func.biliGame'),
        }"
        :key="href"
      >
        <a :href="href" @click="handleExternalLink">{{ label }}</a>
      </li>
    </ul>
    <a-space direction="vertical">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-button v-if="!loaded && !loading" @click="load">{{ t('core.mystery.retry') }}</a-button>
    </a-space>
  </SectionCard>
</template>
