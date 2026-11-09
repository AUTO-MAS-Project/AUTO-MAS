<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLogHighlight } from '@/composables/useLogHighlight'
import { useDownloadLogStyle, sampleDownload } from '@/composables/useDownloadLogStyle'
import DownloadLogLine from './DownloadLogLine.vue'

const props = defineProps<{ editingTheme: 'light' | 'dark' }>()
const { t } = useI18n()
const { lightColors, darkColors, styles, editorConfig } = useLogHighlight()
const currentColors = computed(() =>
  props.editingTheme === 'dark' ? darkColors.value : lightColors.value
)
const { downloadClasses, downloadVariables } = useDownloadLogStyle(
  computed(() => props.editingTheme === 'dark')
)
</script>

<template>
  <div
    class="preview-content"
    :class="downloadClasses"
    :style="{
      ...downloadVariables,
      '--download-background': downloadVariables['--download-background'],
      '--download-foreground': downloadVariables['--download-foreground'],
      fontSize: editorConfig.fontSize + 'px',
      lineHeight: editorConfig.lineHeight,
    }"
  >
    <div class="preview-line">
      <span
        :style="{
          color: '#' + currentColors.timestamp,
          fontWeight: styles.timestampBold ? 'bold' : 'normal',
        }"
        >2024-12-09 10:30:45.123</span
      >
      <span
        :style="{
          color: '#' + currentColors.info,
          fontWeight: styles.levelBold ? 'bold' : 'normal',
        }"
      >
        INFO
      </span>
      <span :style="{ color: '#' + currentColors.module }">[MainModule]</span>
      <span>{{ t('core.comp.appStartedPort') }}</span>
      <span :style="{ color: '#' + currentColors.port }">:8080</span>
    </div>
    <div class="preview-line">
      <span
        :style="{
          color: '#' + currentColors.timestamp,
          fontWeight: styles.timestampBold ? 'bold' : 'normal',
        }"
        >2024-12-09 10:30:46.456</span
      >
      <span
        :style="{
          color: '#' + currentColors.warning,
          fontWeight: styles.levelBold ? 'bold' : 'normal',
        }"
      >
        WARN
      </span>
      <span :style="{ color: '#' + currentColors.module }">[Network]</span>
      <span>{{ t('core.comp.connectionTimedOutIp') }}</span>
      <span :style="{ color: '#' + currentColors.ip }">192.168.1.100</span>
      <span :style="{ color: '#' + currentColors.variable }"> retries</span>
      <span :style="{ color: '#' + currentColors.operator }">=</span>
      <span :style="{ color: '#' + currentColors.number }">3</span>
    </div>
    <div class="preview-line">
      <span
        :style="{
          color: '#' + currentColors.timestamp,
          fontWeight: styles.timestampBold ? 'bold' : 'normal',
        }"
        >2024-12-09 10:30:47.789</span
      >
      <span
        :style="{
          color: '#' + currentColors.error,
          fontWeight: styles.levelBold ? 'bold' : 'normal',
        }"
      >
        ERROR
      </span>
      <span :style="{ color: '#' + currentColors.module }">[Database]</span>
      <span
        :style="{
          color: '#' + currentColors.errorKeyword,
          fontWeight: styles.keywordBold ? 'bold' : 'normal',
        }"
      >
        Exception</span
      >
      <span>{{ t('core.comp.connectionFailed') }}</span>
      <span :style="{ color: '#' + currentColors.string }">"Connection refused"</span>
    </div>
    <div class="preview-line">
      <span :style="{ color: '#' + currentColors.stackTrace }">
        at com.example.Database.connect(Database.java:42)</span
      >
    </div>
    <div class="preview-line">
      <span
        :style="{
          color: '#' + currentColors.timestamp,
          fontWeight: styles.timestampBold ? 'bold' : 'normal',
        }"
        >2024-12-09 10:30:48.000</span
      >
      <span :style="{ color: '#' + currentColors.debug }"> DEBUG </span>
      <span :style="{ color: '#' + currentColors.module }">[Task]</span>
      <span> UUID: </span>
      <span :style="{ color: '#' + currentColors.uuid }">550e8400-e29b-41d4-a716-446655440000</span>
    </div>
    <div class="preview-line">
      <span
        :style="{
          color: '#' + currentColors.timestamp,
          fontWeight: styles.timestampBold ? 'bold' : 'normal',
        }"
        >2024-12-09 10:30:49.123</span
      >
      <span :style="{ color: '#' + currentColors.trace }"> TRACE </span>
      <span :style="{ color: '#' + currentColors.module }">[HTTP]</span>
      <span>{{ t('core.comp.request') }}</span>
      <span
        :style="{
          color: '#' + currentColors.url,
          textDecoration: styles.urlUnderline ? 'underline' : 'none',
        }"
        >https://api.example.com/data</span
      >
      <span
        :style="{
          color: '#' + currentColors.success,
          fontWeight: styles.keywordBold ? 'bold' : 'normal',
        }"
      >
        Success</span
      >
    </div>
    <div class="preview-line">
      <span :style="{ color: '#' + currentColors.trace }"> TRACE </span>
      <span>{{ t('core.comp.response') }}</span>
      <span :style="{ color: '#' + currentColors.json }">{"status": "ok", "count": 42}</span>
      <span> enabled</span>
      <span :style="{ color: '#' + currentColors.operator }">=</span>
      <span :style="{ color: '#' + currentColors.boolean }">true</span>
    </div>
    <DownloadLogLine :data="sampleDownload" />
  </div>
</template>

<style scoped>
.preview-content {
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, Courier, monospace;
}

.preview-line {
  white-space: nowrap;
}

.preview-content {
  background: var(--download-background);
  color: var(--download-foreground);
}
</style>
<style src="./downloadLog.css"></style>
