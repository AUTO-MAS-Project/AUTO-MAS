<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Empty, message } from 'ant-design-vue'
import { ArrowLeftOutlined, LockOutlined } from '@ant-design/icons-vue'
import { navigateTo } from '@/router'
import { useMysteryStore } from '@/stores/mystery'

const { t } = useI18n()
const store = useMysteryStore()
const logger = window.electronAPI.getLogger('神秘入口')
const form = reactive({ accessCode: '' })
const error = ref('')
const loadFailed = ref(false)

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
        <a-button @click="navigateTo('/settings', { query: { tab: 'function' } })">
          <template #icon><ArrowLeftOutlined /></template>
          {{ t('mystery.back') }}
        </a-button>
        <h1>{{ t('mystery.entry') }}</h1>
      </div>
      <a-button v-if="store.unlocked" :loading="store.saving" @click="lock">
        <template #icon><LockOutlined /></template>
        {{ t('mystery.lock') }}
      </a-button>
    </div>

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
          :label="t('mystery.accessCode')"
          :rules="[{ required: true, message: t('mystery.accessCodeRequired') }]"
          :validate-status="error ? 'error' : undefined"
          :help="error || undefined"
        >
          <a-input-password
            v-model:value="form.accessCode"
            :placeholder="t('mystery.accessCodePlaceholder')"
            :disabled="store.saving"
            autocomplete="off"
            @change="error = ''"
          />
        </a-form-item>
        <p class="mystery-hint">{{ t('mystery.rememberHint') }}</p>
        <a-button type="primary" html-type="submit" :loading="store.saving">
          {{ t('mystery.unlock') }}
        </a-button>
      </a-form>
    </a-card>
    <!-- 后续神秘小功能放在解锁后的区域，当前保留空状态。 -->
    <a-card v-else>
      <a-empty :image="Empty.PRESENTED_IMAGE_SIMPLE" :description="t('mystery.empty')" />
    </a-card>
  </div>
</template>

<style scoped>
.mystery-page {
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
  max-width: 400px;
}

.mystery-loading {
  min-height: 224px;
  display: grid;
  place-items: center;
}

.mystery-hint {
  margin-bottom: 24px;
  color: var(--ant-color-text-secondary);
}
</style>
