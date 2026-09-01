<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">{{ t('edit.scripts') }}</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/bettergi`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? t('comp.editUser') : t('comp.addUser2') }}
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <a-space size="middle">
        <a-tooltip
          v-if="!showBettergiConfigMask && !pageLoading && formData.Info.IfUseMasConfig"
          placement="bottom"
        >
          <template #title>
            <span style="white-space: normal">
              {{ t('edit.bettergiMasConfigTooltip') }}
            </span>
          </template>
          <a-button
            type="primary"
            ghost
            size="large"
            :loading="bettergiConfigLoading"
            :disabled="pageLoading || !userId"
            @click="handleBettergiConfig"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            {{ t('edit.bettergiConfigure') }}
          </a-button>
        </a-tooltip>
        <a-button
          v-else-if="!showBettergiConfigMask"
          type="primary"
          ghost
          size="large"
          :loading="bettergiConfigLoading"
          :disabled="pageLoading || !userId"
          @click="handleBettergiConfig"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          {{ t('edit.bettergiConfigure') }}
        </a-button>
        <a-button v-else type="default" size="large" disabled class="configuring-button">
          <template #icon>
            <SettingOutlined />
          </template>
          {{ t('edit.configuring') }}
        </a-button>
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          {{ t('edit.back') }}
        </a-button>
      </a-space>
    </div>

    <teleport to="body">
      <div v-if="showBettergiConfigMask" class="bettergi-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">{{ t('edit.bettergiConfiguringTitle') }}</h2>
          <p class="mask-description">
            {{ t('edit.bettergiConfiguringDesc') }}
            <br />
            {{ t('edit.bettergiConfiguringDesc2') }}
          </p>
          <div class="mask-actions">
            <a-button
              v-if="bettergiWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveBettergiConfig"
            >
              {{ t('edit.saveSettings') }}
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

    <div class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.basicInfo') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.username') }}
                      <a-tooltip :title="t('edit.bettergiUserNameHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    :placeholder="t('edit.enterUsername')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Name', formData.userName)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.enabled') }}
                      <a-tooltip :title="t('edit.whetherThisUserEnabled')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    class="modern-select"
                    @change="saveField('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                    <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiAccount') }}
                      <a-tooltip :title="t('edit.bettergiAccountHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    :placeholder="t('edit.bettergiEnterAccount')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiAccountUid') }}
                      <a-tooltip :title="t('edit.bettergiUidHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Switch.Uid"
                    :placeholder="t('edit.bettergiEnterUid')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Switch.Uid', formData.Switch.Uid)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.password') }}
                      <a-tooltip :title="t('edit.bettergiPasswordHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    :placeholder="t('edit.bettergiEnterPasswordPlaceholder')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Password', formData.Info.Password)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiGameServer') }}
                      <a-tooltip :title="t('edit.bettergiGameServerHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Switch.Resource"
                    size="large"
                    class="modern-select"
                    @change="saveField('Switch.Resource', formData.Switch.Resource)"
                  >
                    <a-select-option value="官服">{{ t('edit.bettergiServerCn') }}</a-select-option>
                    <a-select-option value="B服">{{
                      t('edit.bettergiServerBili')
                    }}</a-select-option>
                    <a-select-option value="亚服">{{
                      t('edit.bettergiServerAsia')
                    }}</a-select-option>
                    <a-select-option value="欧服">{{
                      t('edit.bettergiServerEurope')
                    }}</a-select-option>
                    <a-select-option value="美服">{{
                      t('edit.bettergiServerAmerica')
                    }}</a-select-option>
                    <a-select-option value="港澳台服">
                      {{ t('edit.bettergiServerTwHkMo') }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.daysLeft') }}
                      <a-tooltip :title="t('edit.daysLeftAccount1')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-number
                    v-model:value="formData.Info.RemainedDay"
                    :min="-1"
                    :max="9999"
                    size="large"
                    style="width: 100%"
                    @blur="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="24">
                <GeneralConfigModeSelector
                  :model-value="formData.Info.IfUseMasConfig"
                  :disabled="pageLoading"
                  :saving="configModeSaving"
                  @change="handleConfigModeChange"
                />
              </a-col>
            </a-row>

            <a-form-item>
              <template #label>
                <span class="form-label">
                  {{ t('edit.note') }}
                  <a-tooltip :title="t('edit.addNoteAboutThis')">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </span>
              </template>
              <a-textarea
                v-model:value="formData.Info.Notes"
                :placeholder="t('edit.enterNote')"
                :rows="4"
                class="modern-input"
                @blur="saveField('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </div>
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>
                {{ t('edit.taskConfiguration') }}
                <a-tooltip :title="t('edit.bettergiTaskConfigHint')">
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </h3>
            </div>

            <a-alert
              v-if="!formData.Info.IfUseMasConfig"
              type="warning"
              show-icon
              class="mode-guide-alert"
            >
              <template #message>
                <span class="mode-guide-message">
                  {{ t('edit.bettergiDirectModeAlert') }}
                </span>
              </template>
              <template #action>
                <a-button
                  type="primary"
                  size="small"
                  :loading="configModeSaving"
                  @click="handleConfigModeChange(true)"
                >
                  {{ t('edit.bettergiSwitchToMasConfig') }}
                </a-button>
              </template>
            </a-alert>

            <a-alert
              v-if="formData.Info.IfUseMasConfig"
              type="info"
              show-icon
              class="mode-guide-alert config-flow-hint"
            >
              <template #message>
                <span class="config-flow-title">{{ t('edit.bettergiMasConfigHowTo') }}</span>
              </template>
              <template #description>
                <p class="config-flow-desc config-flow-p">
                  {{ t('edit.bettergiMasConfigHowTo1a') }}
                  <b>{{ t('edit.bettergiMasConfigSlotName') }}</b>
                  {{ t('edit.bettergiMasConfigHowTo1b') }}
                </p>
                <p class="config-flow-desc config-flow-p">
                  {{ t('edit.bettergiMasConfigHowTo2') }}
                </p>
              </template>
            </a-alert>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      <span class="required-mark">*</span>
                      {{ t('edit.bettergiOneDragonName') }}
                      <a-tooltip :title="t('edit.bettergiOneDragonNameHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Task.OneDragonConfigName"
                    :options="oneDragonConfigOptions"
                    :placeholder="t('edit.bettergiPickOneDragonName')"
                    size="large"
                    show-search
                    option-filter-prop="label"
                    class="modern-input"
                    @dropdown-visible-change="
                      (open: boolean) => {
                        if (open) void loadOneDragonConfigs()
                      }
                    "
                    @change="
                      saveField('Task.OneDragonConfigName', formData.Task.OneDragonConfigName)
                    "
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiDailyRewardParty') }}
                      <a-tooltip :title="t('edit.bettergiKeepExistingHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.OneDragon.DailyRewardPartyName"
                    :disabled="!formData.Info.IfUseMasConfig"
                    :placeholder="t('edit.bettergiEnterDailyRewardParty')"
                    size="large"
                    class="modern-input"
                    @blur="
                      saveField(
                        'OneDragon.DailyRewardPartyName',
                        formData.OneDragon.DailyRewardPartyName
                      )
                    "
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiBattleParty') }}
                      <a-tooltip :title="t('edit.bettergiKeepExistingHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.OneDragon.PartyName"
                    :disabled="!formData.Info.IfUseMasConfig"
                    :placeholder="t('edit.bettergiEnterBattleParty')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('OneDragon.PartyName', formData.OneDragon.PartyName)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiBattleStrategy') }}
                      <a-tooltip :title="t('edit.bettergiBattleStrategyHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.OneDragon.AutoBossStrategyName"
                    :disabled="!formData.Info.IfUseMasConfig"
                    :placeholder="t('edit.bettergiEnterBattleStrategy')"
                    size="large"
                    :options="strategyOptions"
                    allow-clear
                    show-search
                    option-filter-prop="label"
                    class="modern-input"
                    @dropdown-visible-change="
                      (open: boolean) => {
                        if (open) void loadStrategyOptions()
                      }
                    "
                    @change="
                      saveField(
                        'OneDragon.AutoBossStrategyName',
                        formData.OneDragon.AutoBossStrategyName
                      )
                    "
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <p class="config-group-hint">
              {{ t('edit.bettergiGroupCapsuleHint') }}
            </p>

            <div class="config-group-grid">
              <div
                v-for="option in oneDragonGroupOptions"
                :key="option.value"
                class="config-group-item"
                :class="{ disabled: !formData.Info.IfUseMasConfig }"
                @click="toggleGroup(option.value)"
              >
                <span class="config-group-item-label">{{ option.label }}</span>
                <div
                  class="config-group-item-capsule"
                  :class="{ active: formData.OneDragon.Groups.includes(option.value) }"
                >
                  <span class="config-group-item-dot"></span>
                </div>
              </div>
            </div>

            <div class="custom-groups-section">
              <div class="custom-groups-header">
                <h3>
                  {{ t('edit.bettergiCustomGroups') }}
                  <a-tooltip placement="top">
                    <template #title>
                      <div style="max-width: 320px; white-space: normal">
                        {{ t('edit.bettergiCustomGroupsTip1') }}
                        <br /><br />
                        {{ t('edit.bettergiCustomGroupsTip2a') }}
                        <b>{{ t('edit.bettergiCustomGroupsDefaultRun') }}</b>
                        {{ t('edit.bettergiCustomGroupsTip2b') }}
                        <br /><br />
                        {{ t('edit.bettergiCustomGroupsTip3') }}
                      </div>
                    </template>
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </h3>
                <div class="custom-groups-toggle">
                  <span class="custom-groups-toggle-label">{{ t('edit.enabled2') }}</span>
                  <div
                    class="config-group-item-capsule custom-groups-capsule"
                    :class="{
                      active: formData.OneDragon.IfUseCustomGroups,
                      disabled: !formData.Info.IfUseMasConfig,
                    }"
                    @click="toggleCustomGroupsMaster"
                  >
                    <span class="config-group-item-dot"></span>
                  </div>
                </div>
              </div>

              <p class="section-desc custom-groups-desc">
                {{ t('edit.bettergiCustomGroupsDesc') }}
              </p>

              <div
                v-if="formData.OneDragon.IfUseCustomGroups && formData.Info.IfUseMasConfig"
                class="custom-groups-body"
              >
                <div class="custom-groups-toolbar">
                  <a-button size="small" type="primary" ghost @click="openCustomGroupModal">
                    {{ t('edit.bettergiAddGroup') }}
                  </a-button>
                  <a-popconfirm
                    :title="t('edit.bettergiDeleteGroupConfirm')"
                    :disabled="selectedCustomGroupKeys.length === 0"
                    @confirm="deleteSelectedCustomGroups"
                  >
                    <a-button size="small" danger :disabled="selectedCustomGroupKeys.length === 0">
                      {{ t('edit.deleteSelected') }}
                    </a-button>
                  </a-popconfirm>
                </div>
                <a-table
                  :columns="customGroupColumns"
                  :data-source="customGroupsTable"
                  :row-selection="customGroupRowSelection"
                  :pagination="false"
                  size="small"
                  :scroll="{ x: 320 }"
                  row-key="name"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'enabled'">
                      <div
                        class="config-group-item-capsule custom-groups-capsule"
                        :class="{ active: record.enabled }"
                        @click="toggleCustomGroupEnabled(record)"
                      >
                        <span class="config-group-item-dot"></span>
                      </div>
                    </template>
                  </template>
                </a-table>
              </div>
            </div>
          </div>

          <!-- 添加配置组弹窗 -->
          <a-modal
            v-model:open="customGroupModal.open"
            :title="t('edit.bettergiAddGroup')"
            :ok-text="
              customGroupModal.saving ? t('edit.bettergiAdding') : t('edit.bettergiAddAction')
            "
            :ok-button-props="{ disabled: customGroupModal.saving }"
            @ok="confirmAddCustomGroup"
            @cancel="customGroupModal.open = false"
          >
            <a-select
              v-model:value="customGroupModal.name"
              :options="customGroupModal.addOptions"
              :placeholder="t('edit.bettergiPickExistingGroup')"
              show-search
              allow-clear
              style="width: 100%"
              option-filter-prop="label"
            />
          </a-modal>
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.notificationSettings') }}</h3>
            </div>
            <a-row :gutter="24" align="middle">
              <a-col :span="6">
                <span style="font-weight: 500">{{ t('edit.enableNotifications') }}</span>
              </a-col>
              <a-col :span="18">
                <a-switch
                  v-model:checked="formData.Notify.Enabled"
                  @change="saveField('Notify.Enabled', formData.Notify.Enabled)"
                />
              </a-col>
            </a-row>

            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <span style="font-weight: 500">{{ t('edit.notificationContent') }}</span>
              </a-col>
              <a-col :span="18">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendStatistic"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
                >
                  {{ t('edit.notifyStatistics') }}
                </a-checkbox>
              </a-col>
            </a-row>

            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendMail"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendMail', formData.Notify.IfSendMail)"
                >
                  {{ t('edit.notifyMail') }}
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ToAddress"
                  :placeholder="t('edit.enterRecipientAddress')"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfSendMail"
                  size="large"
                  @blur="saveField('Notify.ToAddress', formData.Notify.ToAddress)"
                />
              </a-col>
            </a-row>

            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfServerChan"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfServerChan', formData.Notify.IfServerChan)"
                >
                  {{ t('edit.notifyServerChan') }}
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ServerChanKey"
                  :placeholder="t('edit.enterSendkey')"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfServerChan"
                  size="large"
                  @blur="saveField('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                />
              </a-col>
            </a-row>

            <div style="margin-top: 16px">
              <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
            </div>
          </div>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { BettergiService, type ComboBoxItem, type BetterGIUserConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useBettergiGuiSession } from '@/composables/useBettergiGuiSession'
