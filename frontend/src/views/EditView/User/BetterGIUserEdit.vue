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

            <div class="bettergi-groups-layout">
              <!-- 左栏：一条龙队列（8 内置 + 体力作战 + 自定义组，可拖拽排序） -->
              <div class="bettergi-groups-pane bettergi-groups-list-pane">
                <div class="bettergi-groups-toolbar">
                  <a-space size="small">
                    <a-button
                      type="primary"
                      ghost
                      size="small"
                      :disabled="!groupsEditable"
                      @click="openAddToDragonModal"
                    >
                      <template #icon>
                        <PlusOutlined />
                      </template>
                      {{ t('edit.bettergiAddToDragon') }}
                    </a-button>
                    <a-popconfirm
                      :title="t('edit.bettergiClearDragonTitle')"
                      :ok-text="t('edit.ok')"
                      :cancel-text="t('edit.cancel')"
                      :disabled="!groupsEditable || dragonList.length === 0"
                      @confirm="clearDragon"
                    >
                      <a-button
                        size="small"
                        :disabled="!groupsEditable || dragonList.length === 0"
                      >
                        <template #icon>
                          <ClearOutlined />
                        </template>
                        {{ t('edit.bettergiClearDragon') }}
                      </a-button>
                    </a-popconfirm>
                  </a-space>
                  <span class="bettergi-groups-toolbar-tip">{{ t('edit.bettergiRightClickRemove') }}</span>
                </div>

                <draggable
                  v-model="dragonListModel"
                  :item-key="getDragonRowKey"
                  handle=".group-row-drag-area"
                  :animation="200"
                  :disabled="!groupsEditable"
                  ghost-class="group-row-ghost"
                  chosen-class="group-row-chosen"
                  drag-class="group-row-drag"
                  class="bettergi-groups-list"
                  @end="handleGroupDragEnd"
                >
                  <template #item="{ element: item }">
                    <div
                      class="group-row"
                      :class="{
                        'group-row-selected': isRowSelected(item),
                        'group-row-disabled': !groupsEditable || isGroupFrozen(item),
                        'group-row-frozen': isGroupFrozen(item),
                      }"
                      @contextmenu.prevent="handleRowContextMenu(item)"
                    >
                      <!-- 可拖拽热区：覆盖整行左 2/3（名称区），仅右键菜单/开关在热区外 -->
                      <div
                        class="group-row-drag-area"
                        @click="selectConfigGroup(item)"
                      >
                        <HolderOutlined class="group-row-drag-handle" aria-hidden="true" />
                        <span class="group-row-name">
                          <a-tag
                            color="default"
                            size="small"
                            class="group-row-kind-tag"
                            :class="{
                              'group-row-prefix-stamina': item.kind === 'stamina',
                              'group-row-prefix-custom': item.kind === 'custom',
                            }"
                          >
                            {{ groupPrefix(item) }}
                          </a-tag>
                          <span class="group-row-label">{{ groupLabel(item) }}</span>
                          <a-tag v-if="isGroupFrozen(item)" color="orange" size="small">
                            {{ t('edit.bettergiGroupFrozen') }}
                          </a-tag>
                        </span>
                      </div>
                      <div
                        class="config-group-item-capsule group-row-capsule"
                        :class="{ active: groupEnabled(item) }"
                        @click.stop="toggleConfigGroup(item)"
                      >
                        <span class="config-group-item-dot"></span>
                      </div>
                    </div>
                  </template>
                </draggable>
              </div>

              <!-- 右栏：选中配置组详情 -->
              <div class="bettergi-groups-pane bettergi-groups-detail-pane">
                <template v-if="selectedGroupIdentity">
                  <div class="bettergi-groups-detail-header">
                    <div class="bettergi-groups-detail-title">
                      <a-tag
                        :color="
                          selectedGroupIdentity.kind === 'stamina'
                            ? 'purple'
                            : selectedGroupIdentity.kind === 'custom'
                              ? 'blue'
                              : 'default'
                        "
                        size="small"
                      >
                        {{ groupPrefix(selectedGroupIdentity) }}
                      </a-tag>
                      <span class="bettergi-groups-detail-name">
                        {{ groupLabel(selectedGroupIdentity) }}
                      </span>
                    </div>
                    <a-tooltip
                      v-if="isGroupFrozen(selectedGroupIdentity)"
                      :title="t('edit.bettergiGroupFrozenTip')"
                    >
                      <a-tag color="orange">{{ t('edit.bettergiGroupFrozen') }}</a-tag>
                    </a-tooltip>
                    <div
                      v-else
                      class="config-group-item-capsule custom-groups-capsule"
                      :class="{
                        active: groupEnabled(selectedGroupIdentity),
                        disabled: !groupsEditable,
                      }"
                      @click="toggleConfigGroup(selectedGroupIdentity)"
                    >
                      <span class="config-group-item-dot"></span>
                    </div>
                  </div>
                  <p class="bettergi-groups-detail-desc">{{ groupDescText(selectedGroupIdentity) }}</p>
                </template>
                <div v-else class="bettergi-groups-detail-empty">
                  <a-empty :description="t('edit.bettergiGroupsEmptyRight')" />
                </div>
              </div>
            </div>
          </div>

          <!-- 添加配置组弹窗（加入一条龙末尾） -->
          <a-modal
            v-model:open="addModal.open"
            :title="t('edit.bettergiAddToDragon')"
            :ok-text="t('edit.bettergiAddToDragonOk')"
            :ok-button-props="{ disabled: !addModal.name.trim() }"
            :cancel-text="t('edit.cancel')"
            @ok="confirmAddToDragon"
            @cancel="addModal.open = false"
          >
            <a-input
              v-model:value="addModal.name"
              :placeholder="t('edit.bettergiInputGroupNames')"
              class="add-dragon-input"
            />
            <p class="add-dragon-input-tip">{{ t('edit.bettergiInputGroupNamesTip') }}</p>
            <div class="add-dragon-candidates">
              <div
                v-for="candidate in addModal.candidates"
                :key="`${candidate.kind}:${candidate.key}`"
                class="add-dragon-candidate"
                :class="{
                  'add-dragon-candidate-picked': candidateInInput(candidate),
                  'add-dragon-candidate-disabled': !ALLOW_DUPLICATE_GROUPS && inDragon(candidate),
                }"
                @click="
                  !ALLOW_DUPLICATE_GROUPS && inDragon(candidate)
                    ? warnAlreadyInDragon()
                    : pickAddCandidate(candidate)
                "
              >
                <a-tag
                  size="small"
                  :color="candidate.kind === 'stamina' ? 'purple' : candidate.kind === 'custom' ? 'blue' : 'default'"
                  class="add-dragon-candidate-tag"
                >
                  {{ groupPrefix(candidate) }}
                </a-tag>
                <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
                <a-tag v-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)" color="default" size="small">
                  {{ t('edit.bettergiInQueue') }}
                </a-tag>
              </div>
            </div>
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
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import draggable from 'vuedraggable'
import {
  ArrowLeftOutlined,
  ClearOutlined,
  HolderOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { BetterGiService, type ComboBoxItem, type BetterGIUserConfig } from '@/api'
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
      await BetterGiService.getBettergiOneDragonConfigsApiApiScriptsBettergiOneDragonConfigsGet(
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
      await BetterGiService.getBettergiStrategiesApiApiScriptsBettergiStrategiesGet(scriptId)
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
  syncFromForm: syncCustomGroupsFromForm,
  loadFromBettergi: loadCustomGroupsFromBettergi,
  toggleMaster: toggleCustomGroupsMaster,
  deleteSelected: deleteSelectedCustomGroups,
  toggleEnabled: toggleCustomGroupEnabled,
  addByName: addCustomGroupByName,
} = useBettergiCustomGroups({
  scriptId,
  oneDragon: () => formData.OneDragon,
  configName: () => formData.Task.OneDragonConfigName,
  masConfig: () => formData.Info.IfUseMasConfig,
  editable: () => formData.Info.IfUseMasConfig,
  saveField,
})

// ============================================================
// 一条龙配置组「队列可视化」（8 内置 + 体力作战 + 自定义组）
// ============================================================
// 交互语义：
//  - 左栏列表即「一条龙队列」：其中的配置组按顺序执行。默认 = 8 个官方内置组 + 体力作战（第 9 项）。
//  - 行前缀 tag：内置 →「默认」；体力作战 →「专项」；自定义组 →「自定义」。
//  - 行内胶囊开关控制是否启用（内置 ↔ Groups；自定义 ↔ CustomGroups；体力作战为本地虚拟项）。
//  - 点击「添加配置组」：从候选（8 内置 + 体力作战 + BetterGI 现有自定义组）挑选，加入队列末尾。
//  - 右键某一配置组：从一条龙移除（内置移出 Groups、自定义移出 CustomGroups、体力作战移除并关闭）。
//  - 体力作战启用互斥：开启体力作战时，自动关闭并冻结「自动秘境 / 自动地脉花 / 自动首领讨伐」；
//    体力作战关闭或从一条龙移除后才解冻，三组可重新开启。
// 说明：BetterGI 内置组执行顺序与队列成员最终由后端一条龙 TaskOrder 决定，本次后端顺序化尚未
// 配套，左栏顺序/成员作为前端队列编排（dragonList）保留，待后端支持后映射 Groups/CustomGroups。
const STAMINA_COMBAT_KEY = '__mas_stamina_combat__'

type ConfigGroupKind = 'builtin' | 'stamina' | 'custom'

type ConfigGroupIdentity = {
  kind: ConfigGroupKind
  key: string // builtin/custom: 组名字面量；stamina: STAMINA_COMBAT_KEY
  /** 队列行唯一实例标识：允许同一配置组重复添加时，每行都有独立 uid（拖拽/删除按行实例） */
  uid?: number
}

// 启用体力作战时自动关闭并冻结的官方内置组（专项接管刷取）
const STAMINA_FROZEN_BUILTINS = ['自动秘境', '自动地脉花', '自动首领讨伐']

// 重复添加配置组功能开关：开启后允许同一配置组在一条龙中多次添加（每行为独立实例）。
// 后端"同一配置多次添加"的语义后续详说，本开关用于先行测试。
const ALLOW_DUPLICATE_GROUPS = true

// 队列行 uid 自增计数器
let dragonRowSeq = 0

// 当前一条龙队列（有序身份列表，顺序即执行顺序）
const dragonList = ref<ConfigGroupIdentity[]>([])

// 体力作战是否已加入一条龙（本地虚拟项，默认加入）
const staminaInDragon = ref(true)
// 体力作战启用开关（本地虚拟项，不落库）
const staminaCombatEnabled = ref(false)
// 启用体力作战前的记忆快照：记录受影响内置组原本是否启用，用于关闭体力后恢复
const staminaFrozenSnapshot = ref<Record<string, boolean>>({})

// 当前选中的队列行（右侧面板展示）
const selectedGroupIdentity = ref<ConfigGroupIdentity | null>(null)

// 内置组的显示名表（key=中文组名 value）
const builtinGroupLabels = computed<Record<string, string>>(() =>
  Object.fromEntries(ONE_DRAGON_GROUPS.map(g => [g.value, t(g.labelKey)]))
)

// 左侧是否可编辑/可展示列表（受「MAS 独立配置」总开关约束）
const groupsEditable = computed(() => formData.Info.IfUseMasConfig)
const groupsShowCustom = computed(
  () => formData.OneDragon.IfUseCustomGroups && formData.Info.IfUseMasConfig
)

// 前缀 tag 文案
const groupPrefix = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return t('edit.bettergiGroupPrefixDefault')
  if (item.kind === 'stamina') return t('edit.bettergiGroupKindStamina')
  return t('edit.bettergiGroupKindCustom')
}

