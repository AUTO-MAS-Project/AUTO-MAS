<template>
  <a-button size="small" @click="openDialog">
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
    :ok-button-props="{ disabled: !canApply }"
    :confirm-loading="applying"
    @ok="apply"
  >
    <a-segmented
      v-model:value="sourceKind"
      block
      class="queue-import-switch"
      :options="sourceKindOptions"
    />

    <!-- 本脚本的其他用户：单选卡片，选中的那份队列覆盖当前用户的 -->
    <template v-if="sourceKind === 'users'">
      <a-spin :spinning="userLoading" :class="{ 'queue-import-spin': userLoading }">
        <div v-if="userCandidates.length > 0" class="queue-import-users" role="radiogroup">
          <div
            v-for="candidate in userCandidates"
            :key="candidate.userId"
            role="radio"
            tabindex="0"
            :aria-checked="pickedUserId === candidate.userId"
            class="queue-import-user"
            :class="{ 'queue-import-user-selected': pickedUserId === candidate.userId }"
            @click="pickedUserId = candidate.userId"
            @keydown.enter.prevent="pickedUserId = candidate.userId"
            @keydown.space.prevent="pickedUserId = candidate.userId"
          >
            <div class="queue-import-user-head">
              <span class="queue-import-user-name">{{ candidate.name }}</span>
              <span class="queue-import-user-count">
                {{ t('edit.queueTaskCount', { count: candidate.chips.length }) }}
              </span>
              <span v-if="candidate.invalidCount > 0" class="queue-invalid-tag">
                {{ t('edit.queueInvalidCount', { count: candidate.invalidCount }) }}
              </span>
              <span v-if="candidate.passwordCount > 0" class="queue-password-tag">
                {{ t('edit.queueImportPasswordCount', { count: candidate.passwordCount }) }}
              </span>
            </div>
            <MaaFWQueueChips :chips="candidate.chips" />
          </div>
        </div>
        <a-empty
          v-else-if="!userLoading"
          class="shell-queue-import-empty"
          :description="t('edit.queueImportNoUsers')"
        />
      </a-spin>
    </template>

    <template v-else>
      <!-- 从哪儿读：默认按脚本的项目来源目录（后端先来源、再内嵌副本），也能临时改指别的目录——
           用户把脚本位置挪了、或者平时用的是另一份外壳时用得上 -->
      <div class="shell-queue-import-source">
        <span class="shell-queue-import-dir" :title="shownDir">
          {{ t('edit.shellQueueImportDir', { dir: shownDir }) }}
        </span>
        <a-button type="link" size="small" @click="pickDirectory">
          {{ t('edit.mfwHotkeyImportPickDir') }}
        </a-button>
      </div>

      <a-spin :spinning="shellLoading" :class="{ 'queue-import-spin': shellLoading }">
        <a-select
          v-if="instances.length > 0"
          v-model:value="picked"
          class="shell-queue-import-select"
          :options="instanceOptions"
        />
        <a-empty
          v-else-if="!shellLoading"
          class="shell-queue-import-empty"
          :description="t('edit.shellQueueImportNone')"
        />
      </a-spin>
    </template>

    <a-alert type="warning" show-icon :message="t('edit.shellQueueImportNote')" />
  </a-modal>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message, notification } from 'ant-design-vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import type { MaaFWShellInstanceItem } from '@/api'
import { useMaaFWShellInstanceApi } from '@/composables/useMaaFWShellInstanceApi'
import type { MaaFWUserQueueImportCandidate } from '../../MaaFWFlavor/sectionContracts'
import MaaFWQueueChips from './MaaFWQueueChips.vue'

/**
 * 「配置导入」：把本脚本另一个用户的队列，或外壳（MFAAvalonia / MXU / MFW-PyQt6）里配好的任务队列
 * 与选项覆盖到当前用户。引导最后一步的「导入已有配置为账号」只在新建脚本时走一次，脚本建好之后
 * 再想同步就从这里。
 *
 * 「本脚本其他用户」：能不能导入要按 interface 与当前控制器 / 资源判断，数据由页面备好（打开时发
 * `load-users` 让页面取一次用户列表），这里只显示、交回选中的用户，替换与落盘由页面做。
 *
 * 「外壳」：换算在后端（与引导那条同一条），这里只管选实例、把算好的快照交给父级换进本地状态；
 * 写库也由后端那次请求完成，这里不再走一次用户保存——同一个动作写两遍没有意义。
 * 脚本与用户直接从路由取（页面自己也是这么拿的），不经 `queueHeader` 分节的属性契约。
 */

const props = defineProps<{
  userCandidates: MaaFWUserQueueImportCandidate[]
  userLoading: boolean
}>()

const emit = defineEmits<{
  /** 打开了弹窗：父级取一次本脚本的用户列表 */
  'load-users': []
  /** 「本脚本其他用户」选定了一个用户：父级用它的队列覆盖当前队列 */
  'import-from-user': [userId: string]
  /**
   * 实际写进用户配置的任务快照（原始 JSON）与特调一并改掉的用户信息字段，
   * 由父级按用户页自己的形状换进本地状态
   */
  imported: [snapshot: Record<string, unknown>, info: Record<string, unknown>]
}>()

