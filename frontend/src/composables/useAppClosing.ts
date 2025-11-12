import { ref, readonly } from 'vue'

// 全局状态：应用是否正在关闭
const isClosing = ref(false)

export function useAppClosing() {
  const showClosingOverlay = () => {
    isClosing.value = true
  }

  const hideClosingOverlay = () => {
    isClosing.value = false
  }

  return {
    isClosing: readonly(isClosing),
    showClosingOverlay,
    hideClosingOverlay,
  }
}