import { useBettergiCustomGroups } from '@/composables/useBettergiCustomGroups'
import WebhookManager from '@/components/WebhookManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser, error: userApiError } = useUserApi()
const { getScript } = useScriptApi()

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref(t('edit.bettergiScriptFallbackName'))

const pageLoading = ref(true)
const isInitializing = ref(true)
const configModeSaving = ref(false)

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type BetterGIUserFormData = {
  userName: string
  Info: FormSection<NonNullable<BetterGIUserConfig['Info']>>
  Task: FormSection<NonNullable<BetterGIUserConfig['Task']>>
  Switch: FormSection<NonNullable<BetterGIUserConfig['Switch']>>
  OneDragon: FormSection<NonNullable<BetterGIUserConfig['OneDragon']>>
  Notify: FormSection<NonNullable<BetterGIUserConfig['Notify']>>
}

// 一条龙内置配置组（与后端 BetterGIUserConfig.OneDragon.Groups 的默认项保持一致）。
// value 参与后端判定，保持中文原样；只有显示名接词表。
const ONE_DRAGON_GROUPS = [
  { value: '领取邮件', labelKey: 'edit.bettergiGroupMail' },
  { value: '合成树脂', labelKey: 'edit.bettergiGroupResin' },
  { value: '自动地脉花', labelKey: 'edit.bettergiGroupLeyLine' },
  { value: '自动秘境', labelKey: 'edit.bettergiGroupDomain' },
  { value: '自动首领讨伐', labelKey: 'edit.bettergiGroupBoss' },
  { value: '自动幽境危战', labelKey: 'edit.bettergiGroupStygian' },
  { value: '领取每日奖励', labelKey: 'edit.bettergiGroupDailyReward' },
  { value: '领取尘歌壶奖励', labelKey: 'edit.bettergiGroupTeapot' },
]

