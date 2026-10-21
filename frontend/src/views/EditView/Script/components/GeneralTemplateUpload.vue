<script setup lang="ts">
import { onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, type FormInstance } from 'ant-design-vue'
import { CloudUploadOutlined } from '@ant-design/icons-vue'
import { openExternalUrl } from '@/utils/openExternal'
import {
  queueGeneralShareAuthAction as queueAuthAction,
  waitForGeneralShareAuth,
} from './generalShareAuthQueue'
import {
  IDLE_SHARE_AUTH,
  useShareApi,
  type ShareAuthState,
  type ShareRiskItem,
} from '@/composables/useShareApi'
const props = defineProps<{ scriptId: string; scriptName: string }>()
const { scriptId } = props
const { t } = useI18n()
const logger = window.electronAPI.getLogger('通用脚本模板上传')
const uploadFormRef = ref<FormInstance>()
const {
  error: shareError,
  getShareAuthStatus,
  startShareAuth,
  pollShareAuth,
  cancelShareAuth,
  inspectShare,
  uploadShare,
} = useShareApi()
// 弹窗和授权各自标记代次，关闭后仅让已发出的请求完成，不再更新新的视图。
const uploadModalVisible = ref(false)
const uploadLoading = ref(false)
const dialogLoading = ref(false)
const shareAuthLoading = ref(false)
const shareAuth = ref<ShareAuthState>({ ...IDLE_SHARE_AUTH })
const shareRisks = ref<ShareRiskItem[]>([])
const riskAcknowledged = ref(false)
const uploadForm = reactive({ config_name: '', description: '' })
const uploadRules = {
  config_name: [{ required: true, message: t('edit.enterConfigurationName'), trigger: 'blur' }],
  description: [{ required: true, message: t('edit.enterDescription'), trigger: 'blur' }],
}
let alive = true
let dialogOpen = false
let dialogVersion = 0
let authVersion = 0
let riskVersion = 0
let sharePollTimer: ReturnType<typeof setTimeout> | null = null
const currentDialog = (version: number) =>
  alive && uploadModalVisible.value && version === dialogVersion
