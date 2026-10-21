<script setup lang="ts">
import { onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, type FormInstance } from 'ant-design-vue'
import { CloudUploadOutlined } from '@ant-design/icons-vue'
import { openExternalUrl } from '@/utils/openExternal'
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
// 上传脚本配置相关
const uploadModalVisible = ref(false)
const uploadLoading = ref(false)
const shareAuthLoading = ref(false)
const shareAuth = ref<ShareAuthState>({ ...IDLE_SHARE_AUTH })
const shareRisks = ref<ShareRiskItem[]>([])
const riskAcknowledged = ref(false)
let sharePollTimer: ReturnType<typeof setTimeout> | null = null

const uploadForm = reactive({
  config_name: '',
  description: '',
})

// 上传表单验证规则
const uploadRules = {
  config_name: [{ required: true, message: t('edit.enterConfigurationName'), trigger: 'blur' }],
  description: [{ required: true, message: t('edit.enterDescription'), trigger: 'blur' }],
}

// 显示上传弹窗：带出当前脚本名称，并同步一次配置中心授权状态与隐私检查
const showUploadModal = async () => {
  uploadModalVisible.value = true
  if (!uploadForm.config_name) {
    uploadForm.config_name = props.scriptName || ''
  }

  const status = await getShareAuthStatus()
  if (status) shareAuth.value = status
  if (status?.status === 'pending') startSharePolling(status.interval)

  await refreshShareRisks()
}

// 隐藏上传弹窗：停止轮询，并撤销尚未完成的授权等待
const handleUploadCancel = async () => {
  uploadModalVisible.value = false
  stopSharePolling()
  if (shareAuth.value.status === 'pending') {
    const status = await cancelShareAuth()
    if (status) shareAuth.value = status
  }
}

const refreshShareRisks = async () => {
  const risks = await inspectShare(scriptId, uploadForm.config_name || '未命名配置')
  if (risks === null) {
    logger.warn(`分享前检查失败: ${shareError.value ?? ''}`)
    return
  }
  const knownFields = new Set(shareRisks.value.map(risk => risk.field))
  const hasNewRisk = risks.some(risk => !knownFields.has(risk.field))
  shareRisks.value = risks
  // 只有冒出新的风险项才要求重新确认；风险变少不该把用户刚勾的框清掉
  if (hasNewRisk) riskAcknowledged.value = false
}

const stopSharePolling = () => {
  if (sharePollTimer !== null) {
    clearTimeout(sharePollTimer)
    sharePollTimer = null
  }
}

// 按配置中心给的间隔轮询授权结果，弹窗关闭或拿到终态就停
const startSharePolling = (interval: number) => {
  stopSharePolling()
  sharePollTimer = setTimeout(
    async () => {
      sharePollTimer = null
      if (!uploadModalVisible.value) return

      const status = await pollShareAuth()
      if (!status) {
        startSharePolling(interval)
        return
      }

      shareAuth.value = status
      if (status.status === 'pending') {
        startSharePolling(status.interval || interval)
        return
      }
      if (status.status === 'authorized') {
        message.success(t('edit.share.authorized', { name: status.displayName || status.username }))
      }
    },
    Math.max(interval, 1) * 1000
  )
}

const openShareVerificationPage = () => {
  const uri = shareAuth.value.verificationUri
  // 地址由配置中心下发，只放行普通网页链接
  if (/^https?:\/\//i.test(uri)) {
    openExternalUrl(uri)
    return
  }
  if (uri) logger.warn(`配置中心返回了无法打开的授权地址: ${uri}`)
}

const handleStartShareAuth = async () => {
  shareAuthLoading.value = true
  try {
    const status = await startShareAuth()
    if (!status) {
      message.error(shareError.value ?? t('edit.share.startFailed'))
      return
    }
    shareAuth.value = status
    openShareVerificationPage()
    startSharePolling(status.interval)
  } finally {
    shareAuthLoading.value = false
  }
}

const handleCancelShareAuth = async () => {
  stopSharePolling()
  const status = await cancelShareAuth()
  shareAuth.value = status ?? { ...IDLE_SHARE_AUTH }
}

// 处理上传脚本配置
const handleUpload = async () => {
  try {
    await uploadFormRef.value?.validate()
  } catch {
    return
  }

  if (shareAuth.value.status !== 'authorized') {
    message.warning(t('edit.share.loginRequired'))
    return
  }

  // 配置名会写进 Info.Name 并参与隐私检查，按提交时的名字重新查一遍
  await refreshShareRisks()
  if (shareRisks.value.length > 0 && !riskAcknowledged.value) {
    message.warning(t('edit.share.riskConfirm'))
    return
  }

  uploadLoading.value = true
  try {
    const uploaded = await uploadShare({
      scriptId,
      configName: uploadForm.config_name,
      description: uploadForm.description,
      acknowledged: riskAcknowledged.value,
    })

    if (!uploaded) {
      const errorMsg = shareError.value ?? t('edit.uploadFailedCheckYour')
      logger.error(`上传失败: ${errorMsg}`)
      message.error(errorMsg)
      // 令牌可能已过期，重新同步一次授权状态，让用户知道要重新登录
      const status = await getShareAuthStatus()
      if (status) shareAuth.value = status
      return
    }

    message.success(t('edit.configurationUploadedItWill'))
    uploadModalVisible.value = false
    uploadForm.config_name = ''
    uploadForm.description = ''
    shareRisks.value = []
    riskAcknowledged.value = false
  } finally {
    uploadLoading.value = false
  }
}

onUnmounted(stopSharePolling)
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
    :confirm-loading="uploadLoading"
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