// 切换语言时标签要跟着变，故必须是 computed 而非常量数组
const oneDragonGroupOptions = computed(() =>
  ONE_DRAGON_GROUPS.map(group => ({ label: t(group.labelKey), value: group.value }))
)

const getDefaultUserData = (): Omit<BetterGIUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
    IfUseMasConfig: true,
  },
  Task: {
    OneDragonConfigName: '默认配置',
  },
  Switch: {
    Resource: '官服',
    Uid: '',
  },
  OneDragon: {
    Groups: ONE_DRAGON_GROUPS.map(group => group.value),
    DailyRewardPartyName: '',
    PartyName: '',
    AutoBossStrategyName: '根据队伍自动选择',
    IfUseCustomGroups: false,
    CustomGroups: '[]',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
})

const formData = reactive<BetterGIUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

// saveField 需在自定义配置组 composable 之前定义（后者在 persist/toggle 中调用它）
const createUserImmediately = async (): Promise<boolean> => {
  const resp = await addUser(scriptId, { showError: false })
  if (!resp?.userId) {
    message.error(userApiError.value || t('edit.couldNotCreateUser'))
    handleCancel()
    return false
  }
  userId.value = resp.userId
  isEdit.value = true
  await router.replace({
    name: 'BetterGIUserEdit',
    params: { scriptId, userId: userId.value },
  })
  return true
}

