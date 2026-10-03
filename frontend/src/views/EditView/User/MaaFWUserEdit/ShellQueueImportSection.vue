<template>
  <div class="shell-queue-import">
    <a-button :loading="loading" :disabled="disabled" @click="openDialog">
      {{ t('edit.shellQueueImport') }}
    </a-button>
    <span class="shell-queue-import-hint">{{ t('edit.shellQueueImportHint') }}</span>

    <a-modal
      v-model:open="modalOpen"
      :title="t('edit.shellQueueImportTitle')"
      :ok-text="t('edit.shellQueueImportOk')"
      :cancel-text="t('common.cancel')"
      :ok-button-props="{ disabled: !picked || applying }"
      :confirm-loading="applying"
      @ok="apply"
    >
      <a-select
        v-if="instances.length > 0"
        v-model:value="picked"
        class="shell-queue-import-select"
        :options="instanceOptions"
      />
      <a-alert type="warning" show-icon :message="t('edit.shellQueueImportNote')" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { MaaFWShellInstanceItem } from '@/api'
import { useMaaFWShellInstanceApi } from '@/composables/useMaaFWShellInstanceApi'

/**
 * 用户页任务队列上方的「从外壳导入队列」：脚本建好之后又在外壳（MFAAvalonia / MXU / MFW-PyQt6）
 * 里调过队列时，把那份队列与选项再同步到这个用户——引导里的「导入已有配置为账号」只在新建脚本时
 * 走一次，之后想再同步就只能从这个入口。
 *
 * 换算在后端（与引导那次同一条），这里只负责选实例、把算好的快照交给父级刷进本地状态。
 */

const props = defineProps<{
  scriptId: string
  userId: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** 算好的任务快照（原始 JSON），由父级按用户页自己的快照类型规整后存下去 */
  imported: [snapshot: Record<string, unknown>]
}>()

const { t } = useI18n()
const { listShellInstances, applyShellInstanceToUser } = useMaaFWShellInstanceApi()

const loading = ref(false)
const applying = ref(false)
const modalOpen = ref(false)
const instances = ref<MaaFWShellInstanceItem[]>([])
const picked = ref('')

/** 下拉里带上外壳名、是否当前使用中与任务数：光一个「配置 1」看不出哪份是哪个 */
const instanceOptions = computed(() =>
  instances.value.map(item => ({
    value: item.id,
    label: [
      item.name,
      item.source,
      item.active ? t('edit.shellQueueImportActive') : '',
      t('edit.shellQueueImportTaskCount', { count: item.taskCount }),
    ]
      .filter(Boolean)
      .join(' · '),
  }))
)

const openDialog = async () => {
  loading.value = true
  try {
    const found = await listShellInstances(props.scriptId)
    if (found.length === 0) {
      message.warning(t('edit.shellQueueImportEmpty'))
      return
    }
    instances.value = found
    // 默认选外壳上次用的那份，与引导里同一个口径
    picked.value = (found.find(item => item.active) || found[0]).id
    modalOpen.value = true
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.shellQueueImportFailed'))
  } finally {
    loading.value = false
  }
}

const apply = async () => {
  applying.value = true
  try {
    const { result, snapshot } = await applyShellInstanceToUser(
      props.scriptId,
      props.userId,
      picked.value
    )
    if (!snapshot) {
      message.error(t('edit.shellQueueImportFailed'))
      return
    }
    emit('imported', snapshot)
    modalOpen.value = false
    message.success(t('edit.shellQueueImportDone', { count: result.importedTaskCount ?? 0 }))
    const skipped = result.skipped ?? []
    if (skipped.length > 0) {
      // 漏掉的任务要说清楚，否则用户只看到队列少了东西；多留几秒让他看清
      message.warning(
        t('edit.shellQueueImportSkipped', {
          count: skipped.length,
          items: skipped.slice(0, 3).join('、') + (skipped.length > 3 ? '…' : ''),
        }),
        6
      )
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.shellQueueImportFailed'))
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.shell-queue-import {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.shell-queue-import-hint {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.shell-queue-import-select {
  width: 100%;
  margin-bottom: 12px;
}
</style>