const groupLabel = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return builtinGroupLabels.value[item.key] ?? item.key
  if (item.kind === 'stamina') return t('edit.bettergiGroupStamina')
  return item.key
}

// 右栏说明文字：内置/体力作战/自定义 三类分别给不同文案
const groupDescText = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return t('edit.bettergiGroupCapsuleHint')
  if (item.kind === 'stamina') return t('edit.bettergiGroupStaminaHint')
  return t('edit.bettergiCustomGroupsDesc')
}

// 是否被体力作战冻结（启用体力作战时三个刷取内置组冻结）
const isGroupFrozen = (item: ConfigGroupIdentity): boolean =>
  item.kind === 'builtin' &&
  staminaCombatEnabled.value &&
  STAMINA_FROZEN_BUILTINS.includes(item.key)

const groupEnabled = (item: ConfigGroupIdentity): boolean => {
  if (item.kind === 'builtin') return formData.OneDragon.Groups.includes(item.key)
  if (item.kind === 'stamina') return staminaCombatEnabled.value
  return Boolean(customGroupsTable.value.find(r => r.name === item.key)?.enabled)
}

// 队列是否包含某配置组
const inDragon = (item: ConfigGroupIdentity): boolean =>
  dragonList.value.some(i => i.kind === item.kind && i.key === item.key)

