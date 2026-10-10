import { defineComponent, watch } from 'vue'
import { theme } from 'ant-design-vue'
import { useTheme } from '@/composables/useTheme'

// 必须作为 ConfigProvider 的子组件，才能取得组件实际使用的最终 alias token。
export default defineComponent({
  name: 'ThemeTokenBridge',
  setup() {
    const { token } = theme.useToken()
    const { syncAntTokens } = useTheme()
    watch(token, syncAntTokens, { immediate: true, flush: 'sync' })
    return () => null
  },
})
