<template>
  <!-- MaaFW 是通用引擎，没有可退回的原生配置：三态来源与快速配置开关对它没有所指，
       任务队列始终显示。两个字段仍留在配置模型里，只是不再提供入口。 -->
  <a-flex class="section-header" justify="space-between" align="center" wrap="wrap" gap="small">
    <h3>{{ t('edit.taskQueueConfiguration') }}</h3>
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
        {{ t('edit.configRestoreTitle') }}
      </a-button>
    </a-space>
  </a-flex>
  <!-- 特调类型（M9A）的受管任务（启动 / 切号 / 关闭）由后端全权控制：「添加任务」与预设里
       都没有它们；一条提示一个框：挤在一个框里读起来还是一坨 -->
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
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { HistoryOutlined } from '@ant-design/icons-vue'
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
/* 每条提示一个框（文案里用 \n 分行），框之间留点空 */
.flavor-queue-hint {
  margin-bottom: 8px;
}

.flavor-queue-hint-last {
  margin-bottom: 16px;
}
</style>