// 同步后端内置组启用集合（当前 Groups 含 enabled 列表 + 冻结时剔除冻结项）
const applyGroupsPatch = (next: string[]) => {
  formData.OneDragon.Groups = next
  void saveField('OneDragon.Groups', next)
}

// 从当前 Groups 中剔除指定内置组（冻结 / 删除共用）
const removeBuiltinsFromGroups = (keys: string[]) => {
  const set = new Set(keys)
  const next = formData.OneDragon.Groups.filter(g => !set.has(g))
  if (next.join('\u0001') !== formData.OneDragon.Groups.join('\u0001')) {
    applyGroupsPatch(next)
  }
}

// 生成一条带唯一 uid 的队列行实例
const makeDragonRow = (item: ConfigGroupIdentity): ConfigGroupIdentity => ({
  ...item,
  uid: ++dragonRowSeq,
})

// 队列行去重辅助（仅用于初始化；允许重复时不用此函数）
const pushDragon = (list: ConfigGroupIdentity[], item: ConfigGroupIdentity) => {
  if (!list.some(i => i.kind === item.kind && i.key === item.key)) list.push(makeDragonRow(item))
}

// 依据用户数据初始化一条龙队列（loadUser 后调用一次，随后由增删/拖拽维护）：
// 种子 = 8 内置（默认在列，enabled 由 Groups 表达）+ 体力作战（默认在列，默认关闭）
const initDragonList = () => {
  const order: ConfigGroupIdentity[] = []
  for (const g of ONE_DRAGON_GROUPS) pushDragon(order, { kind: 'builtin', key: g.value })
  if (staminaInDragon.value) pushDragon(order, { kind: 'stamina', key: STAMINA_COMBAT_KEY })
  // 自定义组仅在总开关开启时并入（来自 BetterGI 现有配置 / CustomGroups）
  if (groupsShowCustom.value) {
    for (const row of customGroupsTable.value) pushDragon(order, { kind: 'custom', key: row.name })
  }
  dragonList.value = order
}

