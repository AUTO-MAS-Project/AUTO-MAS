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
import { AppModal } from '@/components/ui'
import { isPluginUnavailable, signflowApi } from '@/services/signflowApi'
import { beginAnalyticsOperation } from '@/utils/analytics'

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
/** 已开会话对应的手机号；号码一改，旧会话里的验证码就作废 */
const sessionPhone = ref('')
const sending = ref(false)
const submitting = ref(false)
const notice = ref('')
let generation = 0
/**
 * 一次短信登录从第一发「发送验证码」开始，到凭据落库或弹窗关闭结束。
 * 用 settled 兜住多条出口（提交成功、重复关闭、帐号切换），保证只报一次终态。
 */
let loginOperation: ReturnType<typeof beginAnalyticsOperation<'community_login_finished'>> | null =
  null
let loginSettled = true
const finishLogin = (outcome: 'saved' | 'failure' | 'expired' | 'cancelled' | 'unsupported') => {
  if (loginSettled) return
  loginSettled = true
  loginOperation?.finish({ provider: 'kuro', stage: 'sms', outcome })
  loginOperation = null
}
const beginLogin = () => {
  if (!loginSettled) return
  loginSettled = false
  loginOperation = beginAnalyticsOperation('community_login_finished')
}

const phoneValid = computed(() => /^1[3-9]\d{9}$/.test(phone.value.trim()))
const canSubmit = computed(() => /^\d{6}$/.test(code.value.trim()) && !!sessionId.value)
/** 发送与提交都占用插件侧的同一条会话，一次只让一个跑 */
const busy = computed(() => sending.value || submitting.value)

const reset = () => {
  // 换号或重新打开时上一条链路就此中断，不能留成永久未决
  finishLogin('cancelled')
  generation += 1
  phone.value = ''
  code.value = ''
  sessionId.value = ''
  sessionPhone.value = ''
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

// 换号后旧会话仍绑着上一个号码，重发会往原号码发码，必须整条作废
watch(phone, value => {
  if (!sessionId.value || value.trim() === sessionPhone.value) return
  sessionId.value = ''
  sessionPhone.value = ''
  code.value = ''
  notice.value = ''
})

const errorText = (error: unknown): string =>
  error instanceof Error ? error.message : String(error)

const send = async () => {
  if (!phoneValid.value || !props.accountUid || busy.value) return
  const current = ++generation
  const targetPhone = phone.value.trim()
  beginLogin()
  sending.value = true
  notice.value = ''
  try {
    const session = sessionId.value
      ? { sessionId: sessionId.value, captchaId: '' }
      : await signflowApi.openTokenLogin(props.accountUid, targetPhone)
    // 开会话期间用户改了号码：这条会话属于旧号码，不能再落到当前表单
    if (current !== generation || phone.value.trim() !== targetPhone) return
    sessionId.value = session.sessionId
    sessionPhone.value = targetPhone
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
    notice.value = isPluginUnavailable(error)
      ? t('core.gamesign.sms.pluginUnavailable')
      : errorText(error)
    if (isPluginUnavailable(error)) finishLogin('unsupported')
  } finally {
    if (current === generation) sending.value = false
  }
}

const submit = async () => {
  if (!canSubmit.value || busy.value) return
  const current = ++generation
  submitting.value = true
  try {
    const result = await signflowApi.submitTokenLoginCode(sessionId.value, code.value.trim())
    if (current !== generation) return
    finishLogin('saved')
    message.success(result.message || t('core.gamesign.toast.tokenSaved'))
    emit('saved')
    emit('close')
    reset()
  } catch (error) {
    if (current !== generation) return
    // 插件未启用时给出可读原因，而不是「登录失败」；
    // 判定统一走 services 里的 isPluginUnavailable，不在各处比对业务码
    const unsupported = isPluginUnavailable(error)
    notice.value = unsupported ? t('core.gamesign.sms.pluginUnavailable') : errorText(error)
    finishLogin(unsupported ? 'unsupported' : 'failure')
  } finally {
    if (current === generation) submitting.value = false
  }
}
</script>

<template>
  <AppModal
    :open="props.open"
    :title="t('core.gamesign.sms.title')"
    :width="400"
    footer="none"
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
      <a-button
        type="primary"
        block
        :loading="sending"
        :disabled="!phoneValid || submitting"
        @click="send"
      >
        {{ sessionId ? t('core.gamesign.sms.resend') : t('core.gamesign.sms.send') }}
      </a-button>
      <a-input
        v-model:value="code"
        size="large"
        :maxlength="6"
        :placeholder="t('core.gamesign.sms.codePlaceholder')"
      />
      <a-button
        type="primary"
        block
        :loading="submitting"
        :disabled="!canSubmit || sending"
        @click="submit"
      >
        {{ t('core.gamesign.login.submit') }}
      </a-button>
      <a-alert v-if="notice" type="warning" show-icon :message="notice" />
    </div>
  </AppModal>
</template>

<style scoped>
.sms-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
</style>
