import { createApp } from 'vue'
import DesktopMascot from './views/DesktopMascot.vue'

// 独立入口只绘制桌宠，不启动主界面的 WebSocket、更新轮询或初始化流程。
createApp(DesktopMascot).mount('#app')
