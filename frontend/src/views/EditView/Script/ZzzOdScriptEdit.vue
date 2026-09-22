<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/zzz-od.ico" alt="ZZZ-OD" class="breadcrumb-logo" />
            {{ t('edit.editScript') }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card :title="t('edit.zzzodScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag">ZZZ-OD</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.scriptName') }}
                    <a-tooltip :title="t('edit.zzzodScriptNameHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('edit.enterScriptName')"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodRootPath') }}
                    <a-tooltip :title="t('edit.zzzodRootPathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.zzzodRootPathPlaceholder')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isSaving"
                    @click="selectRootPath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickDirectory') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.gameConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.enableGameConfiguration') }}
                    <a-tooltip :title="t('edit.masTakesOverStarting')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.Enabled"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'Enabled', zzzodConfig.Game.Enabled)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchGameBeforeTask') }}
                    <a-tooltip :title="t('edit.zzzodLaunchBeforeTaskHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.LaunchBeforeTask"
                  size="large"
                  style="width: 100%"
                  :disabled="!zzzodConfig.Game.Enabled"
                  @change="
                    handleChange('Game', 'LaunchBeforeTask', zzzodConfig.Game.LaunchBeforeTask)
                  "
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodGamePath') }}
                    <a-tooltip :title="t('edit.zzzodGamePathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="zzzodConfig.Game.Path"
                    :placeholder="t('edit.zzzodGamePathPlaceholder')"
                    size="large"
                    class="path-input"
                    readonly
                    :disabled="!zzzodConfig.Game.Enabled"
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="!zzzodConfig.Game.Enabled || isSaving"
                    @click="selectGamePath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFile') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchArguments') }}
                    <a-tooltip :title="t('edit.zzzodGameArgumentsHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="zzzodConfig.Game.Arguments"
                  :placeholder="t('edit.enterGameLaunchArguments')"
                  size="large"
                  style="width: 100%"
                  :disabled="!zzzodConfig.Game.Enabled"
                  @blur="handleChange('Game', 'Arguments', zzzodConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.startupWait') }}
                    <a-tooltip :title="t('edit.howLongWaitAfter')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  :disabled="!zzzodConfig.Game.Enabled"
                  @blur="handleChange('Game', 'WaitTime', zzzodConfig.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodCloseGameOnFinish') }}
                    <a-tooltip :title="t('edit.zzzodCloseGameOnFinishHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.CloseOnFinish"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'CloseOnFinish', zzzodConfig.Game.CloseOnFinish)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodAccountSwitch') }}
                    <a-tooltip :title="t('edit.zzzodAccountSwitchHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.AccountSwitch"
                  :options="accountSwitchOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'AccountSwitch', zzzodConfig.Game.AccountSwitch)"
                >
                  <!-- 逐选项悬停提示：鼠标停在哪个选项上就显示哪个的说明 -->
                  <template #option="{ label, hint }">
                    <a-tooltip :title="hint" placement="right" :mouse-enter-delay="0.3">
                      <div class="account-switch-option">{{ label }}</div>
                    </a-tooltip>
                  </template>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runsPerDay') }}
                    <a-tooltip :title="t('edit.k0MeansNoLimit')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', zzzodConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.zzzodRetryLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', zzzodConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.zzzodRunTimeoutHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', zzzodConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 实例槽管理：脚本级诊断（槽目录按安装目录归池、跨脚本共享），默认折叠 -->
        <div class="form-section">
          <a-collapse
            v-model:activeKey="slotPanelKeys"
            ghost
            class="slot-manage"
            @change="handleSlotPanelChange"
          >
            <a-collapse-panel key="slots">
              <template #header>
                <h3 class="slot-manage-title">
                  {{ t('edit.zzzodSlotsManage') }}
                  <a-tooltip :title="t('edit.zzzodSlotsManageHint')">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </h3>
              </template>
              <div class="slot-manage-actions">
                <a-space :size="8">
                  <a-button size="small" :loading="slotsLoading" @click="loadSlotView">
                    <template #icon><ReloadOutlined /></template>
                    {{ t('edit.zzzodSlotsRefresh') }}
                  </a-button>
                  <a-button
                    size="small"
                    danger
                    :loading="slotsLoading"
                    @click="confirmCleanOrphanSlots"
                  >
                    <template #icon><ClearOutlined /></template>
                    {{ t('edit.zzzodSlotsClean') }}
                  </a-button>
                </a-space>
              </div>
              <a-tabs v-model:activeKey="slotTab" size="small">
                <a-tab-pane key="slots" :tab="t('edit.zzzodSlotTabSlots')">
                  <a-table
                    size="small"
                    row-key="idx"
                    :columns="slotColumns"
                    :data-source="slots"
                    :loading="slotsLoading"
                    :pagination="false"
                    :locale="{ emptyText: t('edit.zzzodSlotEmpty') }"
                  >
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === 'idx'">
                        {{ String(record.idx).padStart(2, '0') }}
                      </template>
                      <template v-else-if="column.key === 'kind'">
                        <a-tag :color="slotKindColor(record.kind)">
                          {{ slotKindLabel(record.kind) }}
                        </a-tag>
                        <a-tooltip
                          v-if="slotNativeConflict(record)"
                          :title="t('edit.zzzodSlotNativeConflictHint')"
                        >
                          <a-tag color="warning" class="slot-conflict-tag">
                            {{ t('edit.zzzodSlotNativeConflict') }}
                          </a-tag>
                        </a-tooltip>
                      </template>
                      <template v-else-if="column.key === 'owner'">
                        {{ slotOwnerText(record) }}
                      </template>
                      <template v-else-if="column.key === 'dir'">
                        {{
                          record.has_dir ? t('edit.zzzodSlotHasDir') : t('edit.zzzodSlotNoDir')
                        }}
                      </template>
                      <template v-else-if="column.key === 'size'">
                        {{ formatSlotSize(record.size) }}
                      </template>
                    </template>
                  </a-table>
                </a-tab-pane>
                <a-tab-pane key="recycle" :tab="recycleTabLabel">
                  <div class="slot-manage-hint-row">
                    <a-typography-text type="secondary" class="slot-manage-hint">
                      {{ t('edit.zzzodRecycleHint') }}
                    </a-typography-text>
                    <a-button
                      size="small"
                      danger
                      :loading="recycleLoading"
                      :disabled="!recycleRows.length"
                      @click="confirmClearRecycle"
                    >
                      <template #icon><ClearOutlined /></template>
                      {{ t('edit.zzzodRecycleClear') }}
                    </a-button>
                  </div>
                  <a-table
                    size="small"
                    row-key="key"
                    :columns="recycleColumns"
                    :data-source="recycleRows"
                    :loading="recycleLoading"
                    :pagination="false"
                    :locale="{ emptyText: t('edit.zzzodRecycleEmpty') }"
                  >
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === 'slot'">
                        {{ String(record.slot).padStart(2, '0') }}
                      </template>
                      <template v-else-if="column.key === 'kind'">
                        {{ recycleKindLabel(record.kind) }}
                      </template>
                      <template v-else-if="column.key === 'ts'">
                        {{ formatArchiveTs(record.ts) }}
                      </template>
                      <template v-else-if="column.key === 'files'">
                        {{ record.files }}
                      </template>
                      <template v-else-if="column.key === 'size'">
                        {{ formatSlotSize(record.size) }}
                      </template>
                      <template v-else-if="column.key === 'ops'">
                        <a-space :size="4">
                          <a-button
                            size="small"
                            type="link"
                            @click="openRecycleFolder(record)"
                          >
                            {{ t('edit.zzzodRecycleOpen') }}
                          </a-button>
                          <a-button
                            v-if="record.kind === 'slot'"
                            size="small"
                            type="link"
                            @click="confirmRestoreRecycle(record)"
                          >
                            {{ t('edit.zzzodRecycleRestore') }}
                          </a-button>
                        </a-space>
                      </template>
                    </template>
                  </a-table>
                </a-tab-pane>
              </a-tabs>
            </a-collapse-panel>
          </a-collapse>
        </div>
      </a-form>
    </a-card>
  </ConfigLockPanel>

  <!-- 原槽被占用：强制覆盖（覆盖前自动存底）或换到其他空闲槽号 -->
  <a-modal
    v-model:open="restoreConflict.open"
    :title="t('edit.zzzodRecycleRestore')"
    :confirm-loading="restoring"
    :ok-text="t('edit.zzzodRecycleRestore')"
    :ok-button-props="{ danger: restoreConflict.mode === 'force' }"
    @ok="submitRestoreConflict"
  >
    <a-typography-paragraph type="warning">
      {{
        t('edit.zzzodRecycleRestoreConflict', {
          slot: String(restoreConflict.entry?.slot ?? 0).padStart(2, '0'),
          occupant: restoreConflict.entry
            ? slotOccupantText(restoreConflict.entry.slot)
            : '',
        })
      }}
    </a-typography-paragraph>
    <a-radio-group v-model:value="restoreConflict.mode" class="restore-mode">
      <a-radio value="force">
        {{
          t('edit.zzzodRecycleRestoreForceHint', {
            slot: String(restoreConflict.entry?.slot ?? 0).padStart(2, '0'),
          })
        }}
      </a-radio>
      <a-radio value="other" :disabled="!freeSlotOptions.length">
        {{ t('edit.zzzodRecycleRestoreOtherHint') }}
      </a-radio>
    </a-radio-group>
    <a-select
      v-if="restoreConflict.mode === 'other'"
      v-model:value="restoreConflict.targetSlot"
      class="restore-mode-target"
      :options="freeSlotOptions"
      :placeholder="t('edit.zzzodRecycleRestoreOtherPlaceholder')"
    />
  </a-modal>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  ClearOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { Service, type ZzzOdRecycleEntryOut, type ZzzOdSlotOut } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useSaveQueue } from '@/composables/useSaveQueue'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('ZZZ-OD脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()
const isInitializing = ref(true)

// ══ ZZZ-OD 项目结构常量（需与 app/task/ZzzOd/AutoProxy.py 的 _ZZZOD_LAUNCHERS 保持同步）══
const ZZZOD_LAUNCHER_NAMES = ['OneDragon-RuntimeLauncher.exe', 'OneDragon-Launcher.exe']

/** MAS 槽号段起点（需与 app/task/ZzzOd/tools/zzz_od_config.py 的 MAS_SLOT_BASE 保持同步）：
 *  恢复快照的候选目标只在这个号段里挑——低号段是一条龙「升序找最小空号」的地盘 */
const MAS_SLOT_BASE = 1001

interface ZzzOdInfoForm {
  Name: string
  RootPath: string
}

interface ZzzOdRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface ZzzOdGameForm {
  Enabled: boolean
  LaunchBeforeTask: boolean
  Path: string
  Arguments: string
  WaitTime: number
  CloseOnFinish: boolean
  AccountSwitch: '单实例切换' | '多实例切换' | 'MAS切换'
}

interface ZzzOdScriptConfigForm {
  Info: ZzzOdInfoForm
  Run: ZzzOdRunForm
  Game: ZzzOdGameForm
}

const formData = reactive({
  name: '',
  get path() {
    return zzzodConfig.Info.RootPath
  },
  set path(value: string) {
    zzzodConfig.Info.RootPath = value
  },
})

const zzzodConfig = reactive<ZzzOdScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 180 },
  Game: {
    Enabled: false,
    LaunchBeforeTask: false,
    Path: '',
    Arguments: '',
    WaitTime: 60,
    CloseOnFinish: true,
    AccountSwitch: '单实例切换',
  },
})

