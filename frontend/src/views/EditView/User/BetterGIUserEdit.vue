<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/bettergi`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? '编辑用户' : '添加用户' }}
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
              独立配置模式：将打开 BetterGI，请在「一条龙」页面编辑「MAS独立配置」，保存退出后自动回读到该用户。
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
            配置 BetterGI
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
          配置 BetterGI
        </a-button>
        <a-button v-else type="default" size="large" disabled class="configuring-button">
          <template #icon>
            <SettingOutlined />
          </template>
          正在配置
        </a-button>
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </a-space>
    </div>

    <teleport to="body">
      <div v-if="showBettergiConfigMask" class="bettergi-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">正在进行 BetterGI 设置</h2>
          <p class="mask-description">
            请在 BetterGI 界面完成设置。
            <br />
            完成后点击“保存设置”结束本次会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="bettergiWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveBettergiConfig"
            >
              保存设置
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
              <h3>基本信息</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      用户名
                      <a-tooltip title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    placeholder="请输入用户名"
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
                      启用状态
                      <a-tooltip title="是否启用该用户">
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
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      账户
                      <a-tooltip
                        title="用于切换账号，无需切换则留空；下拉列表模式填写完整手机号/邮箱，MAS 自动转换为游戏显示的打码形式"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    placeholder="请输入账户"
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
                      账号 UID
                      <a-tooltip
                        title="可不填；切换账号建议填写，填写后切换前识别一致将不执行切换动作"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Switch.Uid"
                    placeholder="请输 UID（切换账号建议填写）"
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
                      密码
                      <a-tooltip
                        title="没有填写密码时，默认为下拉列表切换账号。如果切换账号使用密码登录，必须填写密码"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    placeholder="请输入密码（没有填写密码时，默认为下拉列表切换账号）"
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
                      游戏服务器
                      <a-tooltip title="账号所在服务器：官服 / B服 / 亚服 / 欧服 / 美服 / 港澳台服">
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
                    <a-select-option value="官服">官服</a-select-option>
                    <a-select-option value="B服">B服</a-select-option>
                    <a-select-option value="亚服">亚服</a-select-option>
                    <a-select-option value="欧服">欧服</a-select-option>
                    <a-select-option value="美服">美服</a-select-option>
                    <a-select-option value="港澳台服">港澳台服</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      剩余天数
                      <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
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
                  备注
                  <a-tooltip title="为用户添加备注信息">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </span>
              </template>
              <a-textarea
                v-model:value="formData.Info.Notes"
                placeholder="请输入备注"
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
                任务配置
                <a-tooltip
                  title="勾选要执行的一条龙内置配置组；选择「脚本直控配置」时由 BetterGI 原生配置决定，不可编辑"
                >
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
                  当前为「脚本直控配置」，任务配置项不可编辑。请切换到「用户独立配置」，以在本页为该
                  用户配置独立的一条龙任务。
                </span>
              </template>
              <template #action>
                <a-button
                  type="primary"
                  size="small"
                  :loading="configModeSaving"
                  @click="handleConfigModeChange(true)"
                >
                  切换到用户独立配置
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
                <span class="config-flow-title">如何使用「用户独立配置」</span>
              </template>
              <template #description>
                <p class="config-flow-desc config-flow-p">
                  该用户的一条龙已走独立配置：MAS 会以「MAS独立配置」这条龙槽位启动。想调整
                  具体任务，点击右上角「配置 BetterGI」打开 BGI，在其「一条龙」页面选择并编辑名为
                  <b>「MAS独立配置」</b> 的配置，保存退出后 MAS 会自动回读到该用户。
                  请不要修改你原有的一龙实配（如「默认配置」）——独立配置读取的是「MAS独立配置」
                  槽位，同名实配不会被读取、也不受这里编辑影响。
                </p>
                <p class="config-flow-desc config-flow-p">
                  下方面板的通用战斗队伍 / 通用战斗策略：留空则使用 BetterGI 现有设置（策略留空=「根据队伍
                  自动选择」）；填写后将应用到一条龙里需要战斗的四个任务（自动地脉花、自动秘境、自动首领讨伐、
                  自动幽境危战），替换 BetterGI 对应任务的默认队伍与策略。
                </p>
              </template>
            </a-alert>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      <span class="required-mark">*</span>
                      一条龙名称
                      <a-tooltip
                        title="必填。对应 BetterGI 一条龙页面中已保存/将保存的一条龙配置名称，默认为「默认配置」"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Task.OneDragonConfigName"
                    :options="oneDragonConfigOptions"
                    placeholder="请选择一条龙配置名称"
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
                      领取奖励队伍
                      <a-tooltip title="留空则不覆盖 BetterGI 现有设置">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.OneDragon.DailyRewardPartyName"
                    :disabled="!formData.Info.IfUseMasConfig"
                    placeholder="请输入领取奖励队伍"
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
                      通用战斗队伍
                      <a-tooltip title="留空则不覆盖 BetterGI 现有设置">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.OneDragon.PartyName"
                    :disabled="!formData.Info.IfUseMasConfig"
                    placeholder="请输入通用战斗队伍"
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
                      通用战斗策略
                      <a-tooltip title="留空则默认为【根据队伍自动选择】">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.OneDragon.AutoBossStrategyName"
                    :disabled="!formData.Info.IfUseMasConfig"
                    placeholder="请输入通用战斗策略"
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
                胶囊是「任务配置组」开关：勾选的任务才会执行，未勾选的不执行。
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
                  自定义配置组
                  <a-tooltip placement="top">
                    <template #title>
                      <div style="max-width: 320px; white-space: normal">
                        来源：BetterGI 一条龙配置里除 8 个内置组以外的自定义配置组（在
                        BetterGI 一条龙界面添加），不是下方的「任务配置组」开关。
                        <br /><br />
                        用法（本表只是一个开关）：一条龙里存在但本表未列出的配置组
                        <b>默认执行</b>；已加入本表的组按行的开关执行——开启则执行、关闭则不执行。
                        <br /><br />
                        「添加配置组」从 BetterGI 现有配置（独立配置模式下读取「MAS独立配置」槽位）
                        选取要纳入控制的组；未入表的组仍保留在一条龙里，不会因本表而丢失。
                      </div>
                    </template>
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </h3>
                <div class="custom-groups-toggle">
                  <span class="custom-groups-toggle-label">启用</span>
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
                来源是 BetterGI 一条龙配置里除 8 个内置组以外的自定义配置组；本表只是一个开关——
                一条龙里有但表里没有的组默认执行，入表的组按行的开关执行（开启执行、关闭不执行）。
              </p>

              <div
                v-if="formData.OneDragon.IfUseCustomGroups && formData.Info.IfUseMasConfig"
                class="custom-groups-body"
              >
                <div class="custom-groups-toolbar">
                  <a-button size="small" type="primary" ghost @click="openCustomGroupModal">
                    添加配置组
                  </a-button>
                  <a-popconfirm
                    title="确定删除选中的配置组吗？"
                    :disabled="selectedCustomGroupKeys.length === 0"
                    @confirm="deleteSelectedCustomGroups"
                  >
                    <a-button size="small" danger :disabled="selectedCustomGroupKeys.length === 0">
                      删除选中
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
            title="添加配置组"
            :ok-text="customGroupModal.saving ? '添加中...' : '添加'"
            :ok-button-props="{ disabled: customGroupModal.saving }"
            @ok="confirmAddCustomGroup"
            @cancel="customGroupModal.open = false"
          >
            <a-select
              v-model:value="customGroupModal.name"
              :options="customGroupModal.addOptions"
              placeholder="选择 BGI 现有的配置组（添加后默认启用）"
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
              <h3>通知配置</h3>
            </div>
            <a-row :gutter="24" align="middle">
              <a-col :span="6">
                <span style="font-weight: 500">启用通知</span>
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
                <span style="font-weight: 500">通知内容</span>
              </a-col>
              <a-col :span="18">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendStatistic"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
                >
                  统计信息
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
                  邮件通知
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ToAddress"
                  placeholder="请输入收件邮箱"
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
                  Server酱
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ServerChanKey"
                  placeholder="请输入 SENDKEY"
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
import { nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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

const logger = window.electronAPI.getLogger('BetterGI用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser, error: userApiError } = useUserApi()
const { getScript } = useScriptApi()

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref('BetterGI脚本')

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

// 一条龙内置配置组（与后端 BetterGIUserConfig.OneDragon.Groups 的默认项保持一致）
const oneDragonGroupOptions = [
  { label: '领取邮件', value: '领取邮件' },
  { label: '合成树脂', value: '合成树脂' },
  { label: '自动地脉花', value: '自动地脉花' },
  { label: '自动秘境', value: '自动秘境' },
  { label: '自动首领讨伐', value: '自动首领讨伐' },
  { label: '自动幽境危战', value: '自动幽境危战' },
  { label: '领取每日奖励', value: '领取每日奖励' },
  { label: '领取尘歌壶奖励', value: '领取尘歌壶奖励' },
]

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
    Groups: oneDragonGroupOptions.map(option => option.value),
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
    message.error(userApiError.value || '创建用户失败')
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
  const groups = oneDragonGroupOptions.map(o => o.value).filter(v => set.has(v))
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
    message.error('BetterGI 脚本不存在或加载失败')
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
    message.error('加载用户失败')
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
