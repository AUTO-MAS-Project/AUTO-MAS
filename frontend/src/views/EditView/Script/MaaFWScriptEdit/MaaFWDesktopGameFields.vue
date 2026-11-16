<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div>
    <!-- 按启动方式摆，每行格数成对、最后一行不留单格：
         让 MAS 启动：启动方式 | 游戏 exe ；Unity 分辨率 | 启动参数 | 等待时间 | 键位映射
         通过链接启动：启动方式 | 启动链接 | 游戏 exe ；Unity 分辨率 | 等待时间 | 键位映射
         由脚本控制：启动方式 | 结束后关闭游戏 ；游戏 exe | 启动器 exe | 键位映射
         （交给脚本关时不要两个 exe，键位映射挪到第一行） -->
    <a-row :gutter="24" class="control-detail-row">
      <a-col :span="firstRowSpan">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.howPcGameLaunched') }}</span>
          </template>
          <!-- 收起时只显示标题（option-label-prop），说明只在展开的选项里出现 -->
          <a-select
            v-model:value="maafwConfig.Game.LaunchMode"
            size="large"
            style="width: 100%"
            option-label-prop="label"
            @change="emit('change', 'Game', 'LaunchMode', maafwConfig.Game.LaunchMode)"
          >
            <a-select-option
              v-for="item in launchModeOptions"
              :key="item.value"
              :value="item.value"
              :label="item.title"
            >
              <div class="launch-option">
                <span class="launch-option-title">{{ item.title }}</span>
                <span class="launch-option-hint">{{ item.hint }}</span>
              </div>
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col v-if="launchMode === 'DirectExe'" :span="12">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.gameExecutable') }}</span>
          </template>
          <PathPickerField
            v-model="maafwConfig.Game.LaunchPath"
            mode="file"
            :placeholder="t('core.edit.pickGameExeThat')"
            :pick-label="t('core.edit.pickExe')"
            @pick="emit('select-launch-path')"
          />
        </a-form-item>
      </a-col>
      <template v-else-if="launchMode === 'URL'">
        <a-col :span="8">
          <a-form-item>
            <template #label>
              <a-tooltip :title="t('core.edit.mfwLaunchLinkTip')">
                <span class="form-label">
                  {{ t('core.edit.mfwLaunchLink') }}
                  <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="maafwConfig.Game.URL"
              placeholder="steam://rungameid/<appid>"
              size="large"
              class="modern-input"
              @blur="emit('change', 'Game', 'URL', maafwConfig.Game.URL)"
            />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item>
            <template #label>
              <span class="form-label">{{ t('core.edit.mfwGameExeForDetect') }}</span>
            </template>
            <PathPickerField
              v-model="maafwConfig.Game.LaunchPath"
              mode="file"
              :placeholder="t('core.edit.pickGameExeThat')"
              :pick-label="t('core.edit.pickExe')"
              @pick="emit('select-launch-path')"
            />
          </a-form-item>
        </a-col>
      </template>
      <template v-else>
        <a-col :span="firstRowSpan">
          <a-form-item>
            <template #label>
              <a-tooltip :title="t('core.edit.mfwCloseGameTip')">
                <span class="form-label">
                  {{ t('core.edit.mfwCloseGameAfterRun') }}
                  <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                </span>
              </a-tooltip>
            </template>
            <a-select
              v-model:value="maafwConfig.Game.CloseMode"
              size="large"
              style="width: 100%"
              :options="closeModeOptions"
              @change="(value: string | number) => emit('change', 'Game', 'CloseMode', value)"
            />
          </a-form-item>
        </a-col>
        <MaaFWHotkeyField
          v-if="closeMode === 'Script'"
          :span="8"
          :script-id="scriptId"
          :preview-data="previewData"
          :controller-name="effectiveControllerName"
          :resource-name="effectiveResourceName"
          :value="maafwConfig.Game.Hotkeys"
          @save="handleHotkeysSave"
        />
      </template>
    </a-row>

    <a-row v-if="launchMode !== 'AttachOnly'" :gutter="24" class="control-detail-row">
      <a-col :span="secondRowSpan">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('core.edit.mfwUnityResolutionTip')">
              <span class="form-label">
                {{ t('core.edit.mfwUnityResolution') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Game.UnityResolution"
            size="large"
            style="width: 100%"
            :options="unityResolutionOptions"
            @change="(value: string | number) => emit('change', 'Game', 'UnityResolution', value)"
          />
        </a-form-item>
      </a-col>
      <!-- 通过链接启动时不要启动参数：参数写进链接 -->
      <a-col v-if="launchMode === 'DirectExe'" :span="secondRowSpan">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.launchArguments') }}</span>
          </template>
          <a-input
            v-model:value="maafwConfig.Game.Arguments"
            :placeholder="t('core.edit.optional')"
            size="large"
            class="modern-input"
            @blur="emit('change', 'Game', 'Arguments', maafwConfig.Game.Arguments)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="secondRowSpan">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('core.edit.mfwWaitTimeTip')">
              <span class="form-label">
                {{ t('core.edit.waitTimeSeconds') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-number
            v-model:value="maafwConfig.Game.WaitTime"
            :min="0"
            :max="9999"
            size="large"
            style="width: 100%"
            @blur="emit('change', 'Game', 'WaitTime', maafwConfig.Game.WaitTime)"
          />
        </a-form-item>
      </a-col>
      <MaaFWHotkeyField
        :span="secondRowSpan"
        :script-id="scriptId"
        :preview-data="previewData"
        :controller-name="effectiveControllerName"
        :resource-name="effectiveResourceName"
        :value="maafwConfig.Game.Hotkeys"
        @save="handleHotkeysSave"
      />
    </a-row>

    <a-row v-else-if="closeMode !== 'Script'" :gutter="24" class="control-detail-row">
      <a-col :span="pairedColSpan">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.mfwGameExeOptional') }}</span>
          </template>
          <PathPickerField
            v-model="maafwConfig.Game.LaunchPath"
            mode="file"
            :placeholder="t('core.edit.mfwGameExeOptionalPlaceholder')"
            :pick-label="t('core.edit.pickExe')"
            @pick="emit('select-launch-path')"
          >
            <template #after-pick>
              <a-button
                v-if="maafwConfig.Game.LaunchPath"
                size="large"
                :aria-label="t('core.edit.clearPath')"
                @click="clearPath('LaunchPath')"
              >
                <template #icon>
                  <DeleteOutlined />
                </template>
              </a-button>
            </template>
          </PathPickerField>
        </a-form-item>
      </a-col>
      <a-col :span="pairedColSpan">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.mfwLauncherExeOptional') }}</span>
          </template>
          <PathPickerField
            v-model="maafwConfig.Game.LauncherPath"
            mode="file"
            :placeholder="t('core.edit.optional')"
            :pick-label="t('core.edit.pickExe')"
            @pick="emit('select-launcher-path')"
          >
            <template #after-pick>
              <a-button
                v-if="maafwConfig.Game.LauncherPath"
                size="large"
                :aria-label="t('core.edit.clearPath')"
                @click="clearPath('LauncherPath')"
              >
                <template #icon>
                  <DeleteOutlined />
                </template>
              </a-button>
            </template>
          </PathPickerField>
        </a-form-item>
      </a-col>
      <MaaFWHotkeyField
        :span="8"
        :script-id="scriptId"
        :preview-data="previewData"
        :controller-name="effectiveControllerName"
        :resource-name="effectiveResourceName"
        :value="maafwConfig.Game.Hotkeys"
        @save="handleHotkeysSave"
      />
    </a-row>
  </div>
</template>

<script setup lang="ts">
import PathPickerField from '@/components/PathPickerField.vue'
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { DeleteOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type {
  MaaFWCloseMode,
  MaaFWInterfacePreviewData,
  MaaFWLaunchMode,
  MaaFWScriptConfig,
  MaaFWUnityResolution,
} from '@/types/script'
import MaaFWHotkeyField from './MaaFWHotkeyField.vue'
import { collectHotkeyOptions } from './hotkeyOptions'

const props = defineProps<{
  /** 脚本 ID：键位映射弹窗「从项目导入」按它读外壳配置实例 */
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  effectiveControllerName: string
  effectiveResourceName: string
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'select-launch-path': []
  'select-launcher-path': []
}>()

const { t } = useI18n()

const launchMode = computed<MaaFWLaunchMode>(() => props.maafwConfig.Game.LaunchMode)
const closeMode = computed<MaaFWCloseMode>(() => props.maafwConfig.Game.CloseMode ?? 'OnFailure')

const launchModeOptions = computed<Array<{ value: MaaFWLaunchMode; title: string; hint: string }>>(
  () => [
    {
      value: 'DirectExe',
      title: t('core.edit.letMasLaunchGame'),
      hint: t('core.edit.pickGameSOwn'),
    },
    {
      value: 'URL',
      title: t('core.edit.mfwLaunchGameByLink'),
      hint: t('core.edit.mfwLaunchGameByLinkHint'),
    },
    {
      value: 'AttachOnly',
      title: t('core.edit.launchGameOtherWay'),
      hint: t('core.edit.masOnlyTakesOver'),
    },
  ]
)

const closeModeOptions = computed<Array<{ label: string; value: MaaFWCloseMode }>>(() => [
  { label: t('core.edit.mfwCloseGameByScript'), value: 'Script' },
  { label: t('core.edit.mfwCloseGameOnFailure'), value: 'OnFailure' },
  { label: t('core.edit.mfwCloseGameAlways'), value: 'Always' },
])

// 键位映射格只在 interface 有对当前控制器 / 资源生效的 hotkey option 时才渲染（与 MaaFWHotkeyField
// 同一判据），没有它时同一行其余各格平分，不在右边空出一格
const hasHotkeyField = computed(
  () =>
    collectHotkeyOptions(
      props.previewData,
      props.effectiveControllerName,
      props.effectiveResourceName
    ).length > 0
)
// 让 MAS 启动的第二行四格（Unity 分辨率、启动参数、等待时间、键位映射），通过链接启动少了启动参数；
// 由脚本控制的第二行是两个 exe + 键位映射
const secondRowSpan = computed(() =>
  launchMode.value === 'DirectExe' ? (hasHotkeyField.value ? 6 : 8) : hasHotkeyField.value ? 8 : 12
)
const pairedColSpan = computed(() => (hasHotkeyField.value ? 8 : 12))
const firstRowSpan = computed(() => {
  if (launchMode.value === 'URL') return 8
  if (launchMode.value === 'AttachOnly' && closeMode.value === 'Script') {
    return hasHotkeyField.value ? 8 : 12
  }
  return 12
})

const clearPath = (key: 'LaunchPath' | 'LauncherPath') => {
  props.maafwConfig.Game[key] = null
  emit('change', 'Game', key, null)
}

// 只给两档常用尺寸：Unity 播放器只认整数宽高，1080p 是各脚本闸门的基准，720p 留给小屏
const unityResolutionOptions = computed<Array<{ label: string; value: MaaFWUnityResolution }>>(
  () => [
    { label: t('core.edit.mfwUnityResolutionOff'), value: 'Off' },
    { label: '1920×1080', value: '1920x1080' },
    { label: '1280×720', value: '1280x720' },
  ]
)

// 键位映射弹窗保存：先改草稿再走页面的自动保存通道
const handleHotkeysSave = (value: string) => {
  props.maafwConfig.Game.Hotkeys = value
  emit('change', 'Game', 'Hotkeys', value)
}
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
.launch-option {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
  padding: 2px 0;
}

.launch-option-title {
  font-weight: 500;
}

.launch-option-hint {
  font-size: 12px;
  opacity: 0.65;
}

.control-detail-row {
  margin-top: 16px;
}
</style>
