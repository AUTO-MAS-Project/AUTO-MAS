<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, ArrowRightOutlined, LockOutlined } from '@ant-design/icons-vue'
import { GetService, UpdateService } from '@/api'
import { navigateTo } from '@/router'
import { useMysteryStore } from '@/stores/mystery'

const { t } = useI18n()
const route = useRoute()
const store = useMysteryStore()
const logger = window.electronAPI.getLogger('神秘入口')
const form = reactive({ accessCode: '' })
const error = ref('')
const loadFailed = ref(false)

const isFeaturePage = computed(() => route.name !== 'Mystery')
const pageTitle = computed(() =>
  store.unlocked && typeof route.meta.mysteryTitleKey === 'string'
    ? t(route.meta.mysteryTitleKey)
    : t('mystery.entry')
)

const back = () => {
  if (isFeaturePage.value) {
    navigateTo('/settings/mystery')
  } else {
    navigateTo('/settings', { query: { tab: 'function' } })
  }
}

const openTokens = () => navigateTo('/settings/mystery/tokens')

// 「并非神秘入口」：个人版 MaaStellaSora 的专属编排开关（Function.IfPersonalMss）。
// 启用不另设密码——神秘入口自己的密钥门槛就是防手滑的那道门。
const personalMssEnabled = ref(false)
const personalMssSaving = ref(false)

const loadPersonalMss = async () => {
  try {
    const response = await GetService.getScriptsApiSettingGetPost()
    if (response.code !== 200) return
    personalMssEnabled.value = response.data?.Function?.IfPersonalMss === true
  } catch {
    // 读不到就按关闭显示：这是展示位上的开关，后端一时拿不到不该拦住解锁流程
    personalMssEnabled.value = false
  }
}

const savePersonalMss = async (enabled: boolean) => {
  personalMssSaving.value = true
  try {
    const response = await UpdateService.updateScriptApiSettingUpdatePost({
      data: { Function: { IfPersonalMss: enabled } },
    })
    if (response.code !== 200) {
      message.error(t('mystery.personalMss.failed'))
      return
    }
    personalMssEnabled.value = enabled
    message.success(t(enabled ? 'mystery.personalMss.on' : 'mystery.personalMss.off'))
  } catch {
    message.error(t('mystery.personalMss.failed'))
  } finally {
    personalMssSaving.value = false
  }
}

const handlePersonalMssToggle = async (checked: boolean | string | number) => {
  const next = checked === true
  // 值没变就别写：开关的 onChange 不保证只在用户改过时才来
  if (next === personalMssEnabled.value) return
  await savePersonalMss(next)
}

const load = async () => {
  loadFailed.value = false
  try {
    await store.load()
  } catch (cause) {
    loadFailed.value = true
    logger.error(`加载失败: ${cause instanceof Error ? cause.message : String(cause)}`)
  }
}

onMounted(() => {
  void load()
  void loadPersonalMss()
})

const unlock = async () => {
  error.value = ''
  try {
    if (!(await store.unlock(form.accessCode))) {
      error.value = t('mystery.accessCodeInvalid')
      return
    }
    form.accessCode = ''
  } catch (cause) {
    logger.error(`解锁失败: ${cause instanceof Error ? cause.message : String(cause)}`)
    error.value = t('mystery.saveFailed')
  }
}

const lock = async () => {
  try {
    await store.lock()
    form.accessCode = ''
    error.value = ''
  } catch (cause) {
    logger.error(`重新锁定失败: ${cause instanceof Error ? cause.message : String(cause)}`)
    message.error(t('mystery.saveFailed'))
  }
}
</script>

<template>
  <div class="mystery-page">
    <div class="mystery-header">
      <div class="mystery-heading">
        <a-button @click="back">
          <template #icon><ArrowLeftOutlined /></template>
          {{ t(isFeaturePage ? 'mystery.backToOverview' : 'mystery.back') }}
        </a-button>
        <h1>{{ pageTitle }}</h1>
      </div>
      <a-button v-if="store.unlocked" :loading="store.saving" @click="lock">
        <template #icon><LockOutlined /></template>
        {{ t('mystery.lock') }}
      </a-button>
    </div>

    <div class="mystery-content" :class="{ 'mystery-content-unlocked': store.unlocked }">
      <a-result v-if="loadFailed" status="error" :title="t('mystery.loadFailed')">
        <template #extra>
          <a-button type="primary" @click="load">{{ t('mystery.retry') }}</a-button>
        </template>
      </a-result>
      <div v-else-if="!store.initialized" class="mystery-loading">
        <a-spin />
      </div>
      <a-card v-else-if="!store.unlocked" :title="t('mystery.unlockTitle')" class="mystery-unlock">
        <a-form :model="form" layout="vertical" @finish="unlock">
          <a-form-item
            name="accessCode"
            :rules="[{ required: true, message: t('mystery.accessCodeRequired') }]"
            :validate-status="error ? 'error' : undefined"
            :help="error || undefined"
          >
            <a-input-password
              v-model:value="form.accessCode"
              :aria-label="t('mystery.accessCode')"
              :placeholder="t('mystery.accessCodePlaceholder')"
              :disabled="store.saving"
              size="large"
              autocomplete="off"
              @change="error = ''"
            />
          </a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="store.saving">
            {{ t('mystery.unlock') }}
          </a-button>
        </a-form>
      </a-card>
      <!-- 子页面共用解锁门槛，锁定或跨日后卸载正在运行的功能。 -->
      <router-view v-else-if="isFeaturePage" />
      <a-row v-else :gutter="[16, 16]">
        <a-col :xs="24" :sm="12" :lg="8">
          <a-card
            hoverable
            :title="t('mystery.tokens.title')"
            :aria-label="t('mystery.tokens.title')"
            role="button"
            tabindex="0"
            @click="openTokens"
            @keydown.enter="openTokens"
            @keydown.space.prevent="openTokens"
          >
            <template #extra><ArrowRightOutlined /></template>
            {{ t('mystery.tokens.entryDescription') }}
          </a-card>
        </a-col>
        <a-col :xs="24" :sm="12" :lg="8">
          <a-card :title="t('mystery.personalMss.title')" :aria-label="t('mystery.personalMss.title')">
            {{ t('mystery.personalMss.hint') }}
            <div class="personal-mss-switch">
              <a-switch
                :checked="personalMssEnabled"
                :loading="personalMssSaving"
                :aria-label="t('mystery.personalMss.title')"
                @change="handlePersonalMssToggle"
              />
            </div>
          </a-card>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<style scoped>
.mystery-page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.mystery-header,
.mystery-heading {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.mystery-header {
  justify-content: space-between;
  margin-bottom: 24px;
}

.mystery-heading h1 {
  margin: 0;
  font-size: 24px;
  color: var(--ant-color-text);
}

.mystery-unlock {
  width: 100%;
  max-width: 520px;
}

.mystery-unlock :deep(.ant-card-head-title) {
  text-align: center;
  font-size: 20px;
}

.mystery-unlock :deep(.ant-card-body) {
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

.personal-mss-switch {
  margin-top: 16px;
}
</style>
