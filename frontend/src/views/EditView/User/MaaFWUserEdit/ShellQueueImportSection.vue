<template>
  <a-button size="small" :loading="loading" @click="openDialog">
    <template #icon>
      <ImportOutlined />
    </template>
    {{ t('edit.shellQueueImport') }}
  </a-button>

  <a-modal
    v-model:open="modalOpen"
    :title="t('edit.shellQueueImportTitle')"
    :ok-text="t('edit.shellQueueImportOk')"
    :cancel-text="t('common.cancel')"
    :ok-button-props="{ disabled: !picked || applying }"
    :confirm-loading="applying"
    @ok="apply"
  >
    <!-- 从哪儿读：默认按脚本的项目来源目录（后端先来源、再内嵌副本），也能临时改指别的目录——
         用户把脚本位置挪了、或者平时用的是另一份外壳时用得上 -->
    <div class="shell-queue-import-source">
      <span class="shell-queue-import-dir" :title="shownDir">
        {{ t('edit.shellQueueImportDir', { dir: shownDir }) }}
      </span>
      <a-button type="link" size="small" @click="pickDirectory">
        {{ t('edit.shellQueueImportPickDir') }}
      </a-button>
    </div>

    <a-select
      v-if="instances.length > 0"
      v-model:value="picked"
      class="shell-queue-import-select"
      :options="instanceOptions"
    />
    <a-empty
      v-else
      class="shell-queue-import-empty"
      :description="t('edit.shellQueueImportNone')"
    />

    <a-alert type="warning" show-icon :message="t('edit.shellQueueImportNote')" />
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message, notification } from 'ant-design-vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import { h } from 'vue'
import type { MaaFWShellInstanceItem } from '@/api'
import { useMaaFWShellInstanceApi } from '@/composables/useMaaFWShellInstanceApi'

/**
 * 「配置导入」：把外壳（MFAAvalonia / MXU / MFW-PyQt6）里配好的任务队列与选项覆盖到当前用户。
 * 引导最后一步的「导入已有配置为账号」只在新建脚本时走一次，脚本建好之后再想同步就从这里。
 *
 * 换算在后端（与引导那条同一条），这里只管选实例、把算好的快照交给父级换进本地状态；
 * 写库也由后端那次请求完成，这里不再走一次用户保存——同一个动作写两遍没有意义。
 *
 * 脚本与用户直接从路由取（页面自己也是这么拿的），免得为了一个按钮把 `queueHeader` 分节的属性
 * 契约撑大——那份契约是所有特调要替换这一节时照着实现的东西。
 */

const emit = defineEmits<{
  /**
   * 实际写进用户配置的任务快照（原始 JSON）与特调一并改掉的用户信息字段，
   * 由父级按用户页自己的形状换进本地状态
   */
  imported: [snapshot: Record<string, unknown>, info: Record<string, unknown>]
}>()

const { t } = useI18n()
const route = useRoute()
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const { listShellInstances, applyShellInstanceToUser } = useMaaFWShellInstanceApi()

const loading = ref(false)
const applying = ref(false)
const modalOpen = ref(false)
const instances = ref<MaaFWShellInstanceItem[]>([])
const picked = ref('')
/** 「选择其他目录」选的那份；为空表示走脚本默认的来源目录 */
const pickedDir = ref('')

const shownDir = computed(
  () =>
    pickedDir.value ||
    instances.value.find(item => item.sourceDir)?.sourceDir ||
    t('edit.shellQueueImportDefaultDir')
)

/** 下拉里带上外壳名、是否当前使用中与**外壳里**的任务数：光一个「配置 1」看不出哪份是哪个 */
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

const load = async (dir?: string) => {
  loading.value = true
  try {
    const found = await listShellInstances(scriptId, dir)
    instances.value = found
    // 默认选外壳上次用的那份，与引导里同一个口径
    picked.value = found.length > 0 ? (found.find(item => item.active) || found[0]).id : ''
    return true
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.shellQueueImportFailed'))
    return false
  } finally {
    loading.value = false
  }
}

const openDialog = async () => {
  pickedDir.value = ''
  // 默认目录里一份都没有也要开：弹窗里能改指别的目录，那正是「脚本挪过位置」时的出路
  await load()
  modalOpen.value = true
}

const pickDirectory = async () => {
  if (!window.electronAPI?.selectFolder) {
    message.error(t('edit.filePickingUnavailableRun'))
    return
  }
  const dir = await window.electronAPI.selectFolder()
  if (!dir) return
  if (await load(dir)) {
    pickedDir.value = dir
    if (instances.value.length === 0) {
      message.warning(t('edit.shellQueueImportNone'))
    }
  }
}

const apply = async () => {
  applying.value = true
  try {
    // 列表从哪个目录读的就回哪个目录找：实例 ID 只是外壳里的文件名，换了目录可能撞名
    const { result, snapshot, info } = await applyShellInstanceToUser(
      scriptId,
      userId,
      picked.value,
      pickedDir.value || undefined
    )
    if (!snapshot) {
      message.error(t('edit.shellQueueImportFailed'))
      return
    }
    // 父级是同步的：换本地状态而已，写库那次请求后端已经做完了
    emit('imported', snapshot, info)
    modalOpen.value = false
    message.success(t('edit.shellQueueImportDone', { count: result.importedTaskCount ?? 0 }))
    const skipped = result.skipped ?? []
    if (skipped.length > 0) {
      // 覆盖会冲掉原队列，漏掉的任务必须**全部**列出来、而且不能自己消失——
      // 只提示前几条再自动收起，用户永远不知道少的是哪几个
      notification.warning({
        message: t('edit.shellQueueImportSkippedTitle', { count: skipped.length }),
        description: h(
          'ul',
          { class: 'shell-queue-import-skipped' },
          skipped.map(item => h('li', item))
        ),
        duration: 0,
      })
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.shellQueueImportFailed'))
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.shell-queue-import-source {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.shell-queue-import-dir {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.shell-queue-import-select {
  width: 100%;
  margin-bottom: 12px;
}

.shell-queue-import-empty {
  margin-bottom: 12px;
}
</style>
