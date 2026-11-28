<template>
  <UserEditShell
    :max-width="1200"
    script-type="BAAH"
    :script-id="scriptId"
    :script-name="scriptName"
    :is-edit="isEdit"
    :user-id="userId"
    :user-name="formData.userName"
    @cancel="handleCancel"
  >
    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <UserAccountHeading
          :user-name="formData.userName"
          :options="{ isEdit, logoSrc: accountIcon }"
        />
        <SectionCard variant="plain" :title="t('core.edit.basicInfo')">
          <template #actions>
            <a-button size="small" @click="restoreOpen = true">
              <template #icon><HistoryOutlined /></template>
              {{ t('core.edit.configRestoreTitle') }}
            </a-button>
          </template>
          <UserBasicInfoFields
            v-model:user-name="formData.userName"
            v-model:status="formData.Info.Status"
            v-model:remained-day="formData.Info.RemainedDay"
            v-model:notes="formData.Info.Notes"
            :disabled="loading"
            @save-name="handleFieldSave('userName', formData.userName)"
            @save-status="handleFieldSave('Info.Status', formData.Info.Status)"
            @save-days="handleFieldSave('Info.RemainedDay', formData.Info.RemainedDay)"
            @save-notes="handleFieldSave('Info.Notes', formData.Info.Notes)"
          />
        </SectionCard>

        <SectionCard variant="plain">
          <BAAHConfigSelector
            v-model="formData.Info.ConfigName"
            :script-id="scriptId"
            :disabled="loading || isInitializing || configLocked"
            :save-selection="name => handleFieldSave('Info.ConfigName', name)"
          />

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahUserTag')"
                    :hint="t('core.edit.baahUserTagHint')"
                    variant="form"
                  />
                </template>
                <div class="user-tag-list">
                  <a-tag
                    v-for="(tag, index) in userTags"
                    :key="index"
                    :title="tag.text"
                    :color="tag.color"
                  >
                    {{ tag.text }}
                  </a-tag>
                </div>
              </a-form-item>
            </a-col>
          </a-row>

          <a-alert type="info" show-icon :message="t('core.edit.baahConfigSourceHint')" />
        </SectionCard>

        <!-- 数据统计（只读，由本软件自动写入） -->
        <SectionCard variant="plain" :title="t('core.edit.statistics')">
          <a-row :gutter="24">
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahLastProxyDate')"
                    :hint="t('core.edit.baahDataReadOnlyHint')"
                    variant="form"
                  />
                </template>
                <a-input
                  :value="formatConfigDate(formData.Data.LastProxyDate, 4 * 60)"
                  readonly
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahProxyTimes')"
                    :hint="t('core.edit.baahDataReadOnlyHint')"
                    variant="form"
                  />
                </template>
                <a-input :value="formData.Data.ProxyTimes" readonly size="large" />
              </a-form-item>
            </a-col>
          </a-row>
        </SectionCard>

        <UserNotifyConfig v-model="formData.Notify" :loading="loading" @save="handleFieldSave" />

        <SectionCard variant="plain" :title="t('core.edit.baahCalendarReminder')">
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.baahActivityLineType')"
                    :hint="t('core.edit.baahActivityLineTypeHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="formData.Info.ActivityLineType"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                  @change="handleFieldSave('Info.ActivityLineType', formData.Info.ActivityLineType)"
                >
                  <a-select-option value="CN">{{
                    t('core.edit.baahActivityLineCN')
                  }}</a-select-option>
                  <a-select-option value="JP">{{
                    t('core.edit.baahActivityLineJP')
                  }}</a-select-option>
                  <a-select-option value="Globle">{{
                    t('core.edit.baahActivityLineGloble')
                  }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </SectionCard>
      </a-form>
    </ConfigLockPanel>

    <template #overlay>
      <!-- ══ 配置恢复（通用组件：MAS 用户字段在前、BAAH 原生配置在后）══ -->
      <ConfigRestoreSection
        v-model:open="restoreOpen"
        :disabled="configLocked"
        :script-name="BAAH_DISPLAY_NAME"
        :targets="restoreTargets"
        :api="restoreApi"
        :user-desc="t('core.edit.baahConfigRestoreUserDesc')"
        :script-desc="t('core.edit.baahConfigRestoreScriptDesc')"
        :on-restored="handleRestored"
      >
        <!-- mas 备份为字段侧车分区、native 备份为关键字段反读分区 -->
        <template #preview="{ raw }">
          <NoData
            v-if="!previewSections(raw).length"
            :description="t('core.edit.configRestorePreviewEmpty')"
          />
          <div v-else>
            <template v-for="s in previewSections(raw)" :key="s.name">
              <h4 class="baah-preview-title">{{ s.label }}</h4>
              <a-descriptions
                v-if="s.rows && s.rows.length"
                :column="1"
                size="small"
                bordered
                class="baah-preview-box"
              >
                <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
                  {{ row.value }}
                </a-descriptions-item>
              </a-descriptions>
              <div
                v-for="g in s.groups ?? []"
                :key="`${s.name}-${g.name}`"
                class="baah-preview-group"
              >
                <div class="baah-preview-group-name">{{ g.name }}</div>
                <a-descriptions :column="1" size="small" bordered class="baah-preview-box">
                  <a-descriptions-item v-for="row in g.rows" :key="row.key" :label="row.key">
                    {{ row.value }}
                  </a-descriptions-item>
                </a-descriptions>
              </div>
            </template>
          </div>
        </template>
      </ConfigRestoreSection>
    </template>
  </UserEditShell>
</template>

<script setup lang="ts">
import UserEditShell from '@/components/UserEditShell.vue'
import { SectionCard } from '@/components/ui'
import UserAccountHeading from '@/components/UserAccountHeading.vue'
import accountIcon from '@/assets/baah.png'
import UserBasicInfoFields from '@/components/UserBasicInfoFields.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { formatConfigDate } from '@/utils/configDateTime'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { HistoryOutlined } from '@ant-design/icons-vue'
import type { Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { buildFieldPatch } from '@/utils/fieldPatch'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { parseStatusTagList } from '@/composables/useStatusTag.ts'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import BAAHConfigSelector from './components/BAAHConfigSelector.vue'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'
import { useSaveQueue } from '@/composables/useSaveQueue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('BAAH用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading, error: userApiError } = useUserApi()
const { getScript, error: scriptApiError } = useScriptApi()

const isInitializing = ref(true) // 标记是否正在初始化

// 路由参数
const scriptId = route.params.scriptId as string

let userId = route.params.userId as string
const { enqueue: enqueueSave } = useSaveQueue()
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新
const { configLocked } = useScriptConfigLock(() => ({ scriptId, userId }))

// 脚本信息
const scriptName = ref('')

// BAAH 用户默认数据（与后端 BAAHUserConfig 的默认值保持一致）
const getDefaultBAAHUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    ConfigName: '',
    ActivityLineType: 'CN',
    Notes: '',
    Tag: '',
  },
  Data: {
    LastProxyDate: '2000-01-01T00:00:00+04:00',
    ProxyTimes: 0,
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  // 嵌套的实际数据
  ...getDefaultBAAHUserData(),
})

