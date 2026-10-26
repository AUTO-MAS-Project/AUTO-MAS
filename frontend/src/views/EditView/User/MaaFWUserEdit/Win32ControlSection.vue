<template>
  <!-- Win32 控制器的三个方式：截图、鼠标、键盘。它们都是**脚本级**设置（Device 组），
       不是每个用户各一份，所以整块只在 Win32 控制器的脚本上出现。值 0 表示不覆盖，
       跟随项目 interface.json 里写的那一份。 -->
  <div v-if="visible" class="form-section win32-control">
    <h3 class="section-title">
      {{ t('edit.maafwWin32Control') }}
      <a-tooltip :title="t('edit.maafwWin32ControlHint')">
        <QuestionCircleOutlined class="section-help" />
      </a-tooltip>
    </h3>

    <a-row :gutter="[24, 8]">
      <a-col :xs="24" :md="8">
        <a-form-item :label="t('edit.maafwWin32Screencap')">
          <a-select
            :value="screencap"
            :options="screencapOptions"
            :disabled="disabled"
            :loading="saving"
            @change="(value: number) => save('Win32ScreencapMethod', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item :label="t('edit.maafwWin32Mouse')">
          <a-select
            :value="mouse"
            :options="inputOptions"
            :disabled="disabled"
            :loading="saving"
            @change="(value: number) => save('Win32MouseMethod', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item :label="t('edit.maafwWin32Keyboard')">
          <a-select
            :value="keyboard"
            :options="inputOptions"
            :disabled="disabled"
            :loading="saving"
            @change="(value: number) => save('Win32KeyboardMethod', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <p class="win32-control-note">{{ t('edit.maafwWin32ControlScope') }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWScriptConfig } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'

/**
 * Win32 控制器的截图 / 鼠标 / 键盘方式。
 *
 * 三个值在引擎里是 ``script_config.Device.Win32{Screencap,Mouse,Keyboard}Method``：
 * 非 0 就用它，0 表示这一项不覆盖、跟随项目 interface 的 ``controller.win32``
 * （解析见 runner_task._resolve_win32_method）。名字与数值抄的是 runner_task 的
 * ``_WIN32_SCREENCAP_METHODS`` / ``_WIN32_INPUT_METHODS``，改那边要同步这里。
 *
 * 它们属于脚本配置（所有用户共用），所以这张表只读脚本配置、也只写脚本配置；
 * 用户页上出现它是因为用户平时就在这一页调，界面上会写明是脚本级。
 */

const props = defineProps<{
  scriptId: string
  scriptConfig: MaaFWScriptConfig | null
  /** 当前控制器是不是 Win32（页面按 interface 里那个控制器的 type 算好传进来） */
  isWin32: boolean
  /** 页面还在加载 / 配置被锁：整块置灰 */
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** 脚本配置已写回后端：页面把新值并入自己的脚本配置副本 */
  saved: [patch: Record<string, Record<string, number>>]
}>()

const { t } = useI18n()
const { updateScript } = useScriptApi()

const saving = ref(false)

const device = computed<Record<string, number | undefined>>(
  () => (props.scriptConfig?.Device ?? {}) as Record<string, number | undefined>
)

/** 只有 Win32 控制器的脚本才看得到这三项：Adb 的截图 / 输入方式是 Device 里另一组字段 */
const visible = computed(() => props.isWin32)

const screencap = computed(() => Number(device.value.Win32ScreencapMethod ?? 0))
const mouse = computed(() => Number(device.value.Win32MouseMethod ?? 0))
const keyboard = computed(() => Number(device.value.Win32KeyboardMethod ?? 0))

/** 0 = 不覆盖，跟随项目 interface.json（runner_task._resolve_win32_method 的口径） */
const followProject = () => ({ value: 0, label: t('edit.maafwWin32FollowProject') })

/** 截图方式可以按位或组合（Foreground / Background 就是组合名） */
const screencapOptions = computed(() => [
  followProject(),
  { value: 1, label: 'GDI' },
  { value: 2, label: 'FramePool' },
  { value: 4, label: 'DXGI_DesktopDup' },
  { value: 8, label: 'DXGI_DesktopDup_Window' },
  { value: 16, label: 'PrintWindow' },
  { value: 32, label: 'ScreenDC' },
  { value: 18, label: 'Background（FramePool + PrintWindow）' },
  { value: 40, label: 'Foreground（DXGI_DesktopDup_Window + ScreenDC）' },
])

const inputOptions = computed(() => [
  followProject(),
  { value: 1, label: 'Seize' },
  { value: 2, label: 'SendMessage' },
  { value: 4, label: 'PostMessage' },
  { value: 8, label: 'LegacyEvent' },
  { value: 16, label: 'PostThreadMessage' },
  { value: 32, label: 'SendMessageWithCursorPos' },
  { value: 64, label: 'PostMessageWithCursorPos' },
  { value: 128, label: 'SendMessageWithWindowPos' },
  { value: 256, label: 'PostMessageWithWindowPos' },
  { value: 512, label: 'Interception' },
  { value: 1024, label: 'AnchoredTouch' },
])

const save = async (field: string, value: number) => {
  if (!props.scriptId) return
  saving.value = true
  try {
    const ok = await updateScript(props.scriptId, { Device: { [field]: value } })
    if (!ok) {
      message.error(t('edit.maafwWin32SaveFailed'))
      return
    }
    emit('saved', { Device: { [field]: value } })
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.maafwWin32SaveFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.win32-control-note {
  margin: 0 0 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.section-help {
  margin-left: 6px;
  color: var(--ant-color-text-tertiary);
}
</style>