// 把 BetterGI 侧新增的自定义组补入队列末尾（保留用户已删除的自定义组不回来）
const appendCustomRows = () => {
  if (!groupsShowCustom.value) return
  for (const row of customGroupsTable.value) {
    const item: ConfigGroupIdentity = { kind: 'custom', key: row.name }
    if (!inDragon(item)) dragonList.value.push(makeDragonRow(item))
  }
}

// 供 draggable v-model 使用（纯前端顺序）
const dragonListModel = computed<ConfigGroupIdentity[]>({
  get: () => dragonList.value,
  set: value => {
    dragonList.value = value
  },
})

// ---- 开关 ----
// 开启/关闭体力作战（含互斥冻结/解冻 + 记忆恢复）
const toggleStaminaCombat = () => {
  const next = !staminaCombatEnabled.value
  if (next) {
    // 启用体力作战：先记忆受影响组原本的启用状态，再自动关闭（冻结）
    staminaFrozenSnapshot.value = Object.fromEntries(
      STAMINA_FROZEN_BUILTINS.map(name => [name, formData.OneDragon.Groups.includes(name)])
    )
    removeBuiltinsFromGroups(STAMINA_FROZEN_BUILTINS)
  } else {
    // 关闭体力作战：按记忆恢复原本开启的组（记忆为空则不误改）
    const toRestore = STAMINA_FROZEN_BUILTINS.filter(name => staminaFrozenSnapshot.value[name])
    if (toRestore.length) {
      const nextGroups = [...new Set([...formData.OneDragon.Groups, ...toRestore])]
      applyGroupsPatch(nextGroups)
    }
    staminaFrozenSnapshot.value = {}
  }
  staminaCombatEnabled.value = next
}

