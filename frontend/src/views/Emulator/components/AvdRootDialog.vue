<script setup lang="ts">
/**
 * 添加魔改 AVD：选根目录（解压好的模拟器内测包）→ 看电脑检查与组件 → 添加。
 *
 * 组件随内测包提供，MAS 不下载；缺了由电脑检查写明缺哪几项、请用完整的内测包。组件齐了点「添加」
 * 走普通的路径纳管。已纳管的根目录也从这里看组件和电脑检查。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined } from '@ant-design/icons-vue'

import type { Emulator2AvdStatusOut } from '@/api'
import { useAvdApi } from '@/composables/useAvdApi'
import { isRootAdded, samePath } from '../avdLogic'
import AvdComponentList from './AvdComponentList.vue'
import AvdPrecheckList from './AvdPrecheckList.vue'

const open = defineModel<boolean>('open', { required: true })
/** `addedRoots`：这条配置里已经纳管的魔改 AVD 根目录，已在里面的不再给「添加」 */
const props = defineProps<{ emulatorId: string; initialRoot?: string; addedRoots?: string[] }>()
const emit = defineEmits<{ added: [] }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const api = useAvdApi()

const root = ref('')
const checking = ref(false)
const status = ref<Emulator2AvdStatusOut | null>(null)
/** 状态是哪个根目录查出来的；输入框改了之后旧结果不再算数 */
const checkedRoot = ref('')
const adding = ref(false)

const current = computed(() =>
  status.value && samePath(checkedRoot.value, root.value) ? status.value : null
)
const ready = computed(() => Boolean(current.value?.ready))
const alreadyAdded = computed(() => isRootAdded(props.addedRoots ?? [], root.value))

const reset = () => {
  root.value = props.initialRoot ?? ''
  status.value = null
  checkedRoot.value = ''
}

/** `refresh`：用户主动检查（回车、点「检查」、选了目录）时跳过电脑检查的缓存 */
const check = async (refresh = false) => {
  const target = root.value.trim()
  if (!target) return
  checking.value = true
  try {
    status.value = await api.getStatus(target, refresh)
    checkedRoot.value = target
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`读取魔改 AVD 状态失败 (${target}): ${detail}`)
    message.error(detail || t('emulator2.avd.toast.statusFailed'))
  } finally {
    checking.value = false
  }
}

const pickRoot = async () => {
  if (!window.electronAPI?.selectFolder) return
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  root.value = picked
  await check(true)
}

const addRoot = async () => {
  adding.value = true
  try {
    const response = await api.addRoot(props.emulatorId, root.value.trim())
    if (!response.ok) {
      const key = `emulator2.reason.${response.reason}`
      message.warning(response.reason && t(key) !== key ? t(key) : response.message)
      return
    }
    message.success(t('emulator2.toast.addOk', { count: 1 }))
    emit('added')
    open.value = false
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`添加魔改 AVD 失败: ${detail}`)
    message.error(detail || t('emulator2.avd.toast.addFailed'))
  } finally {
    adding.value = false
  }
}

watch(open, value => {
  if (!value) return
  reset()
  if (root.value) void check()
})
</script>

<template>
  <a-modal v-model:open="open" :title="t('emulator2.avd.title')" width="760px" :footer="null">
    <div class="avd-root-dialog">
      <a-form layout="vertical">
        <a-form-item :label="t('emulator2.avd.root')">
          <div class="root-row">
            <a-input
              v-model:value="root"
              :placeholder="t('emulator2.avd.rootPlaceholder')"
              @press-enter="check(true)"
            >
              <template #suffix>
                <FolderOpenOutlined class="root-pick" @click="pickRoot" />
              </template>
            </a-input>
            <a-button :loading="checking" :disabled="!root.trim()" @click="check(true)">
              {{ t('emulator2.avd.check') }}
            </a-button>
          </div>
        </a-form-item>
      </a-form>

      <template v-if="current">
        <AvdPrecheckList :items="current.prechecks ?? []" />
        <AvdComponentList :components="current.components ?? []" />
      </template>

      <div class="dialog-footer">
        <a-button @click="open = false">
          {{ alreadyAdded ? t('emulator2.avd.close') : t('emulator.cancel') }}
        </a-button>
        <a-button
          v-if="!alreadyAdded"
          type="primary"
          :loading="adding"
          :disabled="!ready"
          @click="addRoot"
        >
          {{ t('emulator2.add') }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.root-row {
  display: flex;
  gap: 8px;
}

.root-pick {
  cursor: pointer;
  color: var(--ant-color-text-secondary);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