// 只读标签：后端按运行情况生成的 JSON 字符串
const userTags = computed(() => parseStatusTagList(formData.Info.Tag))

// 表单验证规则
const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: t('core.edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('core.edit.usernameMustBe1'), trigger: 'blur' },
    ],
  }
  return baseRules
})

// 同步扁平化字段与嵌套数据
watch(
  () => formData.Info.Name,
  newVal => {
    if (formData.userName !== newVal) {
      formData.userName = newVal || ''
    }
  },
  { immediate: true }
)

watch(
  () => formData.userName,
  newVal => {
    if (formData.Info.Name !== newVal) {
      formData.Info.Name = newVal || ''
    }
  }
)

// 即时保存单个字段变更（经实体串行队列按序落盘，不丢并发修改）
const handleFieldSave = (key: string, value: any): Promise<boolean> => {
  if (isInitializing.value || !userId) return Promise.resolve(false)
  return enqueueSave(async () => {
    try {
      const userData = key === 'userName' ? { Info: { Name: value } } : buildFieldPatch(key, value)
      if (!(await updateUser(scriptId, userId, userData))) return false
      logger.info(`用户配置已保存: ${key}`)
      return true
    } catch (error) {
      logger.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`)
      return false
    }
  }, key)
}

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      // 如果是编辑模式，加载用户数据
      if (isEdit.value) {
        await loadUserData()
      } else {
        // 新增模式：立即创建用户获取 ID
        await createUserImmediately()
      }
    } else {
      if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist2'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript2'))
  }
}

// 新增模式下立即创建用户
const createUserImmediately = async () => {
  if (configLocked.value) return false

  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      // 更新路由，但不刷新页面
      router.replace({
        name: route.name || undefined,
        params: { ...route.params, userId: result.userId },
      })
      logger.info(`用户已创建，ID: ${result.userId}`)
      // 加载新创建用户的数据
      await loadUserData()
    } else {
      if (!userApiError.value) message.error(t('core.edit.couldNotCreateUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建用户失败: ${errorMsg}`)
    if (!userApiError.value) message.error(t('core.edit.couldNotCreateUser'))
    handleCancel()
  }
}

// 加载用户数据
const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      // 查找指定的用户数据
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        // 填充 BAAH 用户数据
        if (userIndex.type === 'BAAHUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultBAAHUserData().Info, ...userData.Info },
            Notify: { ...getDefaultBAAHUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultBAAHUserData().Data, ...userData.Data },
          })
        }

        // 同步扁平化字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''

        logger.info('用户数据加载成功')

        // 数据加载完成，允许自动保存
        isInitializing.value = false
      } else {
        message.error(t('core.edit.userDoesNotExist'))
        handleCancel()
      }
    } else {
      if (!userApiError.value) message.error(t('core.edit.couldNotFetchUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    if (!userApiError.value) message.error(t('core.edit.couldNotLoadUser2'))
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：BAAH 统一叫「baah」
const BAAH_DISPLAY_NAME = 'baah'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户字段（在前）、BAAH 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const { restoreApi, ensureBackup } = useConfigBackupApi({
  scriptId,
  userId: () => userId,
  logger,
})

// 预览响应原文（unknown）收敛为分区视图：泛用组件的 raw 插槽不带专项类型
interface BAAHPreviewRow {
  key: string
  value: string
}
interface BAAHPreviewSection {
  name: string
  label: string
  rows?: BAAHPreviewRow[]
  groups?: Array<{ name: string; rows: BAAHPreviewRow[] }>
}
const previewSections = (raw: unknown): BAAHPreviewSection[] =>
  (raw as { sections?: BAAHPreviewSection[] } | null)?.sections ?? []

// 一键恢复成功：mas 恢复回填字段（当前仅 ConfigName），native 恢复写
// BAAH 配置文件——ConfigName 未变无需刷新表单
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    isInitializing.value = true
    try {
      await loadUserData()
    } finally {
      // 加载失败也要复位：否则按钮永久转圈
      isInitializing.value = false
    }
  }
}

// 编辑界面归档（进入/退出时机，指纹去重）：进入归档 BAAH 原生配置当前状态
// （用户可能刚在 BAAH jsoneditor 里改过），退出归档 MAS 编辑页字段终态；
// 运行前归档挂在 AutoProxy.prepare（托管写入前）
const ensureBAAHBackup = ensureBackup

onMounted(async () => {
  if (!scriptId) {
    message.error(t('core.edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  // 先等脚本信息与用户就绪（新建模式内部会创建用户并写入 userId）再归档，
  // 否则新建用户首次进入会因 userId 未就绪静默跳过归档
  await loadScriptInfo()
  await nextTick()
  void ensureBAAHBackup('native')
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 编辑页字段终态（BAAH 无遮罩会话，无需停会话）
  void ensureBAAHBackup('mas')
})
</script>

<style scoped>
/* ══ 配置恢复预览（分区标题 + 表格 + 详情分组）══ */
.baah-preview-title {
  margin: 16px 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.baah-preview-title:first-of-type {
  margin-top: 0;
}

.baah-preview-group {
  margin-top: 12px;
}

.baah-preview-group-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  margin-bottom: 4px;
}

.baah-preview-box {
  width: 100%;
}

.user-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
}
</style>
