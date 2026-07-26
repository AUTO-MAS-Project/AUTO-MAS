<script setup lang="ts">
/**
 * Lane 8：游戏签到 - 编辑 Token 模态框。
 *
 * 从 TabGameSign.vue 拆分。负责编辑账号名称和三个平台 Token，
 * 并触发米游社扫码登录。
 */
import { QrcodeOutlined } from '@ant-design/icons-vue'

export interface EditableAccount {
  uid: string
  Name: string
  MiyousheToken: string
  KuroToken: string
  SklandToken: string
}

defineProps<{
  visible: boolean
  account: EditableAccount | null
  qrLoading: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  save: []
  'start-qr': []
}>()
</script>

<template>
  <a-modal
    :open="visible"
    :title="`编辑 — ${account?.Name || ''}`"
    ok-text="保存"
    cancel-text="取消"
    :width="560"
    @ok="emit('save')"
    @cancel="emit('update:visible', false)"
  >
    <div v-if="account" class="modal-form">
      <div class="form-item-vertical">
        <span class="form-label">用户名称</span>
        <a-input v-model:value="account.Name" size="large" />
      </div>
      <a-divider orientation="left" class="community-divider">米游社</a-divider>
      <div class="form-item-vertical">
        <a-input-password
          v-model:value="account.MiyousheToken"
          size="large"
          placeholder="浏览器 F12 → document.cookie 获取"
          allow-clear
        />
        <a-button
          size="small"
          style="margin-top: 6px"
          :loading="qrLoading"
          @click="emit('start-qr')"
        >
          <template #icon><QrcodeOutlined /></template>
          扫码登录获取 Token
        </a-button>
      </div>
      <a-divider orientation="left" class="community-divider">库街区</a-divider>
      <div class="form-item-vertical">
        <a-input-password
          v-model:value="account.KuroToken"
          size="large"
          placeholder="抓包或短信验证码获取 Token"
          allow-clear
        />
      </div>
      <a-divider orientation="left" class="community-divider">森空岛</a-divider>
      <div class="form-item-vertical">
        <a-input-password
          v-model:value="account.SklandToken"
          size="large"
          placeholder="鹰角网络通行证登录凭证"
          allow-clear
        />
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.modal-form .form-item-vertical {
  margin-bottom: 16px;
}

.community-divider {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
</style>