// 移除体力作战（右键移出）时同样按记忆恢复受影响组
const restoreStaminaFrozen = () => {
  const toRestore = STAMINA_FROZEN_BUILTINS.filter(name => staminaFrozenSnapshot.value[name])
  if (toRestore.length) {
    applyGroupsPatch([...new Set([...formData.OneDragon.Groups, ...toRestore])])
  }
  staminaFrozenSnapshot.value = {}
  staminaCombatEnabled.value = false
}

// 清空整条一条龙：清掉队列、后端内置组/自定义组，并关闭体力作战（不做冻结组恢复）
const clearDragon = () => {
  dragonList.value = []
  staminaInDragon.value = false
  staminaCombatEnabled.value = false
  staminaFrozenSnapshot.value = {}
  applyGroupsPatch([])
  if (formData.OneDragon.CustomGroups !== '[]') {
    formData.OneDragon.CustomGroups = '[]'
    void saveField('OneDragon.CustomGroups', '[]')
  }
  selectedGroupIdentity.value = null
}

// 行开关：内置写 Groups、体力作战本地翻转（互斥）、自定义交给 composable 持久化
const toggleConfigGroup = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (isGroupFrozen(item)) return
  if (item.kind === 'builtin') {
    toggleGroup(item.key)
  } else if (item.kind === 'stamina') {
    toggleStaminaCombat()
  } else {
    const row = customGroupsTable.value.find(r => r.name === item.key)
    if (row) toggleCustomGroupEnabled(row)
  }
}

// ---- 添加：把配置组加入一条龙（放到队列末尾）----
const addToDragon = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (!ALLOW_DUPLICATE_GROUPS && inDragon(item)) return
  if (item.kind === 'builtin') {
    if (!formData.OneDragon.Groups.includes(item.key)) {
      applyGroupsPatch([...formData.OneDragon.Groups, item.key])
    }
  } else if (item.kind === 'stamina') {
    staminaInDragon.value = true
  } else {
    // 自定义组：确保进入 CustomGroups（启用）并打开总开关
    if (addCustomGroupByName(item.key)) {
      if (!formData.OneDragon.IfUseCustomGroups) toggleCustomGroupsMaster()
    } else {
      const row = customGroupsTable.value.find(r => r.name === item.key)
      if (row && !row.enabled) toggleCustomGroupEnabled(row)
    }
  }
  // 追加到队列末尾：生成带唯一 uid 的行实例（重复开关开启时允许同一配置多次添加）
  dragonList.value.push(makeDragonRow(item))
}

// 队列中是否仍存在同类配置组（删除某实例后判断是否还保留后端启用）
const hasSameKindRow = (item: ConfigGroupIdentity, exceptUid?: number): boolean =>
  dragonList.value.some(i => i.uid !== exceptUid && i.kind === item.kind && i.key === item.key)

// ---- 右键删除：从一条龙移除（按行实例 uid，一次只删一行）----
const removeFromDragon = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (item.kind === 'builtin') {
    if (isGroupFrozen(item)) return // 冻结中不可删除
    dragonList.value = dragonList.value.filter(i => i.uid !== item.uid)
    if (!hasSameKindRow(item, item.uid)) {
      removeBuiltinsFromGroups([item.key])
    }
  } else if (item.kind === 'stamina') {
    dragonList.value = dragonList.value.filter(i => i.uid !== item.uid)
    if (!hasSameKindRow(item, item.uid)) {
      staminaInDragon.value = false
      restoreStaminaFrozen() // 最后一个体力作战被移除：恢复受影响组
    }
  } else {
    dragonList.value = dragonList.value.filter(i => i.uid !== item.uid)
    // 仅当这是最后一个同配置实例时才从 CustomGroups 移除
    if (!hasSameKindRow(item, item.uid)) {
      const row = customGroupsTable.value.find(r => r.name === item.key)
      if (row) {
        selectedCustomGroupKeys.value = [row.name]
        void deleteSelectedCustomGroups()
      }
    }
  }
  if (
    selectedGroupIdentity.value &&
    selectedGroupIdentity.value.uid === item.uid
  ) {
    selectedGroupIdentity.value = null
  }
}

