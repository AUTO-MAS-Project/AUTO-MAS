import { h } from 'vue'
import NoData from './NoData.vue'

const compactComponents = new Set(['Select', 'TreeSelect', 'Cascader', 'Transfer', 'Mentions'])

export function renderEmpty(componentName?: string) {
  return h(
    NoData,
    componentName && compactComponents.has(componentName)
      ? { class: 'ant-empty-small', imageStyle: { height: '48px' } }
      : {}
  )
}
