import NoData from '@/components/NoData.vue'

declare module 'vue' {
  export interface GlobalComponents {
    NoData: typeof NoData
  }
}
