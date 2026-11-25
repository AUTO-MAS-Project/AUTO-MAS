<!--
  库街区短信登录。
  极验 v4 的人机验证只能在浏览器里完成，宿主本体没有验证码渲染能力，
  所以这里只做「打开会话 → 自动发送（需插件侧配置云码）→ 提交六位验证码」这条链路；
  自动发送未成功时把插件给出的原因原样展示，并提示到插件设置里配置云码或改用其它方式绑定。
-->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { signflowApi, SignflowError } from '@/services/signflowApi'

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

const phone = ref('')
const code = ref('')
const sessionId = ref('')
const sending = ref(false)
const submitting = ref(false)
const notice = ref('')
let generation = 0

const phoneValid = computed(() => /^1[3-9]\d{9}$/.test(phone.value.trim()))
const canSubmit = computed(() => /^\d{6}$/.test(code.value.trim()) && !!sessionId.value)

const reset = () => {
  generation += 1
  phone.value = ''
  code.value = ''
  sessionId.value = ''
  sending.value = false
  submitting.value = false
  notice.value = ''
}

watch(
  () => [props.open, props.accountUid] as const,
  () => {
    reset()
  }
)

const errorText = (error: unknown): string =>
  error instanceof Error ? error.message : String(error)

const send = async () => {
  if (!phoneValid.value || !props.accountUid) return
  const current = ++generation
  sending.value = true
  notice.value = ''
  try {
    const session = sessionId.value
      ? { sessionId: sessionId.value, captchaId: '' }
      : await signflowApi.openTokenLogin(props.accountUid, phone.value.trim())
    if (current !== generation) return
    sessionId.value = session.sessionId
    // automatic 需要插件侧配置云码；未配置时插件返回 sent=false 并说明要人工验证
    const result = await signflowApi.sendTokenLoginCode(session.sessionId, null, true)
    if (current !== generation) return
    if (result.sent) {
      message.success(result.message || t('core.gamesign.sms.sent'))
      return
    }
    notice.value = result.message || t('core.gamesign.sms.manualRequired')
  } catch (error) {
    if (current !== generation) return
    logger.error(`库街区短信发送失败: ${errorText(error)}`)
    notice.value = errorText(error)
  } finally {
    if (current === generation) sending.value = false
  }
}

const submit = async () => {
  if (!canSubmit.value) return
  const current = ++generation
  submitting.value = true
  try {
    const result = await signflowApi.submitTokenLoginCode(sessionId.value, code.value.trim())
    if (current !== generation) return
    message.success(result.message || t('core.gamesign.toast.tokenSaved'))
    emit('saved')
    emit('close')
    reset()
  } catch (error) {
    if (current !== generation) return
    // 插件未启用时给出可读原因，而不是「登录失败」
    notice.value =
      error instanceof SignflowError && error.code === 400 ? error.message : errorText(error)
  } finally {
    if (current === generation) submitting.value = false
  }
}
</script>

<template>
  <a-modal
    :open="props.open"
    :title="t('core.gamesign.sms.title')"
    :width="400"
    :footer="null"
    centered
    @cancel="emit('close')"
  >
    <div class="sms-form">
      <a-alert type="info" show-icon :message="t('core.gamesign.sms.hint')" />
      <a-input
        v-model:value="phone"
        size="large"
        :maxlength="11"
        :placeholder="t('core.gamesign.sms.phonePlaceholder')"
      />
      <a-button type="primary" block :loading="sending" :disabled="!phoneValid" @click="send">
        {{ sessionId ? t('core.gamesign.sms.resend') : t('core.gamesign.sms.send') }}
      </a-button>
      <a-input
        v-model:value="code"
        size="large"
        :maxlength="6"
        :placeholder="t('core.gamesign.sms.codePlaceholder')"
      />
      <a-button type="primary" block :loading="submitting" :disabled="!canSubmit" @click="submit">
        {{ t('core.gamesign.login.submit') }}
      </a-button>
      <a-alert v-if="notice" type="warning" show-icon :message="notice" />
    </div>
  </a-modal>
</template>

<style scoped>
.sms-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
</style>
