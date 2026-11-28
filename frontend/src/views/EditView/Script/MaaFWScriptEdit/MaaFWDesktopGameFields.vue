<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div>
    <!-- 按启动方式压成一行排，格宽按格数给（controlGrid.ts），最后一行不留单格：
         让 MAS 启动：启动方式、游戏目标、[设备]、Unity 分辨率、启动参数、等待时间、[键位映射]
         通过链接启动：启动方式、启动链接、游戏目标、[设备]、Unity 分辨率、等待时间、[键位映射]
         由脚本控制：启动方式、结束后关闭游戏、游戏目标（可选）、[设备]、[键位映射]
         游戏目标写托管的游戏绑定；「设备」只在目标有多台设备或所绑设备已删除时出现 -->
    <a-row :gutter="24" class="control-detail-row">
      <a-col v-bind="col('launchMode')">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('core.edit.howPcGameLaunched') }}</span>
          </template>
          <!-- 收起时只显示标题（option-label-prop），说明只在展开的选项里出现 -->
          <a-select
            v-model:value="maafwConfig.Game.LaunchMode"
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
      <a-col v-if="launchMode === 'URL'" v-bind="col('url')">
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
            class="modern-input"
            @blur="emit('change', 'Game', 'URL', maafwConfig.Game.URL)"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="launchMode === 'AttachOnly'" v-bind="col('closeMode')">
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
            style="width: 100%"
            :options="closeModeOptions"
            @change="(value: string | number) => emit('change', 'Game', 'CloseMode', value)"
          />
        </a-form-item>
      </a-col>
      <template v-if="gameBinding.available">
        <a-col v-bind="col('target')">
          <MaaFWGameTargetSelect
            :binding="gameBinding"
            :label="targetLabel"
            :placeholder="t('core.games.selectTarget')"
          />
        </a-col>
        <a-col v-if="gameBinding.desktopDeviceVisible" v-bind="col('device')">
          <MaaFWGameDeviceSelect
            :binding="gameBinding"
            :label="t('core.games.device')"
            :empty-placeholder="t('core.games.selectTarget')"
          />
        </a-col>
      </template>
      <template v-if="launchMode !== 'AttachOnly'">
        <a-col v-bind="col('unity')">
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
              style="width: 100%"
              :options="unityResolutionOptions"
              @change="(value: string | number) => emit('change', 'Game', 'UnityResolution', value)"
            />
          </a-form-item>
        </a-col>
        <!-- 通过链接启动时不要启动参数：参数写进链接 -->
        <a-col v-if="launchMode === 'DirectExe'" v-bind="col('arguments')">
          <a-form-item>
            <template #label>
              <span class="form-label">{{ t('core.edit.launchArguments') }}</span>
            </template>
            <a-input
              v-model:value="maafwConfig.Game.Arguments"
              :placeholder="t('core.edit.optional')"
              class="modern-input"
              @blur="emit('change', 'Game', 'Arguments', maafwConfig.Game.Arguments)"
            />
          </a-form-item>
        </a-col>
        <a-col v-bind="col('waitTime')">
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
              style="width: 100%"
              @blur="emit('change', 'Game', 'WaitTime', maafwConfig.Game.WaitTime)"
            />
          </a-form-item>
        </a-col>
      </template>
      <MaaFWHotkeyField
        :col="col('hotkey')"
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
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type {
  MaaFWCloseMode,
  MaaFWInterfacePreviewData,
  MaaFWLaunchMode,
  MaaFWScriptConfig,
  MaaFWUnityResolution,
} from '@/types/script'
import MaaFWGameDeviceSelect from './MaaFWGameDeviceSelect.vue'
import MaaFWGameTargetSelect from './MaaFWGameTargetSelect.vue'
import MaaFWHotkeyField from './MaaFWHotkeyField.vue'
import { fieldCols } from './controlGrid'
import { collectHotkeyOptions } from './hotkeyOptions'
import type { MaaFWInlineGameBinding } from './useMaaFWInlineGameBinding'

const props = defineProps<{
  /** 脚本 ID：键位映射弹窗「从项目导入」按它读外壳配置实例 */
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  effectiveControllerName: string
  effectiveResourceName: string
  /** 控制配置分节建的游戏绑定（目标 / 设备选择与提示共用一份） */
  gameBinding: MaaFWInlineGameBinding
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'select-launch-path': []
  'select-launcher-path': []
}>()

const { t } = useI18n()

const launchMode = computed<MaaFWLaunchMode>(() => props.maafwConfig.Game.LaunchMode)

type DesktopField =
  | 'launchMode'
  | 'url'
  | 'closeMode'
  | 'target'
  | 'device'
  | 'unity'
  | 'arguments'
  | 'waitTime'
  | 'hotkey'

// interface 里没有对当前控制器 / 资源生效的 hotkey option 时键位映射整格不渲染，格数里也不算它
const hotkeyVisible = computed(
  () =>
    collectHotkeyOptions(
      props.previewData,
      props.effectiveControllerName,
      props.effectiveResourceName
    ).length > 0
)

const fields = computed<DesktopField[]>(() => {
  const binding: DesktopField[] = props.gameBinding.available
    ? ['target', ...(props.gameBinding.desktopDeviceVisible ? (['device'] as const) : [])]
    : []
  const hotkey: DesktopField[] = hotkeyVisible.value ? ['hotkey'] : []
  switch (launchMode.value) {
    case 'URL':
      return ['launchMode', 'url', ...binding, 'unity', 'waitTime', ...hotkey]
    case 'AttachOnly':
      return ['launchMode', 'closeMode', ...binding, ...hotkey]
    default:
      return ['launchMode', ...binding, 'unity', 'arguments', 'waitTime', ...hotkey]
  }
})
const col = computed(() => fieldCols(fields.value))

// 游戏目标那一格沿用各启动方式原来的叫法
const targetLabel = computed(() =>
  launchMode.value === 'URL'
    ? t('core.edit.mfwGameExeForDetect')
    : launchMode.value === 'AttachOnly'
      ? t('core.edit.mfwGameExeOptional')
      : t('core.edit.gameExecutable')
)

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
