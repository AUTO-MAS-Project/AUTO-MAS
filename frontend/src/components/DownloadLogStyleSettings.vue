<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useLogHighlight } from '@/composables/useLogHighlight'
import {
  downloadFields,
  downloadFamilies,
  downloadColorKey,
  type DownloadField,
} from '@/composables/useDownloadLogStyle'

const { t } = useI18n()
const props = defineProps<{ editingTheme: 'light' | 'dark' }>()
const {
  styles,
  setStyles,
  defaultStyles,
  lightColors,
  darkColors,
  defaultLightColors,
  defaultDarkColors,
  setLightColors,
  setDarkColors,
} = useLogHighlight()
const currentColors = computed(() =>
  props.editingTheme === 'light' ? lightColors.value : darkColors.value
)
const setFamily = (field: DownloadField, family: string) => {
  setStyles({ downloadFamilies: { ...styles.value.downloadFamilies, [field]: family } })
}
const updateColor = (field: DownloadField, value: string) => {
  const colors = { [downloadColorKey(field)]: value.replace('#', '') }
  if (props.editingTheme === 'light') setLightColors(colors)
  else setDarkColors(colors)
}
const resetField = (field: DownloadField) => {
  if (styles.value.downloadGradient) setFamily(field, defaultStyles.downloadFamilies[field])
  else {
    const colors = props.editingTheme === 'light' ? defaultLightColors : defaultDarkColors
    updateColor(field, colors[downloadColorKey(field)])
  }
}
</script>

<template>
  <div class="color-group">
    <div class="group-title">{{ t('core.comp.downloadHighlight') }}</div>
    <div class="download-style-toolbar">
      <label class="download-style-control">
        <span>{{ t('core.comp.downloadGradientSpeed') }}</span>
        <a-select
          size="small"
          class="speed-select"
          :disabled="!styles.downloadGradient"
          :value="styles.downloadGradientSeconds"
          :aria-label="t('core.comp.downloadGradientSpeed')"
          @change="(value: number) => setStyles({ downloadGradientSeconds: value })"
        >
          <a-select-option v-for="seconds in [0.5, 1, 2, 4]" :key="seconds" :value="seconds">{{
            t('core.comp.downloadCycle', { seconds })
          }}</a-select-option>
        </a-select>
      </label>
      <label class="download-style-control">
        <span>{{ t('core.comp.downloadGradientContrast') }}</span>
        <a-input-number
          size="small"
          class="contrast-input"
          :disabled="!styles.downloadGradient"
          :value="styles.downloadGradientContrast"
          :min="10"
          :max="100"
          :step="5"
          :aria-label="t('core.comp.downloadGradientContrast')"
          @change="
            (value: number | null) =>
              value !== null && setStyles({ downloadGradientContrast: value })
          "
        />
        <span>%</span>
      </label>
      <label class="download-style-control">
        <span>{{ t('core.comp.downloadGradient') }}</span>
        <a-switch
          size="small"
          :checked="styles.downloadGradient"
          @change="(value: boolean) => setStyles({ downloadGradient: value })"
        />
      </label>
    </div>
    <div class="color-grid">
      <div v-for="field in downloadFields" :key="field" class="color-item">
        <div class="color-info">
          <span class="color-label">{{ t(`core.comp.${downloadColorKey(field)}`) }}</span>
          <a-tooltip :title="t(`core.comp.${downloadColorKey(field)}`)"
            ><QuestionCircleOutlined class="help-icon"
          /></a-tooltip>
        </div>
        <div class="color-controls">
          <a-select
            v-if="styles.downloadGradient"
            size="small"
            class="family-select"
            :aria-label="t(`core.comp.${downloadColorKey(field)}`)"
            :value="styles.downloadFamilies[field]"
            @change="(value: string) => setFamily(field, value)"
          >
            <a-select-option
              v-for="(_, family) in downloadFamilies"
              :key="family"
              :value="family"
              >{{ t(`core.comp.downloadFamily${family}`) }}</a-select-option
            >
          </a-select>
          <template v-else>
            <input
              type="color"
              :value="'#' + currentColors[downloadColorKey(field)]"
              class="color-picker"
              :aria-label="t(`core.comp.${downloadColorKey(field)}`)"
              @input="
                (event: Event) => updateColor(field, (event.target as HTMLInputElement).value)
              "
            />
            <span class="color-value">#{{ currentColors[downloadColorKey(field)] }}</span>
          </template>
          <a-button
            size="small"
            type="text"
            :title="t('core.comp.resetThisColor')"
            @click="resetField(field)"
            ><template #icon><ReloadOutlined /></template
          ></a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="./logHighlightColors.css"></style>
<style scoped>
.download-style-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 8px;
}
.download-style-control {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
.speed-select {
  width: 84px;
}
.contrast-input {
  width: 64px;
}
.family-select {
  width: 100px;
}
</style>
