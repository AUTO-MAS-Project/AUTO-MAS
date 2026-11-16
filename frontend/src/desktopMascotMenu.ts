import { createApp } from 'vue'
import DesktopMascotMenu from './views/DesktopMascotMenu.vue'
import './styles/scrollbar.css'

// 独立弹层只消费菜单协议，不启动主界面的状态、连接或业务初始化。
createApp(DesktopMascotMenu).mount('#app')