// 保存串行化队列：以 promise 链取代布尔 isSaving 互斥。布尔守卫会在「上一次保存尚未返回」时
// 丢弃紧随其后的保存（自定义配置组连续勾选/删除即可触发），造成前后端状态失步；队列则逐条按序
// 写回，不再丢保存。
let saveChain: Promise<boolean> = Promise.resolve(true)

const saveField = (key: string, value: unknown): Promise<boolean> => {
  if (isInitializing.value || !userId.value) return Promise.resolve(false)

  const parts = key.split('.')
  const patch: Record<string, any> = {}
  let current = patch
  for (let i = 0; i < parts.length - 1; i += 1) {
    current[parts[i]] = {}
    current = current[parts[i]]
  }
  current[parts[parts.length - 1]] = value

  if (key === 'Info.Name') {
    formData.userName = String(value || '')
  }

  const persist = async (): Promise<boolean> => {
    try {
      const ok = await updateUser(scriptId, userId.value, patch)
      if (!ok) {
        // updateUser 内部已对多数失败分支弹过 message.error，此处兜底记录并向上返回失败，
        // 不再静默吞掉；调用方（如自定义配置组 persist）可据此决定是否回滚。
        logger.error(`保存字段「${key}」失败: ${userApiError.value || '未知错误'}`)
      }
      return ok
    } catch (e) {
      // 仅 updateUser 自身未捕获的意外异常会走到这里
      logger.error(e instanceof Error ? e.message : String(e))
      return false
    }
  }

  const run = saveChain.then(persist, persist)
  saveChain = run
  return run
}

