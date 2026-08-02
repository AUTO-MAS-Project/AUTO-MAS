<template>
  <div class="direct-control-section">
    <div class="section-header"><h3>脚本直控</h3></div>
    <a-alert
      type="info"
      show-icon
      message="MAS 只负责先启动游戏、跟踪/停止脚本进程和最终游戏清理；登录、任务、兑换码及完成后动作均按导入的原生配置执行。"
      class="direct-alert"
    />

    <a-empty v-if="availableEngines.length === 0" description="当前没有可用的 SRA / 三月七助手" />
    <div v-else class="engine-grid">
      <div v-for="engine in availableEngines" :key="engine" class="engine-card">
        <div class="engine-card-header">
          <div>
            <div class="engine-name">{{ engineLabel(engine) }}</div>
            <div class="engine-description">{{ engineDescription(engine) }}</div>
          </div>
          <a-switch
            :checked="Boolean(control[engine])"
            :disabled="saving"
            checked-children="执行"
            un-checked-children="跳过"
            @change="emit('toggle', engine, Boolean($event))"
          />
        </div>

        <div class="import-state" :class="{ 'import-state-ready': importedAt(engine) }">
          <CheckCircleOutlined v-if="importedAt(engine)" />
          <InfoCircleOutlined v-else />
          <div>
            <div>{{ importedAt(engine) ? '已导入用户快照' : '尚未导入用户快照' }}</div>
            <div v-if="importedAt(engine)" class="import-meta">
              {{ source(engine) }} · {{ importedAt(engine) }}
            </div>
          </div>
        </div>

        <a-space wrap>
          <a-button
            :disabled="saving || !configuratorReady(engine)"
            :loading="openingEngine === engine"
            @click="emit('openConfigurator', engine)"
          >
            重新配置
          </a-button>
          <a-button
            type="primary"
            :disabled="saving"
            :loading="importingEngine === engine"
            @click="emit('importConfig', engine)"
          >
            一键从源配置导入
          </a-button>
        </a-space>
        <a-typography-text v-if="configuratorReason(engine)" type="secondary" class="reason">
          {{ configuratorReason(engine) }}
        </a-typography-text>
      </div>
    </div>

    <a-alert
      v-if="selectedEngines.length === 0"
      type="warning"
      show-icon
      message="请至少启用一个直控脚本。"
      class="direct-alert bottom-alert"
    />
    <a-alert
      v-else-if="selectedEngines.some(engine => !importedAt(engine))"
      type="warning"
      show-icon
      message="已启用的脚本必须先导入用户快照，任务启动检查才会通过。"
      class="direct-alert bottom-alert"
    />

    <div class="managed-mask-preview">
      <div class="mask-copy">
        <LockOutlined />
        <div>
          <strong>MAS 管控配置已停用</strong>
          <span>任务开关、账号、体力副本和动态选项在脚本直控模式下都不会生效。</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircleOutlined, InfoCircleOutlined, LockOutlined } from '@ant-design/icons-vue'
import type { HSREngine, HSRNativeControlSnapshot } from '@/composables/useHSRPluginApi'
import type { HSRUserConfigData } from '@/views/HSRUserEdit/types'

const props = defineProps<{
  availableEngines: HSREngine[]
  control: HSRUserConfigData['Control']
  direct: HSRUserConfigData['Direct']
  nativeControls: Partial<Record<HSREngine, HSRNativeControlSnapshot>>
  saving: boolean
  importingEngine: HSREngine | null
  openingEngine: HSREngine | null
}>()

const emit = defineEmits<{
  toggle: [engine: HSREngine, enabled: boolean]
  importConfig: [engine: HSREngine]
  openConfigurator: [engine: HSREngine]
}>()

const selectedEngines = computed(() =>
  props.availableEngines.filter(engine => Boolean(props.control[engine]))
)

const engineLabel = (engine: HSREngine) => (engine === 'M7A' ? '三月七助手 CLI' : 'SRA CLI')
const engineDescription = (engine: HSREngine) =>
  engine === 'M7A' ? '执行导入的 config.yaml 快照' : '执行导入的 SRA JSON 配置快照'
const importedAt = (engine: HSREngine) =>
  String(props.direct[`${engine}ImportedAt` as keyof HSRUserConfigData['Direct']] || '')
const source = (engine: HSREngine) =>
  String(props.direct[`${engine}Source` as keyof HSRUserConfigData['Direct']] || '')
const configuratorReady = (engine: HSREngine) =>
  props.nativeControls[engine]?.configurator_ready !== false
const configuratorReason = (engine: HSREngine) =>
  props.nativeControls[engine]?.configurator_reason || ''
</script>

<style scoped>
.direct-control-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.section-header h3::before {
  width: 4px;
  height: 20px;
  border-radius: 2px;
  background: var(--ant-color-primary);
  content: '';
}

.direct-alert {
  margin-bottom: 16px;
}

.engine-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.engine-card {
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-bg-container);
}

.engine-card-header,
.import-state,
.mask-copy {
  display: flex;
  align-items: center;
}

.engine-card-header {
  justify-content: space-between;
  gap: 16px;
}

.engine-name {
  font-size: 17px;
  font-weight: 700;
}

.engine-description,
.import-meta,
.reason,
.mask-copy span {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.import-state {
  gap: 10px;
  margin: 16px 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-warning);
}

.import-state-ready {
  color: var(--ant-color-success);
}

.import-meta {
  overflow: hidden;
  max-width: 520px;
  margin-top: 3px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reason {
  display: block;
  margin-top: 10px;
}

.bottom-alert {
  margin-top: 16px;
}

.managed-mask-preview {
  position: relative;
  min-height: 120px;
  margin-top: 20px;
  overflow: hidden;
  border: 1px dashed var(--ant-color-border);
  border-radius: 10px;
  background:
    linear-gradient(rgb(255 255 255 / 72%), rgb(255 255 255 / 72%)),
    repeating-linear-gradient(
      135deg,
      var(--ant-color-fill-quaternary) 0 14px,
      transparent 14px 28px
    );
}

.mask-copy {
  position: absolute;
  inset: 0;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: left;
}

.mask-copy strong,
.mask-copy span {
  display: block;
}
</style>
