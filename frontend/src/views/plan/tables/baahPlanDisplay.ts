import type { Composer } from 'vue-i18n'
import {
  readFieldState,
  readFieldValues,
  type BAAHDayFields,
  type BAAHKeyFieldName,
} from '@/utils/baahPlanKey'

type Translate = Composer['t']
const REGION_LABEL_KEYS = [
  'one',
  'two',
  'three',
  'four',
  'five',
  'six',
  'seven',
  'eight',
  'nine',
  'ten',
]

export const baahRegionLabel = (value: number, t: Translate) => {
  const key = REGION_LABEL_KEYS[value - 1]
  return key ? t(`plan.baah.regions.${key}`) : t('plan.baah.regionNumber', { value })
}

/** 摘要不改变存储值；次数为零仍与关闭、交给 BAAH 分开显示。 */
export const baahCellSummary = (
  fields: BAAHDayFields | undefined,
  field: BAAHKeyFieldName,
  t: Translate
) => {
  const state = readFieldState(fields, field)
  if (state !== 'on')
    return {
      state,
      primary: t(state === 'off' ? 'plan.baah.stateOff' : 'plan.baah.stateAuto'),
      secondary: t(state === 'off' ? 'plan.baah.skipToday' : 'plan.baah.upstreamSettings'),
    }
  const values = readFieldValues(fields, field)
  const stage = values[1]
  const stageLabel =
    stage === -1 ? t('plan.baah.stageHighest') : t('plan.baah.stageNumber', { value: stage })
  let primary = stageLabel
  if (field === 'Wanted' || field === 'Special')
    primary = `${baahRegionLabel(values[0], t)} · ${stageLabel}`
  if (field === 'Exchange')
    primary = `${t('plan.baah.academyNumber', { value: values[0] })} · ${stageLabel}`
  if (field === 'Hard' || field === 'Normal') primary = `${values[0]}-${stage}`
  const times = values[2]
  return {
    state,
    primary,
    secondary:
      times === -1 ? t('plan.baah.timesMax') : t('plan.baah.timesNumber', { value: times }),
  }
}
