<template>
  <div style="padding: 20px;">
    <h2>脚本API测试</h2>
    <a-space>
      <a-button type="primary" @click="testAddMAA" :loading="loading">
        测试添加MAA脚本
      </a-button>
      <a-button type="primary" @click="testAddGeneral" :loading="loading">
        测试添加General脚本
      </a-button>
      <a-button @click="goToScripts">
        前往脚本管理页面
      </a-button>
    </a-space>
    
    <div v-if="result" style="margin-top: 20px;">
      <h3>API响应结果：</h3>
      <pre>{{ JSON.stringify(result, null, 2) }}</pre>
      
      <a-space style="margin-top: 10px;">
        <a-button type="primary" @click="goToEdit">
          前往编辑页面
        </a-button>
      </a-space>
    </div>
    
    <div v-if="error" style="margin-top: 20px; color: red;">
      <h3>错误信息：</h3>
      <p>{{ error }}</p>
    </div>

    <div style="margin-top: 30px;">
      <h3>测试说明：</h3>
      <ul>
        <li>点击"测试添加MAA脚本"或"测试添加General脚本"来测试API调用</li>
        <li>成功后会显示API返回的数据，包含scriptId和配置信息</li>
        <li>点击"前往编辑页面"可以跳转到编辑页面查看配置</li>
        <li>或者直接前往脚本管理页面测试完整流程</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useScriptApi } from '@/composables/useScriptApi'

const router = useRouter()
const { addScript, loading, error } = useScriptApi()
const result = ref<any>(null)
const lastScriptType = ref<'MAA' | 'General'>('MAA')

const testAddMAA = async () => {
  result.value = null
  lastScriptType.value = 'MAA'
  const response = await addScript('MAA')
  if (response) {
    result.value = response
  }
}

const testAddGeneral = async () => {
  result.value = null
  lastScriptType.value = 'General'
  const response = await addScript('General')
  if (response) {
    result.value = response
  }
}

const goToEdit = () => {
  if (result.value) {
    router.push({
      path: `/scripts/${result.value.scriptId}/edit`,
      state: {
        scriptData: {
          id: result.value.scriptId,
          type: lastScriptType.value,
          config: result.value.data
        }
      }
    })
  }
}

const goToScripts = () => {
  router.push('/scripts')
}
</script>