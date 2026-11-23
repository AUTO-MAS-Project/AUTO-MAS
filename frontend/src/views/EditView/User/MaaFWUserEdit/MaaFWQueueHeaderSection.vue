<template>
  <!-- MaaFW 是通用引擎，没有可退回的原生配置：三态来源与快速配置开关对它没有所指，
       任务队列始终显示。两个字段仍留在配置模型里，只是不再提供入口。 -->
  <SectionCard
    variant="plain"
    :title="t('core.edit.taskQueueConfiguration')"
    class="queue-header-section"
  >
    <template #actions>
      <a-space>
        <!-- 从本脚本的其他用户、或外壳（MFAAvalonia / MXU / MFW-PyQt6）把配好的队列搬过来：
             引导最后一步只在新建脚本时走一次，脚本建好之后再同步就走这里 -->
        <ShellQueueImportSection
          :user-candidates="userImportCandidates"
          :user-loading="userImportLoading"
          @load-users="emit('load-user-import')"
          @import-from-user="userId => emit('import-from-user', userId)"
          @imported="(snapshot, info) => emit('imported', snapshot, info)"
        />
        <a-button size="small" @click="emit('open-restore')">
          <template #icon>
            <HistoryOutlined />
          </template>
          {{ t('core.edit.configRestoreTitle') }}
        </a-button>
      </a-space>
    </template>
    <!-- 特调的队列提示（如 MSS 的爬塔排序）与不可选任务的提示；一条提示一个框：挤在一个框里
         读起来还是一坨 -->
    <a-alert
      v-for="(line, index) in queueHintLines"
      :key="index"
      class="flavor-queue-hint"
      type="info"
      show-icon
      :message="line"
    />
    <!-- 队列里还残留受管任务：照常显示。真要拆用户时是警告，其余（如刚导入成 M9A 带进来的
         启动 / 关闭）是轻提示，下次保存或重启会移出队列 -->
    <a-alert
      v-if="managedQueueAlert"
      class="flavor-queue-hint"
      :type="managedQueueAlert.type"
      show-icon
      :message="managedQueueAlert.message"
    />
  </SectionCard>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { HistoryOutlined } from '@ant-design/icons-vue'
import { SectionCard } from '@/components/ui'
import type {
  MaaFWUserQueueHeaderSectionEmits,
  MaaFWUserQueueHeaderSectionProps,
} from '../../MaaFWFlavor/sectionContracts'
import ShellQueueImportSection from './ShellQueueImportSection.vue'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
defineProps<MaaFWUserQueueHeaderSectionProps>()

const emit = defineEmits<MaaFWUserQueueHeaderSectionEmits>()
</script>

<style scoped>
.queue-header-section {
  margin-bottom: 0;
}

/* 每条提示一个框（文案里用 \n 分行），框之间留点空 */
.flavor-queue-hint {
  margin-bottom: 8px;
}
</style>
