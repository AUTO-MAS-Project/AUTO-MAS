<template>
  <!-- 配置组/脚本/路径 项目编辑面板：与内置组设置面板一致的「可见标签栏 + 放大」结构 -->
  <div class="bgi-project-shell">
    <a-tabs :active-key="shellPaneKey" class="bgi-project-shell-tabs">
      <!-- 标签栏最右：放大图标（点击后居中大弹窗展示更大编辑区） -->
      <template #tabBarExtraContent>
        <a-tooltip :title="t('edit.bettergiProjectZoom')" placement="top">
          <a-button
            type="text"
            size="small"
            class="bgi-project-zoom-btn"
            :aria-label="t('edit.bettergiProjectZoom')"
            @click="zoomed = true"
          >
            <template #icon><FullscreenOutlined /></template>
          </a-button>
        </a-tooltip>
      </template>
      <a-tab-pane :key="shellPaneKey" :tab="shellTabLabel">
        <BettergiGroupProjectBody
          ref="bodyRef"
          :script-id="scriptId"
          :user-id="userId"
          :kind="kind"
          :group-name="groupName"
          :folder-name="folderName"
          :display-name="displayName"
          :editable="editable"
          @add-script="emit('add-script')"
        />
      </a-tab-pane>
    </a-tabs>

    <!-- 放大弹窗：更大编辑区居中显示。
         弹窗堆叠遵循「先开的在下、后开的在上」：放大弹窗作为底层 z-index 1000，
         内部双击项目再弹出的设置弹窗(1100)会盖在其上。 -->
    <a-modal
      v-model:open="zoomed"
      :title="zoomTitle"
      :footer="null"
      :width="860"
      centered
      :z-index="1000"
      wrap-class-name="bgi-project-zoom-modal"
      @cancel="zoomed = false"
    >
      <BettergiGroupProjectBody
        v-if="zoomed"
        :script-id="scriptId"
        :user-id="userId"
        :kind="kind"
        :group-name="groupName"
        :folder-name="folderName"
        :display-name="displayName"
        :editable="editable"
        @add-script="emit('add-script')"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FullscreenOutlined } from '@ant-design/icons-vue'
import BettergiGroupProjectBody from './BettergiGroupProjectBody.vue'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    scriptId: string
    userId: string
    groupName: string
    kind: 'scriptgroup' | 'js' | 'pathing' | string
    folderName?: string
    displayName?: string
    editable?: boolean
  }>(),
  {
    folderName: '',
    displayName: '',
    editable: false,
  }
)

const emit = defineEmits<{ (e: 'add-script'): void }>()

const bodyRef = ref<InstanceType<typeof BettergiGroupProjectBody> | null>(null)

const shellPaneKey = 'project-editor'
// 标签栏标题：来源类型（配置组/JS脚本/路径），与父级 detail header 的组名不重复
const shellTabLabel = computed<string>(() => {
  if (props.kind === 'scriptgroup') return t('edit.bettergiGroupKindScriptGroup')
  if (props.kind === 'pathing') return t('edit.bettergiGroupKindPathing')
  return t('edit.bettergiGroupKindCustom')
})
// 放大弹窗标题：当前组/脚本显示名
const zoomTitle = computed<string>(
  () => props.displayName || props.groupName || shellTabLabel.value
)

const zoomed = ref(false)

// 供父组件在「添加配置组弹窗(冻结配置组标签)」确认后把选中的 JS/路径追加并保存
defineExpose({
  reload: () => bodyRef.value?.reload(),
  addProjects: (rows: unknown[]) => bodyRef.value?.addProjects(rows as never[]),
  removeSelectedProjects: () => bodyRef.value?.removeSelectedProjects(),
})
</script>

<style scoped>
.bgi-project-shell {
  width: 100%;
}
.bgi-project-shell-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 10px;
}
.bgi-project-zoom-btn {
  color: var(--ant-color-text-secondary);
}
.bgi-project-zoom-btn:hover {
  color: var(--ant-color-primary);
}
/* 放大弹窗内充分利用空间 */
.bgi-project-zoom-modal :deep(.bgi-project-list),
.bgi-project-zoom-modal :deep(.bgi-project-settings-fields) {
  max-height: 62vh;
}
</style>
