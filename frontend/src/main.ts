import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.ts'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

createApp(App).use(Antd).use(router).mount('#app')