const toggleGroup = (value: string) => {
  if (!formData.Info.IfUseMasConfig) return
  const set = new Set(formData.OneDragon.Groups)
  if (set.has(value)) {
    set.delete(value)
  } else {
    set.add(value)
  }
  // 按内置顺序排序，保持后端一条龙 TaskOrder 稳定
  const groups = ONE_DRAGON_GROUPS.map(g => g.value).filter(v => set.has(v))
  formData.OneDragon.Groups = groups
  void saveField('OneDragon.Groups', groups)
}

// 一条龙配置名下拉选项（{RootPath}/User/OneDragon/*.json，默认配置置顶），由后端实时读取
const oneDragonConfigOptions = ref<{ label: string; value: string }[]>([])
const loadOneDragonConfigs = async () => {
  try {
    const resp =
      await BettergiService.getBettergiOneDragonConfigsApiApiScriptsBettergiOneDragonConfigsGet(
        scriptId
      )
    oneDragonConfigOptions.value = (resp.data || [])
      .filter((item): item is ComboBoxItem & { value: string } => item.value != null)
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 自动战斗策略下拉选项（「根据队伍自动选择」+ {RootPath}/User/AutoFight/*.txt），由后端实时读取
const strategyOptions = ref<{ label: string; value: string }[]>([])
const loadStrategyOptions = async () => {
  try {
    const resp =
      await BettergiService.getBettergiStrategiesApiApiScriptsBettergiStrategiesGet(scriptId)
    strategyOptions.value = (resp.data || [])
      .filter((item): item is ComboBoxItem & { value: string } => item.value != null)
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// ----- 自定义配置组管理（composable）-----
const {
  table: customGroupsTable,
  selectedKeys: selectedCustomGroupKeys,
  modal: customGroupModal,
  columns: customGroupColumns,
  rowSelection: customGroupRowSelection,
  syncFromForm: syncCustomGroupsFromForm,
  loadFromBettergi: loadCustomGroupsFromBettergi,
  toggleMaster: toggleCustomGroupsMaster,
  openAdd: openCustomGroupModal,
  confirmAdd: confirmAddCustomGroup,
  deleteSelected: deleteSelectedCustomGroups,
  toggleEnabled: toggleCustomGroupEnabled,
} = useBettergiCustomGroups({
  scriptId,
  oneDragon: () => formData.OneDragon,
  configName: () => formData.Task.OneDragonConfigName,
  masConfig: () => formData.Info.IfUseMasConfig,
  editable: () => formData.Info.IfUseMasConfig,
  saveField,
})

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'boolean') return
  if (
    isInitializing.value ||
    configModeSaving.value ||
    !userId.value ||
    formData.Info.IfUseMasConfig === value
  ) {
    return
  }

  const previousValue = formData.Info.IfUseMasConfig
  formData.Info.IfUseMasConfig = value
  configModeSaving.value = true

  try {
    const saved = await updateUser(scriptId, userId.value, {
      Info: { IfUseMasConfig: value },
    })

    if (!saved) {
      formData.Info.IfUseMasConfig = previousValue
      return
    }

    logger.info(`配置来源已切换为: ${value ? '用户独立配置' : '脚本直控配置'}`)
  } finally {
    configModeSaving.value = false
  }
}

// ----- 原生 GUI 设置会话（composable）-----
const {
  bettergiConfigLoading,
  bettergiWebsocketId,
  showBettergiConfigMask,
  startSession,
  saveSession,
  stopSession,
  dispose: disposeGuiSession,
} = useBettergiGuiSession()

const handleBettergiConfig = () => {
  if (!userId.value) return
  void startSession(userId.value)
}

const handleSaveBettergiConfig = () => {
  void saveSession()
}

const handleCancel = async () => {
  await stopSession()
  await router.push('/scripts')
}

const loadScriptInfo = async (): Promise<boolean> => {
  const detail = await getScript(scriptId)
  if (!detail || detail.type !== 'BetterGI') {
    message.error(t('edit.bettergiScriptNotFound'))
    handleCancel()
    return false
  }

  scriptName.value = detail.name
  return true
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId.value) {
      if (!(await createUserImmediately())) return
    }
    const resp = await getUsers(scriptId, userId.value)
    const userIndex = resp?.index?.find(i => i.uid === userId.value)
    const data = resp?.data?.[userId.value]
    if (!userIndex || !data) {
      throw new Error('用户不存在或加载失败')
    }

    const userData = data as BetterGIUserConfig

    Object.assign(formData, {
      Info: { ...getDefaultUserData().Info, ...(userData.Info || {}) },
      Task: { ...getDefaultUserData().Task, ...(userData.Task || {}) },
      Switch: { ...getDefaultUserData().Switch, ...(userData.Switch || {}) },
      OneDragon: { ...getDefaultUserData().OneDragon, ...(userData.OneDragon || {}) },
      Notify: { ...getDefaultUserData().Notify, ...(userData.Notify || {}) },
    })
    // 一条龙名称为必填：历史空值归一为「默认配置」
    if (!formData.Task.OneDragonConfigName) {
      formData.Task.OneDragonConfigName = '默认配置'
    }
    await nextTick()
    formData.userName = formData.Info.Name || ''

    // 同步自定义配置组表格；总开关已开且表格为空时，从 BetterGI 自动加载现有自定义组
    syncCustomGroupsFromForm()
    if (formData.OneDragon.IfUseCustomGroups && customGroupsTable.value.length === 0) {
      await loadCustomGroupsFromBettergi()
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(t('edit.couldNotLoadUser'))
    handleCancel()
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

onMounted(async () => {
  if (await loadScriptInfo()) {
    await loadUser()
  }
  await loadStrategyOptions()
  await loadOneDragonConfigs()
})

onUnmounted(() => {
  disposeGuiSession()
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.configuring-button {
  color: #52c41a;
  border-color: #52c41a;
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.required-mark {
  color: var(--ant-color-error);
  margin-right: 4px;
}

.modern-select {
  width: 100%;
}

.section-desc {
  margin: -8px 0 20px;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.config-group-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.config-group-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 4px;
  border: 1px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  user-select: none;
  transition:
    background 0.2s,
    border-color 0.2s;
}

.config-group-item:hover {
  background: var(--ant-color-fill-tertiary);
}

.config-group-item.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.config-group-item.disabled:hover {
  background: transparent;
}

.config-group-item-label {
  font-size: 14px;
  font-weight: 400;
  color: var(--ant-color-text);
}

.config-group-item-capsule {
  position: relative;
  width: 44px;
  height: 22px;
  border-radius: 11px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border);
  transition:
    background 0.2s,
    border-color 0.2s;
}

.config-group-item-capsule.active {
  background: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.config-group-item-dot {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: left 0.2s;
}

.config-group-item-capsule.active .config-group-item-dot {
  left: 25px;
}

.config-group-hint {
  margin: 0 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.config-flow-p {
  margin: 0;
}

.config-flow-p + .config-flow-p {
  margin-top: 8px;
}

.mode-guide-alert {
  margin-bottom: 20px;
}

.mode-guide-message {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.config-flow-title {
  font-weight: 600;
}

.config-flow-desc {
  line-height: 1.7;
  color: var(--ant-color-text);
}

.custom-groups-desc {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.custom-groups-section {
  margin-top: 20px;
}

.custom-groups-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.custom-groups-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.custom-groups-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
}

.custom-groups-toggle-label {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.custom-groups-body {
  margin-top: 12px;
}

.custom-groups-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.custom-groups-capsule {
  cursor: pointer;
}

.custom-groups-capsule.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.bettergi-config-mask {
  position: fixed;
  inset: 32px 0 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
}

.mask-content {
  width: 100%;
  max-width: 480px;
  padding: 24px;
  text-align: center;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.mask-description {
  margin: 0 0 24px;
  color: var(--ant-color-text-secondary);
}

.mask-actions {
  display: flex;
  justify-content: center;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }

  .config-group-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