// 右侧选中行：展示该配置组详情
const selectConfigGroup = (item: ConfigGroupIdentity) => {
  selectedGroupIdentity.value = { ...item }
}

// draggable 行 key：优先用 uid（允许重复时每行唯一）；无 uid 时退化用身份
const getDragonRowKey = (item: ConfigGroupIdentity): string =>
  item.uid != null ? `row:${item.uid}` : `${item.kind}:${item.key}`

// 行是否被选中：按 uid 精确匹配（重复同类行互不影响）
const isRowSelected = (item: ConfigGroupIdentity): boolean => {
  const sel = selectedGroupIdentity.value
  if (!sel) return false
  if (item.uid != null && sel.uid != null) return item.uid === sel.uid
  return sel.kind === item.kind && sel.key === item.key
}

const handleGroupDragEnd = () => {
  // 本次后端顺序化未配套：仅保留前端拖拽结果，不做后端落库
  logger.debug(`一条龙队列顺序已调整（未落库）: ${dragonList.value.map(i => i.key).join(',')}`)
}

// 右键某一配置组 → 确认后从一条龙移除
const handleRowContextMenu = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (isGroupFrozen(item)) {
    message.warning(t('edit.bettergiGroupFrozenTip'))
    return
  }
  Modal.confirm({
    title: t('edit.bettergiRemoveFromDragonTitle'),
    content: t('edit.bettergiRemoveFromDragonContent', { name: groupLabel(item) }),
    okText: t('edit.deleteSelected'),
    okButtonProps: { danger: true },
    cancelText: t('edit.cancel'),
    onOk: () => removeFromDragon(item),
  })
}

// 候选中该项已在一条龙时的提示（替代模板内联 message）
const warnAlreadyInDragon = () => {
  message.info(t('edit.bettergiAlreadyInDragon'))
}

// ---- 添加弹窗（候选：8 内置 + 体力作战 + BetterGI 现有自定义组）----
const addModal = reactive({
  open: false,
  name: '',
  candidates: [] as ConfigGroupIdentity[],
})

// 组装候选项：固定 9 项 + 现有自定义组（已加入队列的项稍后在模板中禁用）
const buildCandidates = () => {
  const items: ConfigGroupIdentity[] = []
  for (const g of ONE_DRAGON_GROUPS) items.push({ kind: 'builtin', key: g.value })
  items.push({ kind: 'stamina', key: STAMINA_COMBAT_KEY })
  for (const row of customGroupsTable.value) {
    if (!items.some(i => i.kind === 'custom' && i.key === row.name)) {
      items.push({ kind: 'custom', key: row.name })
    }
  }
  addModal.candidates = items
}

const openAddToDragonModal = async () => {
  addModal.name = ''
  addModal.open = true
  await loadCustomGroupsFromBettergi()
  buildCandidates()
}

// 拆分输入框内容：支持「;」「；」分隔，返回去空白的组名字面量列表
const splitGroupNames = (raw: string): string[] =>
  (raw || '')
    .split(/[;；]/)
    .map(s => s.trim())
    .filter(Boolean)

// 该候选组名是否已出现在输入框中（用于候选高亮）
const candidateInInput = (candidate: ConfigGroupIdentity): boolean => {
  const label = groupLabel(candidate)
  return splitGroupNames(addModal.name).includes(label)
}

// 候选点击：把该配置组的「名称」追加进输入框并补一个分号，支持连续点击连续添加
const pickAddCandidate = (item: ConfigGroupIdentity) => {
  const name = groupLabel(item)
  const tailSemicolon = /[;；]$/.test(addModal.name)
  addModal.name = `${addModal.name}${tailSemicolon ? '' : addModal.name ? ';' : ''}${name};`
}

// 按名称在候选中定位配置组（内置按 value/翻译名，自定义按组名，体力作战按展示名）
const findCandidateByName = (name: string): ConfigGroupIdentity | undefined =>
  addModal.candidates.find(c => c.key === name || groupLabel(c) === name)