const stopSharePolling = () => {
  if (sharePollTimer !== null) clearTimeout(sharePollTimer)
  sharePollTimer = null
}
const startSharePolling = (interval: number, dialog: number, authorization: number) => {
  stopSharePolling()
  const current = () => currentDialog(dialog) && authorization === authVersion
  if (!current()) return
  sharePollTimer = setTimeout(
    async () => {
      sharePollTimer = null
      if (!current()) return
      const status = await pollShareAuth()
      if (!current()) return
      if (!status) {
        startSharePolling(interval, dialog, authorization)
        return
      }
      shareAuth.value = status
      if (status.status === 'pending')
        startSharePolling(status.interval || interval, dialog, authorization)
      else if (status.status === 'authorized')
        message.success(t('edit.share.authorized', { name: status.displayName || status.username }))
    },
    Math.max(interval, 1) * 1000
  )
}
const refreshShareRisks = async (name: string, dialog: number): Promise<boolean> => {
  const request = ++riskVersion
  const risks = await inspectShare(scriptId, name || '未命名配置')
  if (!currentDialog(dialog) || request !== riskVersion || name !== uploadForm.config_name)
    return false
  if (risks === null) {
    logger.warn(`分享前检查失败: ${shareError.value ?? ''}`)
    return false
  }
  const knownFields = new Set(shareRisks.value.map(risk => risk.field))
  if (risks.some(risk => !knownFields.has(risk.field))) riskAcknowledged.value = false
  shareRisks.value = risks
  return true
}
const showUploadModal = async () => {
  dialogOpen = true
  const dialog = ++dialogVersion
  const authorization = ++authVersion
  stopSharePolling()
  uploadModalVisible.value = true
  uploadLoading.value = false
  dialogLoading.value = true
  shareAuthLoading.value = false
  if (!uploadForm.config_name) uploadForm.config_name = props.scriptName || ''
  // 开启新弹窗前完成上次撤销，避免迟到的撤销把新授权一并取消。
  try {
    await waitForGeneralShareAuth()
    if (!currentDialog(dialog)) return
    const status = await getShareAuthStatus()
    if (!currentDialog(dialog) || authorization !== authVersion) return
    if (status) shareAuth.value = status
    if (status?.status === 'pending') startSharePolling(status.interval, dialog, authorization)
    await refreshShareRisks(uploadForm.config_name, dialog)
  } finally {
    if (dialog === dialogVersion) dialogLoading.value = false
  }
}
const closeUploadModal = async () => {
  if (!dialogOpen) return
  dialogOpen = false
  uploadModalVisible.value = false
  dialogVersion++
  authVersion++
  riskVersion++
  stopSharePolling()
  // cancel 仅撤销等待中的设备授权，不登出已授权账号；状态读取未完成也要清理。
  await queueAuthAction(() => cancelShareAuth())
}
const handleUploadCancel = () => closeUploadModal()
const openShareVerificationPage = () => {
  const uri = shareAuth.value.verificationUri
  if (/^https?:\/\//i.test(uri)) {
    openExternalUrl(uri)
    return
  }
  if (uri) logger.warn(`配置中心返回了无法打开的授权地址: ${uri}`)
}
const handleStartShareAuth = async () => {
  if (
    !uploadModalVisible.value ||
    dialogLoading.value ||
    uploadLoading.value ||
    shareAuthLoading.value
  )
    return
  const dialog = dialogVersion
  const authorization = ++authVersion
  const current = () => currentDialog(dialog) && authorization === authVersion
  stopSharePolling()
  shareAuthLoading.value = true
  try {
    await queueAuthAction(async () => {
      const status = await startShareAuth()
      if (!current()) return
      if (!status) {
        message.error(shareError.value ?? t('edit.share.startFailed'))
        return
      }
      shareAuth.value = status
      openShareVerificationPage()
      if (status.status === 'pending') startSharePolling(status.interval, dialog, authorization)
    })
  } finally {
    if (current()) shareAuthLoading.value = false
  }
}
const handleCancelShareAuth = async () => {
  const dialog = dialogVersion
  const authorization = ++authVersion
  stopSharePolling()
  const status = await queueAuthAction(() => cancelShareAuth())
  if (currentDialog(dialog) && authorization === authVersion) {
    shareAuth.value = status ?? { ...IDLE_SHARE_AUTH }
    shareAuthLoading.value = false
  }
}
const handleUpload = async () => {
  if (
    !uploadModalVisible.value ||
    dialogLoading.value ||
    shareAuthLoading.value ||
    uploadLoading.value
  )
    return
  const dialog = dialogVersion
  const snapshot = { configName: uploadForm.config_name, description: uploadForm.description }
  const authorization = authVersion
  const current = () =>
    currentDialog(dialog) &&
    !shareAuthLoading.value &&
    authorization === authVersion &&
    snapshot.configName === uploadForm.config_name &&
    snapshot.description === uploadForm.description
  uploadLoading.value = true
  try {
    try {
      await uploadFormRef.value?.validate()
    } catch {
      return
    }
    if (!current()) return
    if (shareAuth.value.status !== 'authorized') {
      message.warning(t('edit.share.loginRequired'))
      return
    }
    if (!(await refreshShareRisks(snapshot.configName, dialog))) {
      if (current()) message.error(shareError.value ?? t('edit.uploadFailedCheckYour'))
      return
    }
    if (!current()) return
    if (shareRisks.value.length > 0 && !riskAcknowledged.value) {
      message.warning(t('edit.share.riskConfirm'))
      return
    }
    const uploaded = await uploadShare({
      scriptId,
      ...snapshot,
      acknowledged: riskAcknowledged.value,
    })
    if (!currentDialog(dialog)) return
    if (!uploaded) {
      const errorMsg = shareError.value ?? t('edit.uploadFailedCheckYour')
      logger.error(`上传失败: ${errorMsg}`)
      message.error(errorMsg)
      const authorization = authVersion
      const status = await getShareAuthStatus()
      if (currentDialog(dialog) && authorization === authVersion && status) shareAuth.value = status
      return
    }
    message.success(t('edit.configurationUploadedItWill'))
    if (current()) {
      dialogOpen = false
      uploadModalVisible.value = false
      dialogVersion++
      stopSharePolling()
      uploadForm.config_name = ''
      uploadForm.description = ''
      shareRisks.value = []
      riskAcknowledged.value = false
    }
  } finally {
    if (dialog === dialogVersion) uploadLoading.value = false
  }
}
onUnmounted(() => {
  alive = false
  void closeUploadModal()
})
</script>
<template>
  <a-button size="large" type="primary" class="upload-button" @click="showUploadModal">
    <template #icon>
      <CloudUploadOutlined />
    </template>
    {{ t('edit.shareThisConfigurationConfig') }}
  </a-button>
  <!-- 上传脚本弹窗 -->
  <a-modal
    v-model:open="uploadModalVisible"
    :title="t('edit.uploadThisScriptConfiguration')"
    :confirm-loading="uploadLoading || dialogLoading || shareAuthLoading"
    width="600px"
    :mask-closable="false"
    @ok="handleUpload"
    @cancel="handleUploadCancel"
  >
    <a-form
      ref="uploadFormRef"
      :model="uploadForm"
      :rules="uploadRules"
      layout="vertical"
      class="upload-form"
    >
      <a-form-item name="config_name" :label="t('edit.configurationName')">
        <a-input
          v-model:value="uploadForm.config_name"
          :placeholder="t('edit.giveYourScriptConfiguration')"
          size="large"
          :maxlength="50"
          show-count
          class="modern-input"
        />
      </a-form-item>

      <a-form-item name="description" :label="t('edit.description')">
        <a-textarea
          v-model:value="uploadForm.description"
          :placeholder="t('edit.brieflyDescribeWhatThis')"
          size="large"
          :rows="4"
          :maxlength="200"
          show-count
          class="modern-textarea"
        />
      </a-form-item>

      <a-alert
        v-if="shareAuth.status === 'authorized'"
        type="success"
        show-icon
        class="share-auth-alert"
        :message="t('edit.share.signedInAs', { name: shareAuth.displayName || shareAuth.username })"
      >
        <template #description>
          <div class="share-auth-idle">
            <p>{{ t('edit.share.signedInDesc') }}</p>
            <a-button size="small" :loading="shareAuthLoading" @click="handleStartShareAuth">{{
              t('edit.share.switchAccount')
            }}</a-button>
          </div>
        </template>
      </a-alert>
      <a-alert
        v-else
        type="warning"
        show-icon
        class="share-auth-alert"
        :message="t('edit.share.loginRequired')"
      >
        <template #description>
          <div v-if="shareAuth.status === 'pending'" class="share-auth-pending">
            <p>{{ t('edit.share.pendingDesc') }}</p>
            <p class="share-user-code">{{ shareAuth.userCode }}</p>
            <a-space>
              <a-button size="small" @click="openShareVerificationPage">{{
                t('edit.share.reopenBrowser')
              }}</a-button>
              <a-button size="small" @click="handleCancelShareAuth">{{
                t('edit.share.cancelAuth')
              }}</a-button>
            </a-space>
          </div>
          <div v-else class="share-auth-idle">
            <p>{{ shareAuth.message || t('edit.share.loginRequiredDesc') }}</p>
            <a-button
              type="primary"
              size="small"
              :loading="shareAuthLoading"
              @click="handleStartShareAuth"
              >{{ t('edit.share.startLogin') }}</a-button
            >
          </div>
        </template>
      </a-alert>

      <a-alert
        v-if="shareRisks.length"
        type="warning"
        show-icon
        class="share-risk-alert"
        :message="t('edit.share.riskTitle')"
      >
        <template #description>
          <ul class="share-risk-list">
            <li v-for="risk in shareRisks" :key="risk.field">
              <code>{{ risk.field }}</code> — {{ risk.reason }}
            </li>
          </ul>
          <a-checkbox v-model:checked="riskAcknowledged">{{
            t('edit.share.riskConfirm')
          }}</a-checkbox>
        </template>
      </a-alert>

      <a-alert :message="t('edit.aboutSharing')" type="info">
        <template #description>
          <p>{{ t('edit.share.privacyNotice') }}</p>
        </template>
      </a-alert>
    </a-form>
  </a-modal>
</template>
<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>
<style scoped>
/* 分享弹窗 */
.share-auth-alert,
.share-risk-alert {
  margin-bottom: 12px;
}

.share-auth-pending p,
.share-auth-idle p {
  margin: 0 0 8px;
}

.share-user-code {
  font-family: var(--ant-font-family-code, monospace);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 3px;
}

.share-risk-list {
  margin: 0 0 8px;
  padding-left: 18px;
}
</style>