// 账号切换方式（value 为后端 Game.AccountSwitch 取值，驱动逻辑需保持原样；label 走词表）
// hint 为逐选项悬停提示（下拉里鼠标停在哪个选项就显示哪个的说明）
const accountSwitchOptions = [
  {
    label: t('edit.zzzodAccountSwitchSingle'),
    value: '单实例切换',
    hint: t('edit.zzzodAccountSwitchSingleHint'),
  },
  {
    label: t('edit.zzzodAccountSwitchMulti'),
    value: '多实例切换',
    hint: t('edit.zzzodAccountSwitchMultiHint'),
  },
  {
    label: t('edit.zzzodAccountSwitchMas'),
    value: 'MAS切换',
    hint: t('edit.zzzodAccountSwitchMasHint'),
    disabled: true,
  },
]

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.zzzodRootPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value) return
  await enqueue(async () => {
    try {
      const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
      const success = await updateScript(scriptId, updateData)
      if (success) {
        logger.info(`配置已保存: ${category}.${key}`)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      logger.error(msg)
    }
  }, `${category}.${key}`)
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('edit.pickScriptRootDirectory'))
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = zzzodConfig.Info.RootPath
  zzzodConfig.Info.RootPath = norm

  return enqueue(async () => {
    try {
      const success = await updateScript(scriptId, {
        Info: { RootPath: norm },
      })
      if (success) {
        message.success(t('edit.zzzodRootPathSaved'))
        return true
      }
      zzzodConfig.Info.RootPath = previousPath
      return false
    } catch (error) {
      zzzodConfig.Info.RootPath = previousPath
      throw error
    }
  })
}

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      message.error(t('edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'ZzzOd') {
      message.error(t('edit.zzzodNotZzzodScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<ZzzOdScriptConfigForm>
    Object.assign(zzzodConfig.Info, config.Info || {})
    Object.assign(zzzodConfig.Run, config.Run || {})
    Object.assign(zzzodConfig.Game, config.Game || {})
  } catch {
    message.error(t('edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectGamePath = async () => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'ZenlessZoneZero.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return
  const fileName = path.split(/[\\/]/).pop()
  if (fileName?.toLowerCase() !== 'zenlesszonezero.exe') {
    message.error(t('edit.zzzodPickGameExe'))
    return
  }
  const normalized = path.replace(/\\/g, '/')
  const previous = zzzodConfig.Game.Path
  zzzodConfig.Game.Path = normalized
  try {
    await handleChange('Game', 'Path', normalized)
  } catch (error) {
    zzzodConfig.Game.Path = previous
    throw error
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  // 任一启动器存在即视为有效安装目录（RuntimeLauncher / 旧安装器 Launcher）
  const launcherChecks = await Promise.all(
    ZZZOD_LAUNCHER_NAMES.map(name => window.electronAPI.fileExists(`${normalized}/${name}`))
  )
  if (!launcherChecks.some(Boolean)) {
    Modal.error({
      title: t('edit.zzzodInvalidDirectory'),
      content: t('edit.zzzodLauncherNotFound', {
        p0: ZZZOD_LAUNCHER_NAMES[0],
        p1: ZZZOD_LAUNCHER_NAMES[1],
      }),
      okText: t('edit.gotIt'),
    })
    return
  }
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

// ══ 实例槽管理（默认折叠，首次展开时才请求）══
// 槽目录是 MAS 分配在一条龙安装目录里的 config/{idx:02d}，一条龙注册表与 GUI
// 都看不到；这份对照表用于看清「槽目录数与用户数对不上」（绑定但没跑过的槽没有
// 目录），回收池则是被删用户/脚本留下的槽内容与备份池快照（可恢复到原槽号）
const slotPanelKeys = ref<string[]>([])
const slotLoaded = ref(false)
const slotTab = ref('slots')
const slots = ref<ZzzOdSlotOut[]>([])
const slotsLoading = ref(false)
const recycleRows = ref<Array<ZzzOdRecycleEntryOut & { key: string }>>([])
const recycleLoading = ref(false)

const slotColumns = computed(() => [
  { title: t('edit.zzzodSlotColIdx'), key: 'idx', width: 72 },
  { title: t('edit.zzzodSlotColKind'), key: 'kind', width: 210 },
  { title: t('edit.zzzodSlotColOwner'), key: 'owner' },
  { title: t('edit.zzzodSlotColDir'), key: 'dir', width: 80 },
  { title: t('edit.zzzodSlotColSize'), key: 'size', width: 96 },
])

const recycleColumns = computed(() => [
  { title: t('edit.zzzodRecycleColSlot'), key: 'slot', width: 72 },
  { title: t('edit.zzzodRecycleColKind'), key: 'kind', width: 100 },
  { title: t('edit.zzzodRecycleColTime'), key: 'ts', width: 170 },
  { title: t('edit.zzzodRecycleColFiles'), key: 'files', width: 72 },
  { title: t('edit.zzzodRecycleColSize'), key: 'size', width: 96 },
  { title: t('edit.zzzodRecycleColOps'), key: 'ops', width: 88 },
])

const recycleTabLabel = computed(() =>
  recycleRows.value.length
    ? `${t('edit.zzzodSlotTabRecycle')} (${recycleRows.value.length})`
    : t('edit.zzzodSlotTabRecycle')
)

const slotKindLabel = (kind: string) =>
  kind === 'native'
    ? t('edit.zzzodSlotKindNative')
    : kind === 'mas'
      ? t('edit.zzzodSlotKindMas')
      : t('edit.zzzodSlotKindOrphan')

const slotKindColor = (kind: string) =>
  kind === 'native' ? 'default' : kind === 'mas' ? 'processing' : 'warning'

/** 号被一条龙抢走：槽进了原生注册表，却仍有 MAS 用户绑着这个号。
 *  一条龙的「新增实例」只按自己的注册表找最小空号、不扫盘，会把 MAS 槽
 *  的号当成空号拿去用；MAS 侧下次运行会改绑到高位空闲槽并把残留存底 */
const slotNativeConflict = (slot: ZzzOdSlotOut) =>
  slot.kind === 'native' && Boolean(slot.owners?.length)

/** 用户的配置来源（Info.Mode：脚本/用户/直控）→ 展示文案 */
const slotOwnerModeLabel = (mode: string) =>
  mode === '脚本'
    ? t('edit.zzzodSlotOwnerModeScript')
    : mode === '直控'
      ? t('edit.zzzodSlotOwnerModeDirect')
      : t('edit.zzzodSlotOwnerModeUser')

const slotOwnerText = (slot: ZzzOdSlotOut) =>
  slot.owners?.length
    ? slot.owners
        .map(
          item =>
            `${item.userName}（${item.scriptName}·${slotOwnerModeLabel(item.mode)}）`
        )
        .join('、')
    : '—'

const recycleKindLabel = (kind: string) =>
  kind === 'mas' ? t('edit.zzzodRecycleKindMas') : t('edit.zzzodRecycleKindSlot')

const formatSlotSize = (size: number) =>
  size >= 1024 * 1024
    ? `${(size / 1024 / 1024).toFixed(1)} MB`
    : size >= 1024
      ? `${(size / 1024).toFixed(1)} KB`
      : `${size} B`

/** 归档时间戳（目录名 20260921-225131，同秒顺延为 20260921-225131-1）→
 *  2026-09-21 22:51:31（带同秒序号时末尾拼 .N） */
const formatArchiveTs = (ts: string) => {
  const time = `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`
  return ts.length > 15 ? `${time}.${ts.slice(16)}` : time
}

const loadSlots = async () => {
  slotsLoading.value = true
  try {
    const resp = await Service.getZzzodSlotsApiApiScriptsZzzodSlotsGet(scriptId)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodSlotsLoadFailed'))
    }
    slots.value = resp.data || []
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsLoadFailed'))
  } finally {
    slotsLoading.value = false
  }
}

const loadRecycle = async () => {
  recycleLoading.value = true
  try {
    const resp = await Service.getZzzodRecycleApiApiScriptsZzzodRecycleGet(scriptId)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodSlotsLoadFailed'))
    }
    recycleRows.value = (resp.data || []).map(item => ({
      ...item,
      key: `${item.slot}-${item.kind}-${item.ts}`,
    }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsLoadFailed'))
  } finally {
    recycleLoading.value = false
  }
}

/** 刷新实例槽与回收池（首次展开、清理/恢复后调用） */
const loadSlotView = async () => {
  await Promise.all([loadSlots(), loadRecycle()])
}

/** 折叠面板首次展开时才请求：非常用功能，不进页面首屏 */
const handleSlotPanelChange = (keys: string[] | string) => {
  const opened = Array.isArray(keys) ? keys.length > 0 : Boolean(keys)
  if (opened && !slotLoaded.value) {
    slotLoaded.value = true
    void loadSlotView()
  }
}

const cleanOrphanSlots = async () => {
  slotsLoading.value = true
  try {
    const resp = await Service.cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost({
      scriptId,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodSlotsCleanFailed'))
    }
    message.success(t('edit.zzzodSlotsCleanDone', { count: (resp.data || []).length }))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsCleanFailed'))
  } finally {
    slotsLoading.value = false
    await loadSlotView()
  }
}

/** 清理无主槽：内容会先归档到回收池，仍属破坏性操作，需二次确认 */
const confirmCleanOrphanSlots = () => {
  const count = slots.value.filter(item => item.kind === 'orphan' && item.has_dir).length
  if (!count) {
    message.info(t('edit.zzzodSlotsCleanNone'))
    return
  }
  Modal.confirm({
    title: t('edit.zzzodSlotsClean'),
    content: t('edit.zzzodSlotsCleanConfirm', { count }),
    okText: t('edit.zzzodSlotsClean'),
    okButtonProps: { danger: true },
    onOk: () => cleanOrphanSlots(),
  })
}

/** 在文件管理器里打开回收条目的归档目录（便于核对或手动找回文件） */
const openRecycleFolder = async (entry: ZzzOdRecycleEntryOut) => {
  try {
    if (!window.electronAPI?.openFile) return
    const result = await window.electronAPI.openFile(entry.path)
    if (result && !result.success) {
      message.error(result.error || t('edit.zzzodRecycleOpenFailed'))
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

const clearRecyclePool = async () => {
  recycleLoading.value = true
  try {
    const resp = await Service.clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost({
      scriptId,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodRecycleClearFailed'))
    }
    message.success(t('edit.zzzodRecycleClearDone', { count: resp.data ?? 0 }))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodRecycleClearFailed'))
  } finally {
    recycleLoading.value = false
    await loadSlotView()
  }
}

/** 清空回收池不可找回（恢复历史一并删除），需二次确认 */
const confirmClearRecycle = () => {
  const totalSize = recycleRows.value.reduce((sum, item) => sum + item.size, 0)
  Modal.confirm({
    title: t('edit.zzzodRecycleClear'),
    content: t('edit.zzzodRecycleClearConfirm', {
      count: recycleRows.value.length,
      size: formatSlotSize(totalSize),
    }),
    okText: t('edit.zzzodRecycleClear'),
    okButtonProps: { danger: true },
    onOk: () => clearRecyclePool(),
  })
}

const restoring = ref(false)

/** 目标槽是否被原生实例或 MAS 用户占用（与后端守卫同口径：孤儿槽视为空闲） */
const slotOccupied = (idx: number) => {
  const row = slots.value.find(item => item.idx === idx)
  return Boolean(row && row.kind !== 'orphan')
}

/** 占用者描述（原生实例或绑定该槽的用户），用于冲突提示点名 */
const slotOccupantText = (idx: number) => {
  const row = slots.value.find(item => item.idx === idx)
  if (!row) return ''
  return row.kind === 'native' ? t('edit.zzzodSlotKindNative') : slotOwnerText(row)
}

/** 恢复槽快照到目标槽号（覆盖性操作：后端先存底当前内容再替换） */
const restoreRecycle = async (
  entry: ZzzOdRecycleEntryOut,
  options: { targetSlot?: number; force?: boolean } = {}
) => {
  restoring.value = true
  const dest = options.targetSlot ?? entry.slot
  try {
    const resp = await Service.restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost({
      scriptId,
      slot: entry.slot,
      ts: entry.ts,
      targetSlot: options.targetSlot,
      force: options.force,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodRecycleRestoreFailed'))
    }
    message.success(
      t('edit.zzzodRecycleRestoreDone', { slot: String(dest).padStart(2, '0') })
    )
    return true
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodRecycleRestoreFailed'))
    return false
  } finally {
    restoring.value = false
    await loadSlotView()
  }
}

/** 原槽被占用时的两个去处：强制覆盖（先存底）或换到其他空闲槽号 */
const restoreConflict = reactive({
  open: false,
  entry: null as ZzzOdRecycleEntryOut | null,
  mode: 'force' as 'force' | 'other',
  targetSlot: undefined as number | undefined,
})

const freeSlotOptions = computed(() => {
  const occupied = new Set(
    slots.value.filter(item => item.kind !== 'orphan').map(item => item.idx)
  )
  // 可复用的无主残留 + 几个新空号，都只取 MAS 号段：低号段是一条龙
  // 「升序找最小空号」的地盘，把快照恢复进去迟早会被它抢走覆盖
  const free = new Set(
    slots.value
      .filter(item => item.kind === 'orphan' && item.idx >= MAS_SLOT_BASE)
      .map(item => item.idx)
  )
  let next = Math.max(MAS_SLOT_BASE, ...slots.value.map(item => item.idx + 1))
  while (free.size < 4) {
    if (!occupied.has(next)) free.add(next)
    next += 1
  }
  return [...free]
    .sort((a, b) => a - b)
    .map(idx => {
      const row = slots.value.find(item => item.idx === idx)
      const label = String(idx).padStart(2, '0')
      return {
        value: idx,
        label: row
          ? `${label}（${t('edit.zzzodSlotKindOrphan')}·${formatSlotSize(row.size ?? 0)}）`
          : `${label}（${t('edit.zzzodRecycleRestoreEmptySlot')}）`,
      }
    })
})

const submitRestoreConflict = async () => {
  const entry = restoreConflict.entry
  if (!entry) return
  const targetSlot = restoreConflict.mode === 'other' ? restoreConflict.targetSlot : undefined
  if (restoreConflict.mode === 'other' && !targetSlot) {
    message.warning(t('edit.zzzodRecycleRestoreOtherRequired'))
    return
  }
  const done = await restoreRecycle(entry, {
    targetSlot,
    force: restoreConflict.mode === 'force',
  })
  if (done) restoreConflict.open = false
}

/** 恢复确认文案按目标槽现场分三态：被占用 / 有内容（无主残留）/ 空槽。
 *  无主残留按设计视为空闲（可被恢复重新认领），但覆盖它仍是替换性操作，
 *  必须把「这里现在有东西」说清楚，不能与「空槽新建」混为一谈 */
const restoreConfirmContent = (slotIdx: number) => {
  const slot = String(slotIdx).padStart(2, '0')
  if (slotOccupied(slotIdx)) {
    return t('edit.zzzodRecycleRestoreConfirmOccupied', {
      slot,
      occupant: slotOccupantText(slotIdx),
    })
  }
  const row = slots.value.find(item => item.idx === slotIdx)
  return row
    ? t('edit.zzzodRecycleRestoreConfirmOverwrite', {
        slot,
        size: formatSlotSize(row.size ?? 0),
      })
    : t('edit.zzzodRecycleRestoreConfirmEmpty', { slot })
}

/** 恢复槽快照是覆盖性操作，需二次确认；原槽被占用时改为选择去处 */
const confirmRestoreRecycle = (entry: ZzzOdRecycleEntryOut) => {
  const occupied = slotOccupied(entry.slot)
  const overwrites = !occupied && slots.value.some(item => item.idx === entry.slot)
  Modal.confirm({
    title: t('edit.zzzodRecycleRestore'),
    content: restoreConfirmContent(entry.slot),
    okText: t('edit.zzzodRecycleRestore'),
    okButtonProps: { danger: overwrites },
    onOk: async () => {
      if (!occupied) {
        await restoreRecycle(entry)
        return
      }
      restoreConflict.entry = entry
      restoreConflict.mode = 'force'
      restoreConflict.targetSlot = undefined
      restoreConflict.open = true
    },
  })
}

onMounted(loadScript)
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
}

.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

/* 实例槽管理：折叠面板标题与其它 section 标题同节奏，展开区不套卡片 */
.slot-manage :deep(.ant-collapse-header) {
  padding: 0 0 8px;
  align-items: center;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.slot-manage :deep(.ant-collapse-content-box) {
  padding: 12px 0 0;
}

.slot-manage-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.slot-manage-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.slot-manage-hint {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
}

.slot-manage-hint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.slot-manage-hint-row .slot-manage-hint {
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
}

.restore-mode {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slot-conflict-tag {
  margin-left: 4px;
}

.restore-mode-target {
  width: 100%;
  margin-top: 8px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