// 确认：输入框内每段名称依次加入一条龙
const confirmAddToDragon = () => {
  const names = splitGroupNames(addModal.name)
  if (!names.length) {
    message.warning(t('edit.bettergiInputGroupNames'))
    return
  }
  const unknown = names.filter(n => !findCandidateByName(n))
  if (unknown.length) {
    message.warning(t('edit.bettergiGroupNamesUnknown', { names: unknown.join('、') }))
    return
  }
  for (const n of names) {
    const target = findCandidateByName(n)
    if (target) addToDragon(target)
  }
  addModal.name = ''
  addModal.open = false
}

// ---- 监听：BetterGI 现有自定义组在总开关开启时并入队列末尾 ----
watch(
  () => customGroupsTable.value.map(r => r.name).join('\u0001'),
  () => appendCustomRows(),
  { immediate: true }
)

watch(
  () => formData.Info.IfUseMasConfig,
  () => {
    if (!formData.Info.IfUseMasConfig) selectedGroupIdentity.value = null
  }
)

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
    // 初始化一条龙队列（8 内置 + 体力作战 + 已启用自定义组）
    initDragonList()
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

/* 配置组「左分栏 + 拖拽」 */
.bettergi-groups-layout {
  display: grid;
  grid-template-columns: 5fr 4fr;
  gap: 16px;
  align-items: start;
}

.bettergi-groups-pane {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  overflow: hidden;
}

.bettergi-groups-list-pane {
  padding-bottom: 8px;
}

.bettergi-groups-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.custom-groups-master-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ant-color-text);
  min-width: 0;
}

.bettergi-groups-list-hint {
  padding: 8px 14px 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.bettergi-groups-list {
  padding: 0 8px;
}

.group-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border: none;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.group-row:last-child {
  border-bottom: none;
}

.group-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.group-row-selected {
  background: var(--ant-color-primary-bg);
}

.group-row-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.group-row-chosen,
.group-row-drag {
  cursor: grabbing;
}

.group-row-ghost {
  opacity: 0.45;
  background: var(--ant-color-primary-bg);
}

/* 拖拽热区：占整行左 2/3（名称区），右侧胶囊保持可点击 */
.group-row-drag-area {
  flex: 2 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: grab;
}

.group-row-drag-handle {
  flex: 0 0 auto;
  padding: 4px;
  border-radius: 4px;
  color: var(--ant-color-text-quaternary);
  font-size: 15px;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.group-row-chosen .group-row-drag-area,
.group-row-drag .group-row-drag-area {
  cursor: grabbing;
}

.group-row-name {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-row-kind-tag {
  margin-inline-end: 0;
}

.group-row-capsule {
  flex: 0 0 auto;
}

.bettergi-groups-detail-pane {
  min-height: 180px;
  padding: 16px;
}

.bettergi-groups-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.bettergi-groups-detail-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.bettergi-groups-detail-name {
  min-width: 0;
}

.bettergi-groups-detail-desc {
  margin: 0 0 16px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.bettergi-groups-detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
}

@media (max-width: 900px) {
  .bettergi-groups-layout {
    grid-template-columns: 1fr;
  }
}

.bettergi-groups-toolbar-tip {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-row-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-row-kind-tag {
  margin-inline-end: 0;
  flex: 0 0 auto;
}

.group-row-prefix-stamina {
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning);
}

.group-row-prefix-custom {
  background: var(--ant-color-info-bg);
  color: var(--ant-color-info);
}

.group-row-frozen {
  opacity: 0.6;
}

.add-dragon-input {
  margin-bottom: 8px;
}

.add-dragon-input-tip {
  margin: 0 0 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.add-dragon-candidates {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 10px;
}

.add-dragon-candidate {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 16px;
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.add-dragon-candidate:hover {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-fill-tertiary);
}

.add-dragon-candidate-picked {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.add-dragon-candidate-disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.add-dragon-candidate-disabled:hover {
  border-color: var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.add-dragon-candidate-tag {
  flex: 0 0 auto;
  margin-inline-end: 0;
}

.add-dragon-candidate-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