type SourceKind = 'users' | 'shell'

const { t } = useI18n()
const route = useRoute()
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const { listShellInstances, pickShellInstanceDirectory, applyShellInstanceToUser } =
  useMaaFWShellInstanceApi()

const shellLoading = ref(false)
const applying = ref(false)
const modalOpen = ref(false)
const instances = ref<MaaFWShellInstanceItem[]>([])
const picked = ref('')
/** 「选择其他目录」选的那份；为空表示走脚本默认的来源目录 */
const pickedDir = ref('')
const sourceKind = ref<SourceKind>('users')
const pickedUserId = ref('')

const sourceKindOptions = computed(() => [
  { value: 'users', label: t('edit.queueImportFromUsers') },
  { value: 'shell', label: t('edit.queueImportFromShell') },
])

const pickedUser = computed(
  () => props.userCandidates.find(item => item.userId === pickedUserId.value) || null
)

// 用户列表换了（重新读、interface 变了）选中的不在了就清掉，别让确定按钮指着一个看不见的用户
watch(
  () => props.userCandidates,
  candidates => {
    if (!candidates.some(item => item.userId === pickedUserId.value)) pickedUserId.value = ''
  }
)

const canApply = computed(() => {
  if (applying.value) return false
  if (sourceKind.value === 'users') return Boolean(pickedUser.value?.entries.length)
  return Boolean(picked.value) && !shellLoading.value
})

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
      item.active ? t('edit.shellImportActive') : '',
      t('edit.shellQueueImportTaskCount', { count: item.taskCount }),
    ]
      .filter(Boolean)
      .join(' · '),
  }))
)

/** 换上一批实例，默认选外壳上次用的那份（与引导里同一个口径） */
const showInstances = (found: MaaFWShellInstanceItem[]) => {
  instances.value = found
  picked.value = found.length > 0 ? (found.find(item => item.active) || found[0]).id : ''
}

/** 外壳实例的读取序号：读到一半又重开弹窗或改选了目录，旧的那次结果作废 */
let shellListRequest = 0

const loadShellInstances = async () => {
  const request = ++shellListRequest
  shellLoading.value = true
  // 上次「选择其他目录」列出来的那批不能留着：目录已经回到默认，覆盖时会去默认目录按 ID 找
  showInstances([])
  try {
    const found = await listShellInstances(scriptId)
    if (request === shellListRequest) showInstances(found)
  } catch (error) {
    if (request !== shellListRequest) return
    showInstances([])
    message.error(error instanceof Error ? error.message : t('edit.shellQueueImportFailed'))
  } finally {
    if (request === shellListRequest) shellLoading.value = false
  }
}

const openDialog = () => {
  sourceKind.value = 'users'
  pickedUserId.value = ''
  pickedDir.value = ''
  emit('load-users')
  // 先开弹窗（默认页签是本脚本其他用户），外壳实例在后台读，外壳页签里转圈。
  // 默认目录里一份都没有、读失败也照样开着：弹窗里能改指别的目录，那正是「脚本挪过位置」时的出路
  modalOpen.value = true
  void loadShellInstances()
}

const pickDirectory = async () => {
  try {
    const found = await pickShellInstanceDirectory(scriptId)
    if (!found) return
    // 选了目录就以它为准，还没读完的默认目录那次作废
    shellListRequest += 1
    shellLoading.value = false
    showInstances(found.instances)
    pickedDir.value = found.dir
    if (found.instances.length === 0) {
      message.warning(t('edit.shellQueueImportNone'))
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.shellQueueImportFailed'))
  }
}

const apply = async () => {
  if (sourceKind.value === 'users') {
    const candidate = pickedUser.value
    if (!candidate || candidate.entries.length === 0) return
    // 替换、落盘与成功提示都由父级做：保存真正成功后才提示，条数是实际写入的实例数
    emit('import-from-user', candidate.userId)
    modalOpen.value = false
    return
  }
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

.queue-import-switch {
  margin-bottom: 12px;
}

/* 读用户列表 / 外壳实例时还没有内容，留出转圈的位置 */
.queue-import-spin {
  display: block;
  min-height: 64px;
}

.queue-import-users {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  margin-bottom: 12px;
  overflow-y: auto;
}

.queue-import-user {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.queue-import-user:hover {
  border-color: var(--ant-color-primary-hover);
}

.queue-import-user-selected,
.queue-import-user-selected:hover {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.queue-import-user-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.queue-import-user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ant-color-text);
  font-weight: 600;
}

.queue-import-user-count {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 「N 个已失效」：虚线灰标签 */
.queue-invalid-tag {
  flex: none;
  padding: 0 7px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}

/* 「N 项密码需重填」：警告色标签 */
.queue-password-tag {
  flex: none;
  padding: 0 7px;
  border: 1px solid var(--ant-color-warning-border);
  border-radius: 4px;
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning-text);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}
</style>
