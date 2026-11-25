<!--
  塔吉多 / 云异环账密登录。
  账密由后端兑换成凭据后直接落库，这里不接收也不保存任何 Token 文本；
  成功后只通知调用方回读账号组，避免把响应里的中间值当成凭据写进表单。
-->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { CancelablePromise, OutBase } from '@/api'
import { useTokenApi } from '@/views/mystery/tokens/useTokenApi'

const props = defineProps<{
  open: boolean
  accountUid: string
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('游戏社区')
const { loginTaygedo } = useTokenApi()

const form = ref({ phone: '', password: '' })
const loading = ref(false)
let loginRequest: CancelablePromise<OutBase> | undefined

watch(
  () => props.open,
  open => {
    if (open) form.value = { phone: '', password: '' }
  }
)

/**
 * 关闭弹窗：取消在途请求时一并复位加载态。
 *
 * 取消后 Promise 会 reject，但那时 loginRequest 已被清空，finally 里的身份比对不再成立，
 * 只复位 loading 的分支不会执行；这里不显式复位，下次打开提交按钮会一直转圈。
 */
const close = () => {
  loginRequest?.cancel()
  loginRequest = undefined
  loading.value = false
  form.value = { phone: '', password: '' }
  emit('close')
}

const submit = async () => {
  const phone = form.value.phone.trim()
  const password = form.value.password
  if (!phone || !password || !props.accountUid) return
  loading.value = true
  const request = loginTaygedo(props.accountUid, phone, password)
  loginRequest = request
  try {
    const response = await request
    if (loginRequest !== request) return
    if (response.code !== 200 || response.status !== 'success') {
      message.error(response.message || t('core.mystery.tokens.taygedoFailed'))
      return
    }
    message.success(t('core.gamesign.toast.tokenSaved'))
    close()
    emit('saved')
  } catch (error) {
    // 用户关闭弹窗会取消请求，这不是登录失败，迟到的 reject 直接丢弃
    if (loginRequest !== request) return
    logger.error(`塔吉多账密登录失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error(t('core.mystery.tokens.taygedoFailed'))
  } finally {
    if (loginRequest === request) {
      loginRequest = undefined
      loading.value = false
    }
  }
}
</script>

<template>
  <a-modal
    :open="props.open"
    :title="t('core.gamesign.login.taygedoTitle')"
    :width="380"
    :footer="null"
    centered
    @cancel="close"
  >
    <div class="password-form">
      <a-input
        v-model:value="form.phone"
        size="large"
        :placeholder="t('core.gamesign.login.taygedoAccountPlaceholder')"
      />
      <a-input-password
        v-model:value="form.password"
        size="large"
        :placeholder="t('core.gamesign.login.taygedoPasswordPlaceholder')"
      />
      <a-button
        type="primary"
        block
        :loading="loading"
        :disabled="!form.phone.trim() || !form.password"
        @click="submit"
      >
        {{ t('core.gamesign.login.submit') }}
      </a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.password-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
</style>
