<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, ArrowRightOutlined, LockOutlined } from '@ant-design/icons-vue'
import { navigateTo } from '@/router'
import { AppPage, PageHeader, SectionCard } from '@/components/ui'
import { useMysteryStore } from '@/stores/mystery'
import BilibiliAgreement from './BilibiliAgreement.vue'

const { t } = useI18n()
const route = useRoute()
const store = useMysteryStore()
const logger = window.electronAPI.getLogger('神秘入口')
const form = reactive({ accessCode: '' })
const error = ref('')
const loadErrorMessage = computed(() => {
  if (store.loadError === 'DEVICE_UNAVAILABLE') return t('core.mystery.deviceUnavailable')
  if (store.loadError === 'BACKEND_UNAVAILABLE') return t('core.mystery.backendUnavailable')
  return t('core.mystery.loadFailed')
})

const isFeaturePage = computed(() => route.name !== 'Mystery')
const pageTitle = computed(() =>
  store.unlocked && typeof route.meta.mysteryTitleKey === 'string'
    ? t(route.meta.mysteryTitleKey)
    : t('core.mystery.entry')
)

const back = () => {
  if (isFeaturePage.value) {
    navigateTo('/settings/mystery')
  } else {
    navigateTo('/settings', { query: { tab: 'function' } })
  }
}

const openTokens = () => navigateTo('/settings/mystery/tokens')

const load = async () => {
  try {
    await store.load()
  } catch (cause) {
    logger.error(`加载失败: ${cause instanceof Error ? cause.message : String(cause)}`)
  }
}

onMounted(() => {
  void load()
})

const unlock = async () => {
  error.value = ''
  try {
    if (!(await store.unlock(form.accessCode))) {
      error.value = t('core.mystery.accessCodeInvalid')
      return
    }
    form.accessCode = ''
  } catch (cause) {
    logger.error(`解锁失败: ${cause instanceof Error ? cause.message : String(cause)}`)
    error.value = t('core.mystery.saveFailed')
  }
}

const lock = async () => {
  try {
    await store.lock()
    form.accessCode = ''
    error.value = ''
  } catch (cause) {
    logger.error(`重新锁定失败: ${cause instanceof Error ? cause.message : String(cause)}`)
    message.error(t('core.mystery.saveFailed'))
  }
}
</script>

<template>
  <AppPage layout="scroll">
    <PageHeader :title="pageTitle">
      <template #leading>
        <a-button @click="back">
          <template #icon><ArrowLeftOutlined /></template>
          {{ t(isFeaturePage ? 'core.mystery.backToOverview' : 'core.mystery.back') }}
        </a-button>
      </template>
      <template #actions>
        <a-button v-if="store.unlocked" :loading="store.saving" @click="lock">
          <template #icon><LockOutlined /></template>
          {{ t('core.mystery.lock') }}
        </a-button>
      </template>
    </PageHeader>

    <div class="mystery-content" :class="{ 'mystery-content-unlocked': store.unlocked }">
      <a-result v-if="store.loadError" status="error" :title="loadErrorMessage">
        <template #extra>
          <a-button type="primary" @click="load">{{ t('core.mystery.retry') }}</a-button>
        </template>
      </a-result>
      <div v-else-if="!store.initialized" class="mystery-loading">
        <a-spin />
      </div>
      <SectionCard v-else-if="!store.unlocked" class="mystery-unlock">
        <template #title>{{ t('core.mystery.unlockTitle') }}</template>
        <a-typography-paragraph>{{ t('core.mystery.accessCodeHint') }}</a-typography-paragraph>
        <a-form :model="form" layout="vertical" @finish="unlock">
          <a-form-item
            name="accessCode"
            :rules="[{ required: true, message: t('core.mystery.accessCodeRequired') }]"
            :validate-status="error ? 'error' : undefined"
            :help="error || undefined"
          >
            <a-input-password
              v-model:value="form.accessCode"
              :aria-label="t('core.mystery.accessCode')"
              :placeholder="t('core.mystery.accessCodePlaceholder')"
              :disabled="store.saving"
              size="large"
              autocomplete="off"
              @change="error = ''"
            />
          </a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="store.saving">
            {{ t('core.mystery.unlock') }}
          </a-button>
        </a-form>
      </SectionCard>
      <!-- 子页面共用解锁门槛，锁定或跨日后卸载正在运行的功能。 -->
      <router-view v-else-if="isFeaturePage" />
      <a-row v-else :gutter="[16, 16]">
        <a-col :xs="24" :sm="12" :lg="8">
          <BilibiliAgreement />
        </a-col>
        <a-col :xs="24" :sm="12" :lg="8">
          <a-card
            hoverable
            :title="t('core.mystery.tokens.title')"
            :aria-label="t('core.mystery.tokens.title')"
            role="button"
            tabindex="0"
            @click="openTokens"
            @keydown.enter="openTokens"
            @keydown.space.prevent="openTokens"
          >
            <template #extra><ArrowRightOutlined /></template>
            {{ t('core.mystery.tokens.entryDescription') }}
          </a-card>
        </a-col>
      </a-row>
    </div>
  </AppPage>
</template>

<style scoped>
.mystery-unlock.ui-section-card {
  width: 100%;
  max-width: 520px;
  margin-bottom: 0;
  padding: 0;
}

.mystery-unlock.ui-section-card :deep(.section-header h3) {
  grid-column: 1 / -1;
  justify-content: center;
  font-size: 20px;
}

.mystery-unlock :deep(.ui-section-card-body) {
  padding: 32px;
}

.mystery-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mystery-content-unlocked {
  display: block;
}

.mystery-loading {
  min-height: 224px;
  display: grid;
  place-items: center;
}
</style>
