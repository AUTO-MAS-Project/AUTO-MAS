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
                  <!-- 通用战斗策略：点击输入框弹出备选弹窗，单选纯文本 -->
                  <a-input
                    :value="formData.OneDragon.AutoBossStrategyName"
                    readonly
                    :disabled="!formData.Info.IfUseMasConfig"
                    :placeholder="t('edit.bettergiEnterBattleStrategy')"
                    size="large"
                    class="modern-input bettergi-strategy-input"
                    @click="openStrategyPicker"
                  >
                    <template #suffix>
                      <CloseOutlined
                        v-if="formData.OneDragon.AutoBossStrategyName"
                        class="bettergi-strategy-clear"
                        @click.stop="clearBattleStrategy"
                      />
                      <DownOutlined v-else class="bettergi-strategy-arrow" />
                    </template>
                  </a-input>
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

                <div v-if="hasMultiSelection" class="bettergi-groups-multi-bar">
                  <span class="bettergi-groups-multi-count">
                    {{ t('edit.bettergiMultiSelected', { count: multiSelectedRows.length }) }}
                  </span>
                  <a-space size="small">
                    <a-button size="small" @click="batchToggleEnabled(true)">
                      {{ t('edit.bettergiMultiEnable') }}
                    </a-button>
                    <a-button size="small" @click="batchToggleEnabled(false)">
                      {{ t('edit.bettergiMultiDisable') }}
                    </a-button>
                    <a-button size="small" danger @click="batchRemoveSelected">
                      <template #icon><ClearOutlined /></template>
                      {{ t('edit.bettergiMultiRemove') }}
                    </a-button>
                  </a-space>
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
                  <template #item="{ element: item, index }">
                    <div
                      class="group-row"
                      :class="{
                        'group-row-selected': isRowSelected(item),
                        'group-row-multi': isRowMultiSelected(item),
                        'group-row-disabled': !groupsEditable || isGroupFrozen(item),
                        'group-row-frozen': isGroupFrozen(item),
                      }"
                      @contextmenu.prevent="handleRowContextMenu(item)"
                      @click="handleRowClick(item, index, $event)"
                    >
                      <!-- 可拖拽热区：覆盖整行左 2/3（名称区），仅右键菜单/开关在热区外 -->
                      <div class="group-row-drag-area">
                        <HolderOutlined class="group-row-drag-handle" aria-hidden="true" />
                        <span class="group-row-name">
                          <a-tag
                            size="small"
                            class="group-row-kind-tag"
                            :class="kindTagClass(item.kind)"
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
                        size="small"
                        :class="kindTagClass(selectedGroupIdentity.kind)"
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

                  <!-- 内置配置组：该任务在 BGI 一条龙里的可设置项（标签栏右侧可放大到独立弹窗） -->
                  <template v-if="selectedGroupIdentity.kind === 'builtin' && groupsEditable">
                    <BettergiDragonGroupSettings
                      class="bettergi-groups-settings"
                      :sections="currentGroupSettingSections"
                      :dragon-settings="dragonSettings"
                      :global-domain-settings="globalDomainSettings"
                      :domain-catalog="domainCatalog"
                      :boss-catalog="AUTO_BOSS_CATALOG"
                      :loading="dragonSettingsLoading"
                      :saving="dragonSettingsSaving"
                      :dirty="dragonSettingsDirty || globalDomainSettingsDirty"
                      @update="updateSettingField"
                      @save="saveDragonGroupSettings"
                      @pick-strategy="openStrategyPickerForField"
                    />
                  </template>
                  <!-- 配置组 / 脚本 / 路径：项目编辑面板（配置组=json 内 projects；JS/路径=单项目） -->
                  <BettergiGroupProjectEditor
                    v-else-if="isProjectEditorGroup && groupsEditable"
                    ref="groupProjectEditorRef"
                    class="bettergi-groups-settings"
                    :script-id="scriptId"
                    :user-id="userId"
                    :kind="selectedGroupIdentity.kind"
                    :group-name="selectedGroupIdentity.key"
                    :folder-name="projectEditorFolder"
                    :display-name="projectEditorDisplayName"
                    :editable="groupsEditable"
                    @add-script="openAddScriptToGroup"
                  />
                  <!-- 其余非内置（体力/其他自定义等）：无可设置项时给出提示 -->
                  <div
                    v-else-if="selectedGroupIdentity.kind !== 'builtin' && groupsEditable"
                    class="bettergi-groups-detail-note"
                  >
                    {{ t('edit.bettergiGroupSettingsNone') }}
                  </div>
                </template>
                <div v-else class="bettergi-groups-detail-empty"></div>
              </div>
            </div>
          </div>

          <!-- 战斗策略选择弹窗（点击输入框弹出；单选纯文本）。
               顶部「通用战斗策略」与右栏「首领讨伐-讨伐目标」共用：
               strategyPickerTargetField 为空时表示顶部（写 OneDragon.AutoBossStrategyName）；
               非空时表示右栏设置面板字段（写入 dragonSettings 由保存按钮统一落库） -->
          <a-modal
            v-model:open="strategyPickerOpen"
            :title="t('edit.bettergiBattleStrategy')"
            :footer="null"
            :cancel-text="t('edit.cancel')"
            width="560px"
            :z-index="1400"
            class="strategy-picker-modal"
            @cancel="strategyPickerOpen = false"
          >
            <div class="strategy-picker-list">
              <div
                v-for="opt in strategyOptions"
                :key="opt.value"
                class="add-dragon-candidate strategy-picker-candidate"
                :class="{ 'add-dragon-candidate-picked': opt.value === strategyPickerCurrentValue }"
                @click="pickBattleStrategy(opt.value)"
              >
                <span class="add-dragon-candidate-label">{{ opt.label }}</span>
              </div>
            </div>
            <p class="strategy-picker-tip">{{ t('edit.bettergiStrategyPickerTip') }}</p>
          </a-modal>

          <!-- 添加配置组弹窗：加入一条龙 或（配置组编辑器内）添加脚本到当前配置组
               后开的弹窗显示在之前弹窗之上：z-index 高于编辑器放大弹窗(1000)/设置弹窗(1100) -->
          <a-modal
            v-model:open="addModal.open"
            :title="addModalTitle"
            :ok-text="addModalOkText"
            :ok-button-props="{ disabled: !addModal.items.length && !addModal.draft.trim() }"
            :cancel-text="t('edit.cancel')"
            width="920px"
            :z-index="1200"
            class="add-dragon-modal"
            @ok="confirmAddToDragon"
            @cancel="cancelAddModal"
          >
            <!-- 顶部：标签输入（彩色气泡 + 行内输入） + 打开目录按钮 -->
            <div class="add-dragon-input-row">
              <div
                class="add-dragon-tag-editor add-dragon-input"
                :class="{ 'add-dragon-tag-editor-focus': addDraftFocused }"
                @click="handleTagEditorClick"
              >
                <span
                  v-for="chip in addModal.items"
                  :key="chip.chipUid"
                  class="add-dragon-tag-chip"
                  :class="[
                    kindTagClass(chip.kind),
                    { 'add-dragon-tag-chip-selected': isChipSelected(chip.chipUid) },
                  ]"
                  :title="t('edit.bettergiChipSelectHint')"
                  @mousedown="handleChipMouseDown(chip, $event)"
                  @mouseenter="handleChipMouseEnter(chip)"
                  @click.stop="handleChipClick(chip, $event)"
                >
                  <span class="add-dragon-tag-chip-label">{{ groupLabel(chip) }}</span>
                  <CloseOutlined
                    class="add-dragon-tag-chip-remove"
                    @mousedown.stop.prevent
                    @click.stop="removeAddChip(chip.chipUid)"
                  />
                </span>
                <input
                  ref="addDraftInputRef"
                  v-model="addModal.draft"
                  class="add-dragon-tag-draft-input"
                  :placeholder="addModal.items.length ? '' : t('edit.bettergiInputGroupNames')"
                  @focus="addDraftFocused = true"
                  @blur="addDraftFocused = false"
                  @keydown="handleAddDraftKeydown"
                  @click.stop="clearChipSelection()"
                />
              </div>
              <div class="add-dragon-dir-buttons">
                <a-space direction="vertical" size="small" class="add-dragon-dir-col">
                  <a-space size="small">
                    <a-button size="small" @click="openBettergiScriptSite">
                      <template #icon><GlobalOutlined /></template>
                      {{ t('edit.bettergiOpenScriptRepo') }}
                    </a-button>
                    <a-button size="small" @click="openBettergiDir('jsScript')">
                      <template #icon><FolderOpenOutlined /></template>
                      {{ t('edit.bettergiOpenScriptDir') }}
                    </a-button>
                    <a-button size="small" @click="openBettergiDir('autoPathing')">
                      <template #icon><FolderOpenOutlined /></template>
                      {{ t('edit.bettergiOpenTaskDir') }}
                    </a-button>
                  </a-space>
                  <a-space size="small">
                    <a-button size="small" @click="openBettergiScheduler">
                      <template #icon><PlayCircleOutlined /></template>
                      {{ t('edit.bettergiOpenBgi') }}
                    </a-button>
                    <a-button size="small" @click="openBettergiDir('oneDragon')">
                      <template #icon><FolderOpenOutlined /></template>
                      {{ t('edit.bettergiOpenOneDragonDir') }}
                    </a-button>
                    <a-button size="small" @click="openBettergiDir('scriptGroup')">
                      <template #icon><FolderOpenOutlined /></template>
                      {{ t('edit.bettergiOpenScriptGroupDir') }}
                    </a-button>
                  </a-space>
                </a-space>
              </div>
            </div>
            <p class="add-dragon-input-tip">{{ t('edit.bettergiInputGroupNamesTip') }}</p>

            <a-tabs v-model:activeKey="addModal.activeTab" size="small">
              <!-- Tab1：配置组（默认内置 + 专项体力 + BetterGI User/ScriptGroup 内容）→ 配置组模式冻结 -->
              <a-tab-pane key="scriptgroup" :tab="t('edit.bettergiTabScriptGroup')" :disabled="addModal.addToGroupMode">
                <div v-if="!addModal.groupCandidates.length" class="add-dragon-candidates-empty">
                  <a-empty :description="t('edit.bettergiScriptGroupEmptyDir')" />
                </div>
                <div v-else class="add-dragon-candidates">
                  <div
                    v-for="(candidate, index) in addModal.groupCandidates"
                    :key="`${candidate.kind}:${candidate.key}`"
                    class="add-dragon-candidate"
                    :class="{
                      'add-dragon-candidate-picked': isChipAdded(candidate),
                      'add-dragon-candidate-disabled': isCandidateBlocked(candidate),
                    }"
                    @click="handleGroupCandidateClick(candidate, index, $event)"
                  >
                    <a-tag
                      size="small"
                      class="add-dragon-candidate-tag"
                      :class="kindTagClass(candidate.kind)"
                    >
                      {{ groupPrefix(candidate) }}
                    </a-tag>
                    <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
                    <a-tag v-if="isGroupFrozen(candidate)" color="orange" size="small">
                      {{ t('edit.bettergiGroupFrozen') }}
                    </a-tag>
                    <a-tag v-else-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)" color="default" size="small">
                      {{ t('edit.bettergiInQueue') }}
                    </a-tag>
                  </div>
                </div>
              </a-tab-pane>

              <!-- Tab2：JS脚本（JS 脚本 / 自定义组候选） -->
              <a-tab-pane key="js" :tab="t('edit.bettergiTabJsScript')">
                <div v-if="!addModal.candidates.length" class="add-dragon-candidates-empty">
                  <a-empty :description="t('edit.bettergiTabJsEmpty')" />
                </div>
                <div v-else class="add-dragon-candidates">
                  <div
                    v-for="(candidate, index) in addModal.candidates"
                    :key="`${candidate.kind}:${candidate.key}`"
                    class="add-dragon-candidate"
                    :class="{
                      'add-dragon-candidate-picked': isChipAdded(candidate),
                      'add-dragon-candidate-disabled': isCandidateBlocked(candidate),
                    }"
                    @click="handleCandidateClick(candidate, index, $event)"
                  >
                    <a-tag
                      size="small"
                      class="add-dragon-candidate-tag"
                      :class="kindTagClass(candidate.kind)"
                    >
                      {{ groupPrefix(candidate) }}
                    </a-tag>
                    <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
                    <a-tag v-if="isGroupFrozen(candidate)" color="orange" size="small">
                      {{ t('edit.bettergiGroupFrozen') }}
                    </a-tag>
                    <a-tag v-else-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)" color="default" size="small">
                      {{ t('edit.bettergiInQueue') }}
                    </a-tag>
                  </div>
                </div>
              </a-tab-pane>

              <!-- Tab3：地图追踪（AutoPathing 左树右表） -->
              <a-tab-pane key="pathing" :tab="t('edit.bettergiTabPathing')" :force-render="true">
                <p class="add-dragon-pathing-hint">{{ t('edit.bettergiPathingSelectHint') }}</p>
                <div class="add-dragon-pathing-layout">
                  <a-tree
                    v-if="pathingTreeData.length"
                    class="add-dragon-pathing-tree"
                    :tree-data="pathingTreeData"
                    :default-expanded-keys="[pathingTreeData[0]?.key]"
                    :selected-keys="[selectedPathingKey]"
                    @select="handlePathingSelect"
                  />
                  <div v-else class="add-dragon-pathing-empty">
                    <a-empty :description="t('edit.bettergiPathingEmptyTree')" />
                  </div>
                  <div class="add-dragon-pathing-files">
                    <template v-if="selectedPathingFiles.length">
                      <div
                        v-for="(file, index) in selectedPathingFiles"
                        :key="file"
                        class="add-dragon-pathing-file"
                        @click="handlePathingFileClick(file, index, $event)"
                      >
                        <span class="add-dragon-pathing-file-name">{{ pathingDisplayName(file) }}</span>
                        <a-tag size="small" :class="kindTagClass('pathing')">
                          {{ t('edit.bettergiGroupKindPathing') }}
                        </a-tag>
                      </div>
                    </template>
                    <div v-else class="add-dragon-pathing-empty">
                      <a-empty :description="t('edit.bettergiPathingEmptyDir')" />
                    </div>
                  </div>
                </div>
              </a-tab-pane>
            </a-tabs>
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
  CloseOutlined,
  DownOutlined,
  FolderOpenOutlined,
  GlobalOutlined,
  HolderOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import {
  BetterGiService,
  type BetterGIDomainCatalogItem,
  type BetterGIPathingNode,
  type ComboBoxItem,
  type BetterGIUserConfig,
} from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useBettergiGuiSession } from '@/composables/useBettergiGuiSession'
import { useBettergiCustomGroups } from '@/composables/useBettergiCustomGroups'
import {
  fetchDomainCatalog,
  fetchGlobalDomainSettings,
  fetchOneDragonSettings,
  saveGlobalDomainSettings,
  saveOneDragonSettings,
} from '@/composables/useBettergiOneDragonSettings'
import WebhookManager from '@/components/WebhookManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import { openExternalUrl } from '@/utils/openExternal'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'
import BettergiDragonGroupSettings from './BettergiDragonGroupSettings.vue'
import BettergiGroupProjectEditor from './BettergiGroupProjectEditor.vue'

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
// 顺序为 MAS 默认一条龙顺序（体力作战插入其第 3 位，见 initDragonList）：
// 领取邮件 → 合成树脂 → 自动幽境危战 → 自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取尘歌壶奖励 → 领取每日奖励
const ONE_DRAGON_GROUPS = [
  { value: '领取邮件', labelKey: 'edit.bettergiGroupMail' },
  { value: '合成树脂', labelKey: 'edit.bettergiGroupResin' },
  { value: '自动幽境危战', labelKey: 'edit.bettergiGroupStygian' },
  { value: '自动地脉花', labelKey: 'edit.bettergiGroupLeyLine' },
  { value: '自动首领讨伐', labelKey: 'edit.bettergiGroupBoss' },
  { value: '自动秘境', labelKey: 'edit.bettergiGroupDomain' },
  { value: '领取尘歌壶奖励', labelKey: 'edit.bettergiGroupTeapot' },
  { value: '领取每日奖励', labelKey: 'edit.bettergiGroupDailyReward' },
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

// 自动战斗策略选项（「根据队伍自动选择」+ {RootPath}/User/AutoFight/*.txt），由后端实时读取
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

// 战斗策略选择弹窗（顶部通用 + 右栏首领讨伐共用）：
// strategyPickerTargetField 为空 → 写顶部 OneDragon.AutoBossStrategyName（即时保存）；
// 非空 → 写右栏 dragonSettings 对应字段（由「保存设置」统一落库）。
const strategyPickerOpen = ref(false)
/** 右栏目标字段（首领讨伐的 AutoBossStrategyName）；null=顶部通用战斗策略 */
const strategyPickerTargetField = ref<DragonSettingField | null>(null)
// 弹窗高亮的当前值：按目标字段来源取（顶部字段 / 右栏字段）
const strategyPickerCurrentValue = computed<string>(() => {
  const field = strategyPickerTargetField.value
  return field
    ? String(dragonSettings.value[field.key] ?? '')
    : String(formData.OneDragon.AutoBossStrategyName ?? '')
})
const openStrategyPicker = async () => {
  if (!formData.Info.IfUseMasConfig) return
  strategyPickerTargetField.value = null
  await loadStrategyOptions()
  strategyPickerOpen.value = true
}
// 右栏「首领讨伐-讨伐目标」字段发起：把弹窗目标指向该字段再打开
const openStrategyPickerForField = async (field: DragonSettingField) => {
  if (!formData.Info.IfUseMasConfig) return
  strategyPickerTargetField.value = field
  await loadStrategyOptions()
  strategyPickerOpen.value = true
}
const pickBattleStrategy = (value: string) => {
  const field = strategyPickerTargetField.value
  if (field) {
    updateSettingField(field, value)
  } else {
    formData.OneDragon.AutoBossStrategyName = value
    saveField('OneDragon.AutoBossStrategyName', value)
  }
  strategyPickerOpen.value = false
  strategyPickerTargetField.value = null
}
const clearBattleStrategy = () => {
  formData.OneDragon.AutoBossStrategyName = ''
  saveField('OneDragon.AutoBossStrategyName', '')
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
//  - 左栏列表即「一条龙队列」：其中的配置组按顺序执行。默认顺序 =
//    领取邮件 → 合成树脂 → 体力作战 → 自动幽境危战 → 自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取尘歌壶奖励 → 领取每日奖励。
//  - 行前缀 tag：内置 →「默认」；体力作战 →「专项」；自定义组 →「自定义」。
//  - 行内胶囊开关控制是否启用（内置 ↔ Groups；自定义 ↔ CustomGroups；体力作战为本地虚拟项）。
//  - 点击「添加配置组」：从候选（8 内置 + 体力作战 + BetterGI 现有自定义组）挑选，加入队列末尾。
//  - 右键某一配置组：从一条龙移除（内置移出 Groups、自定义移出 CustomGroups、体力作战移除并关闭）。
//  - 体力作战启用互斥：开启体力作战时，自动关闭并冻结「自动秘境 / 自动地脉花 / 自动首领讨伐」；
//    体力作战关闭或从一条龙移除后才解冻，三组可重新开启。
// 说明：BetterGI 内置组执行顺序与队列成员最终由后端一条龙 TaskOrder 决定，本次后端顺序化尚未
// 配套，左栏顺序/成员作为前端队列编排（dragonList）保留，待后端支持后映射 Groups/CustomGroups。
const STAMINA_COMBAT_KEY = '__mas_stamina_combat__'

type ConfigGroupKind = 'builtin' | 'stamina' | 'custom' | 'js' | 'pathing' | 'scriptgroup'

type ConfigGroupIdentity = {
  kind: ConfigGroupKind
  key: string // builtin/custom/js/pathing: 组名字面量或相对路径；stamina: STAMINA_COMBAT_KEY
  /** 队列行唯一实例标识：允许同一配置组重复添加时，每行都有独立 uid（拖拽/删除按行实例） */
  uid?: number
}

// 启用体力作战时自动关闭并冻结的官方内置组（专项接管刷取）
const STAMINA_FROZEN_BUILTINS = ['自动秘境', '自动地脉花', '自动首领讨伐', '自动幽境危战']

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
  if (item.kind === 'pathing') return t('edit.bettergiGroupKindPathing')
  if (item.kind === 'scriptgroup') return t('edit.bettergiGroupKindScriptGroup')
  // JS 脚本与现有自定义组同属「自定义」来源（按需求：JS 的 tag 改为自定义）
  return t('edit.bettergiGroupKindCustom')
}

// 前缀 tag 颜色（队列行/右栏详情/候选弹窗统一走同一套）：默认=灰、专项=紫、配置组=橘、
// 自定义&JS=蓝、路径=绿
const kindTagClass = (kind: ConfigGroupKind): string => {
  if (kind === 'stamina') return 'gi-kind-tag-stamina'
  if (kind === 'pathing') return 'gi-kind-tag-pathing'
  if (kind === 'scriptgroup') return 'gi-kind-tag-scriptgroup'
  if (kind === 'custom' || kind === 'js') return 'gi-kind-tag-custom'
  return 'gi-kind-tag-default'
}

// 可加入一条龙的 BetterGI 自定义 JS 脚本候选。
// value=脚本目录名（BetterGI 按目录名定位任务，落库/执行用它）；label=manifest 中文显示名（展示用）。
const jsScriptOptions = ref<{ label: string; value: string }[]>([])

// CustomGroups 中某名字是否命中 BetterGI JsScript 目录（来源为 JS 脚本时队列行标为 js 前缀）
const isJsScriptName = (name: string): boolean =>
  jsScriptOptions.value.some(o => o.value === name)

// BetterGI「配置组」候选：{RootPath}/User/ScriptGroup/*.json 的文件名（即组名）。
// value/label 均用文件名（不含 .json），BetterGI 一条龙按该名引用配置组。
const scriptGroupOptions = ref<{ label: string; value: string }[]>([])

// CustomGroups 中某名字是否命中 BetterGI ScriptGroup 配置组目录
const isScriptGroupName = (name: string): boolean =>
  scriptGroupOptions.value.some(o => o.value === name)

// JS 目录名 → manifest 中文显示名（候选/队列展示用；找不到时回退目录名）
const jsDisplayName = (folder: string): string =>
  jsScriptOptions.value.find(o => o.value === folder)?.label || folder

// 地图追踪目录树（BetterGIPathingNode）与常用目录/可执行文件路径的加载状态
const pathingTreeRoot = ref('')
const pathingTreeDirs = ref<BetterGIPathingNode[]>([])
const bettergiDirs = ref<{
  repoDir?: string
  jsScriptDir?: string
  autoPathingDir?: string
  oneDragonDir?: string
  scriptGroupDir?: string
  exePath?: string
}>({})
// 当前选中的目录节点 key（相对路径）
const selectedPathingKey = ref('')

// 地图追踪相对路径（不含 .json）→ 展示文件名（取路径最后一段）
const pathingDisplayName = (rel: string): string => {
  const seg = String(rel || '').split('/').filter(Boolean).pop()
  return seg || rel
}

// AutoPathing 目录树所有文件的相对路径集合（用于识别 pathing 行）
const pathingFileSet = computed<Set<string>>(() => {
  const set = new Set<string>()
  const walk = (nodes: BetterGIPathingNode[] | undefined) => {
    for (const n of nodes || []) {
      for (const f of n.files || []) set.add(f)
      walk(n.dirs)
    }
  }
  walk(pathingTreeDirs.value)
  return set
})

// CustomGroups 中某名字是否命中 AutoPathing 文件相对路径（来源为地图追踪时队列行标为 pathing 前缀）
const isPathingName = (name: string): boolean =>
  pathingTreeDirs.value.length > 0 && pathingFileSet.value.has(name)

const groupLabel = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return builtinGroupLabels.value[item.key] ?? item.key
  if (item.kind === 'stamina') return t('edit.bettergiGroupStamina')
  if (item.kind === 'js') return jsDisplayName(item.key)
  if (item.kind === 'pathing') return pathingDisplayName(item.key)
  return item.key
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
// 种子 = 8 内置（默认在列，enabled 由 Groups 表达）+ 体力作战（默认在列，默认关闭）。
// 默认顺序：领取邮件 → 合成树脂 → 体力作战 → 自动幽境危战 → 自动地脉花 →
//           自动首领讨伐 → 自动秘境 → 领取尘歌壶奖励 → 领取每日奖励
const initDragonList = () => {
  const order: ConfigGroupIdentity[] = []
  for (const g of ONE_DRAGON_GROUPS) {
    // 体力作战固定插入第 3 位：即「合成树脂」之后、「自动幽境危战」之前
    if (staminaInDragon.value && g.value === '自动幽境危战') {
      pushDragon(order, { kind: 'stamina', key: STAMINA_COMBAT_KEY })
    }
    pushDragon(order, { kind: 'builtin', key: g.value })
  }
  // 兜底：若「自动幽境危战」不在内置列表（理论不发生），体力作战追加到末尾避免丢失
  if (staminaInDragon.value && !order.some(i => i.kind === 'stamina')) {
    pushDragon(order, { kind: 'stamina', key: STAMINA_COMBAT_KEY })
  }
  // 自定义组仅在总开关开启时并入（来自 BetterGI 现有配置 / CustomGroups）
  if (groupsShowCustom.value) {
    for (const row of customGroupsTable.value) {
      const kind: ConfigGroupKind = resolveStoredRowKind(row.name)
      pushDragon(order, { kind, key: row.name })
    }
  }
  dragonList.value = order
}

// 由存储的自定义组名推断队列行来源类型：命中 JS 脚本目录→js；命中 AutoPathing 文件→pathing；
// 命中 ScriptGroup 配置组目录→scriptgroup；其余→custom
const resolveStoredRowKind = (name: string): ConfigGroupKind => {
  if (isJsScriptName(name)) return 'js'
  if (isPathingName(name)) return 'pathing'
  if (isScriptGroupName(name)) return 'scriptgroup'
  return 'custom'
}

// 把 BetterGI 侧新增的自定义组补入队列末尾（保留用户已删除的自定义组不回来）
const appendCustomRows = () => {
  if (!groupsShowCustom.value) return
  for (const row of customGroupsTable.value) {
    const item: ConfigGroupIdentity = {
      kind: resolveStoredRowKind(row.name),
      key: row.name,
    }
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
  clearMultiSelection()
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
  // 体力作战开启时刷取类官方内置组被冻结，禁止再次加入一条龙（防止把被接管的组写回后端 Groups）
  if (item.kind === 'builtin' && isGroupFrozen(item)) {
    message.warning(t('edit.bettergiGroupFrozenTip'))
    return
  }
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
  // 被移除的行若在多选中，同步剔除
  if (item.uid != null && multiSelectedUids.value.has(item.uid)) {
    const next = new Set(multiSelectedUids.value)
    next.delete(item.uid)
    multiSelectedUids.value = next
  }
}

// 右侧选中行：展示该配置组详情
const selectConfigGroup = (item: ConfigGroupIdentity) => {
  selectedGroupIdentity.value = { ...item }
}

// ---- 右栏「任务设置」：内置组 → BGI 一条龙可设置字段（按任务分组）----
// 字段 key 与 BGI 一条龙 JSON 顶层 camelCase 键一致（对应 res/templates 默认配置.json）；
// 少数字段来自 BGI 全局 config.json 段（source: 'globalDomain'，见「自动秘境-秘境刷取配置」）。
type DragonSettingField = {
  key: string
  label: string
  type: 'text' | 'number' | 'bool' | 'select' | 'multi' | 'strategy' | 'boss'
  min?: number
  max?: number
  step?: number
  /** select / multi 用：候选 */
  options?: { label: string; value: string }[]
  /** select 是否开启搜索过滤（首领等大候选集用） */
  searchable?: boolean
  /** BGI 原生灰色说明（帮助文案），渲染为 label 右侧的 help 图标 */
  help?: string
  /** bool 反向显示/写回（true=界面勾选时存 false；用于「原粹树脂耗尽模式」等反义开关） */
  invert?: boolean
  /** 数据来源：默认一条龙 per-user JSON；globalDomain 走 BGI 全局 config.json 段 */
  source?: 'dragon' | 'globalDomain'
  /** 受控字段：仅当 masterKey 对应值 === masterValue 时可编辑（masterInvert=true 则取反判断） */
  masterKey?: string
  masterValue?: unknown
  masterInvert?: boolean
  /** 受控不可编辑时是否隐藏（默认禁用+灰显，true 则隐藏） */
  hideWhenDisabled?: boolean
}

/** 每周秘境周表行：默认（兜底）或某天，三个 key 与 BGI 一条龙顶层键一致 */
type WeeklyDomainTableRow = {
  uid: string
  label: string
  partyKey: string
  domainKey: string
  rewardKey: string
}

/** 通用周表行：仅当行内所有列都可由普通字段描述时使用（如地脉花每周刷取） */
type WeeklyFieldTableRow = {
  uid: string
  label: string
  /** 各列字段（key 与 BGI 一条龙顶层键一致；options 用于 select 渲染） */
  fields: DragonSettingField[]
}

type DragonSettingSection = {
  title: string
  fields: DragonSettingField[]
  /** 每周秘境表格模式（开关 + 默认/周一~周日逐行表格）或地脉花「每周刷取」表格模式 */
  kind?: 'weekly-table' | 'weekly-field-table'
  enableField?: DragonSettingField
  weeklyRows?: WeeklyDomainTableRow[]
  /** 地脉花「每周刷取」表格模式（周一~周日，列=地区/任务类型/执行） */
  weeklyFieldRows?: WeeklyFieldTableRow[]
}

// ---- 地区/国家候选（与 BGI 各任务各自的下拉一致，不再共用一份）----
// 合成树脂合成台地区：BGI OneDragonFlowViewModel.CraftingBenchCountry
const CRAFTING_BENCH_REGION_OPTIONS = [
  { label: '枫丹', value: '枫丹' },
  { label: '稻妻', value: '稻妻' },
  { label: '璃月', value: '璃月' },
  { label: '蒙德', value: '蒙德' },
]
// 领取每日奖励的冒险者协会地区：BGI AdventurersGuildCountry
const ADVENTURERS_GUILD_REGION_OPTIONS = [
  { label: '挪德卡莱', value: '挪德卡莱' },
  { label: '枫丹', value: '枫丹' },
  { label: '稻妻', value: '稻妻' },
  { label: '璃月', value: '璃月' },
  { label: '蒙德', value: '蒙德' },
]
// 地脉花国家：BGI TaskSettingsPageViewModel.LeyLineOutcropCountryList
const LEY_LINE_COUNTRY_OPTIONS = [
  { label: '蒙德', value: '蒙德' },
  { label: '璃月', value: '璃月' },
  { label: '稻妻', value: '稻妻' },
  { label: '须弥', value: '须弥' },
  { label: '枫丹', value: '枫丹' },
  { label: '纳塔', value: '纳塔' },
  { label: '挪德卡莱', value: '挪德卡莱' },
  { label: '至冬', value: '至冬' },
]

// 地脉花类型：BGI LeyLineOutcropTypeList（启示之花=经验书，藏金之花=摩拉）
const LEY_LINE_TYPE_OPTIONS = [
  { label: '启示之花（经验书）', value: '启示之花' },
  { label: '藏金之花（摩拉）', value: '藏金之花' },
]

// 分解圣遗物星级：BGI TaskSettingsPageViewModel.ArtifactSalvageStarList = ["4","3","2","1"]
const ARTIFACT_STAR_OPTIONS = [
  { label: '4', value: '4' },
  { label: '3', value: '3' },
  { label: '2', value: '2' },
  { label: '1', value: '1' },
]

// 讨伐首领候选（按地区分组事实源）：BGI AutoBossData.CountryToBosses
// （蒙德/璃月/稻妻/须弥/枫丹/纳塔/挪德卡莱 共 41 个，无至冬分组）。
// 二级弹窗（地区 → 首领）由此目录驱动；value 存首领名（BGI AutoBossName 语义，
// 留空=不指定，由 BGI 按配置决定默认），显示「首领名称-地区」便于区分同名首领。
const AUTO_BOSS_CATALOG: { region: string; name: string; label: string }[] = [
  // 蒙德
  { region: '蒙德', name: '急冻树', label: '急冻树-蒙德' },
  { region: '蒙德', name: '无相之雷', label: '无相之雷-蒙德' },
  { region: '蒙德', name: '守望者·堕天', label: '守望者·堕天-蒙德' },
  // 璃月
  { region: '璃月', name: '爆炎树', label: '爆炎树-璃月' },
  { region: '璃月', name: '纯水精灵', label: '纯水精灵-璃月' },
  { region: '璃月', name: '古岩龙蜥', label: '古岩龙蜥-璃月' },
  { region: '璃月', name: '无相之岩', label: '无相之岩-璃月' },
  { region: '璃月', name: '遗迹巨蛇', label: '遗迹巨蛇-璃月' },
  { region: '璃月', name: '隐山猊兽', label: '隐山猊兽-璃月' },
  // 稻妻
  { region: '稻妻', name: '无相之火', label: '无相之火-稻妻' },
  { region: '稻妻', name: '恒常机关阵列', label: '恒常机关阵列-稻妻' },
  { region: '稻妻', name: '雷音权现', label: '雷音权现-稻妻' },
  { region: '稻妻', name: '魔偶剑鬼', label: '魔偶剑鬼-稻妻' },
  { region: '稻妻', name: '无相之水', label: '无相之水-稻妻' },
  // 须弥
  { region: '须弥', name: '掣电树', label: '掣电树-须弥' },
  { region: '须弥', name: '半永恒统辖矩阵', label: '半永恒统辖矩阵-须弥' },
  { region: '须弥', name: '翠翎恐蕈', label: '翠翎恐蕈-须弥' },
  { region: '须弥', name: '风蚀沙虫', label: '风蚀沙虫-须弥' },
  { region: '须弥', name: '无相之草', label: '无相之草-须弥' },
  { region: '须弥', name: '深罪浸礼者', label: '深罪浸礼者-须弥' },
  { region: '须弥', name: '兆载永劫龙兽', label: '兆载永劫龙兽-须弥' },
  // 枫丹
  { region: '枫丹', name: '歌裴莉娅的葬送', label: '歌裴莉娅的葬送-枫丹' },
  { region: '枫丹', name: '科培琉司的劫罚', label: '科培琉司的劫罚-枫丹' },
  { region: '枫丹', name: '实验性场力发生装置', label: '实验性场力发生装置-枫丹' },
  { region: '枫丹', name: '魔像督军', label: '魔像督军-枫丹' },
  { region: '枫丹', name: '千年珍珠骏麟', label: '千年珍珠骏麟-枫丹' },
  { region: '枫丹', name: '水形幻人', label: '水形幻人-枫丹' },
  { region: '枫丹', name: '铁甲熔火帝皇', label: '铁甲熔火帝皇-枫丹' },
  // 纳塔
  { region: '纳塔', name: '金焰绒翼龙暴君', label: '金焰绒翼龙暴君-纳塔' },
  { region: '纳塔', name: '灵觉隐修的迷者', label: '灵觉隐修的迷者-纳塔' },
  { region: '纳塔', name: '秘源机兵·构型械', label: '秘源机兵·构型械-纳塔' },
  { region: '纳塔', name: '秘源机兵·统御械', label: '秘源机兵·统御械-纳塔' },
  { region: '纳塔', name: '熔岩辉龙像', label: '熔岩辉龙像-纳塔' },
  { region: '纳塔', name: '深邃摹结株', label: '深邃摹结株-纳塔' },
  { region: '纳塔', name: '贪食匿叶龙山王', label: '贪食匿叶龙山王-纳塔' },
  // 挪德卡莱
  { region: '挪德卡莱', name: '蕴光月守宫', label: '蕴光月守宫-挪德卡莱' },
  { region: '挪德卡莱', name: '深黯魇语之主', label: '深黯魇语之主-挪德卡莱' },
  { region: '挪德卡莱', name: '超重型陆巡舰·机动战垒', label: '超重型陆巡舰·机动战垒-挪德卡莱' },
  { region: '挪德卡莱', name: '霜夜巡天灵主', label: '霜夜巡天灵主-挪德卡莱' },
  { region: '挪德卡莱', name: '蕴光月幻蝶', label: '蕴光月幻蝶-挪德卡莱' },
  { region: '挪德卡莱', name: '重拳出击鸭', label: '重拳出击鸭-挪德卡莱' },
]

// 周日/限时奖励序号候选：与 BGI 原生下拉（SundaySelectedValueList = ["", "1", "2", "3"]）一致。
// 0 与空串在 BGI 中都表示“默认/不指定”。
// 注：每日/每周秘境均以「weekly-table」渲染（奖励联动所选秘境的物品档位），此常量保留语义注释。

// 尘歌壶进壶方式：BGI OneDragonFlowViewModel.SereniteaPotTpTypes = ["地图传送", "尘歌壶道具"]
const SERENITEA_TP_OPTIONS = [
  { label: '地图传送', value: '地图传送' },
  { label: '尘歌壶道具', value: '尘歌壶道具' },
]

// 尘歌壶奖励对象：BGI SecretTreasureObjectList（含购买日期首项「每天重复」）
const SECRET_TREASURE_OPTIONS = [
  { label: '每天重复', value: '每天重复' },
  { label: '布匹', value: '布匹' },
  { label: '须臾树脂', value: '须臾树脂' },
  { label: '大英雄的经验', value: '大英雄的经验' },
  { label: '流浪者的经验', value: '流浪者的经验' },
  { label: '精锻用魔矿', value: '精锻用魔矿' },
  { label: '摩拉', value: '摩拉' },
  { label: '祝圣精华', value: '祝圣精华' },
  { label: '祝圣油膏', value: '祝圣油膏' },
]

// 周一到周日（BGI JSON 里的星期键前缀与展示名）
const WEEKDAY_KEYS = [
  { key: 'Monday', label: '周一' },
  { key: 'Tuesday', label: '周二' },
  { key: 'Wednesday', label: '周三' },
  { key: 'Thursday', label: '周四' },
  { key: 'Friday', label: '周五' },
  { key: 'Saturday', label: '周六' },
  { key: 'Sunday', label: '周日' },
]

// ---- 内置组 schema ----
// 字段 key：
//   - 默认与 BGI 一条龙 JSON 顶层键一致（PartyName/DomainName/AutoBoss*/LeyLine* 等）
//   - source:'globalDomain' 的字段对应 BetterGI 全局 config.json 段
//     （autoDomainConfig.specifyResinUse…/autoArtifactSalvageConfig.maxArtifactStar），
//     由后端按 scriptId 读写，不随用户/配置组切换。
// help 文本摘录自 BGI 界面灰字副说明，悬浮展示在字段 label 右侧。
const BUILTIN_GROUP_SETTING_SECTIONS: Record<string, DragonSettingSection[]> = {
  合成树脂: [
    {
      title: '合成树脂',
      fields: [
        { key: 'CraftingBenchCountry', label: '合成台地区', type: 'select', options: CRAFTING_BENCH_REGION_OPTIONS, help: '前往指定地区合成台合成浓缩树脂' },
        { key: 'MinResinToKeep', label: '合成后保留原粹树脂', type: 'number', min: 0, max: 200, help: '合成浓缩树脂后保留的原粹树脂数量' },
      ],
    },
  ],
  自动地脉花: [
    {
      title: '刷取设置',
      fields: [
        { key: 'LeyLineOneDragonMode', label: '跳过准备流程', type: 'bool', help: '跳过部分准备流程（例如传送回七天神像）。' },
        { key: 'LeyLineResinExhaustionMode', label: '树脂耗尽模式', type: 'bool', help: '按当前树脂与库存自动计算可刷次数，结束后自动停止。' },
        { key: 'LeyLineOpenModeCountMin', label: '刷取次数最小值', type: 'bool', help: '与手动次数取最小值，避免超过树脂可用次数。' },
        { key: 'LeyLineRunCount', label: '刷取次数', type: 'number', min: 0, help: '填 0 则使用独立任务配置。' },
      ],
    },
    {
      // 每周刷取：周一~周日 表格（列=地区/任务类型/执行）。执行=仅勾选的星期刷取；
      // 未勾选任何星期则每天执行（BGI 一条龙 JSON 顶层 LeyLineRun{Day}/LeyLine{Day}Country/
      // LeyLine{Day}Type，与旧的平铺 schema 字段一致，仅换表格布局）。
      title: '每周刷取',
      kind: 'weekly-field-table',
      fields: [],
      weeklyFieldRows: WEEKDAY_KEYS.map(({ key, label }) => ({
        uid: key,
        label,
        fields: [
          { key: `LeyLine${key}Country`, label: '地区', type: 'select' as const, options: LEY_LINE_COUNTRY_OPTIONS, help: '留空时使用独立任务默认设置。' },
          { key: `LeyLine${key}Type`, label: '任务类型', type: 'select' as const, options: LEY_LINE_TYPE_OPTIONS, help: '留空时使用独立任务默认设置。' },
          { key: `LeyLineRun${key}`, label: '执行', type: 'bool' as const, help: '仅勾选的星期执行；未勾选任何星期则每天执行。' },
        ],
      })),
    },
  ],
  自动秘境: [
    {
      // 领奖树脂设定 / 分解圣遗物 / 启用奖励识别：存于 BGI 全局 config.json 段（autoDomainConfig/autoArtifactSalvageConfig）
      title: '秘境刷取配置',
      fields: [
        { key: 'autoArtifactSalvage', label: '分解圣遗物', type: 'bool', source: 'globalDomain', help: '领取奖励后自动分解圣遗物。' },
        { key: 'maxArtifactStar', label: '分解圣遗物星级', type: 'select', source: 'globalDomain', options: ARTIFACT_STAR_OPTIONS, help: '分解的最高星级。' },
        { key: 'rewardRecognitionEnabled', label: '启用奖励识别', type: 'bool', source: 'globalDomain', help: '每轮领取后识别奖励名称与数量，任务结束打印汇总。' },
        { key: 'specifyResinUse', label: '领奖树脂设定', type: 'bool', source: 'globalDomain', help: '关闭=先用浓缩，后原粹，其余不用；开启=按下方配置数量使用树脂。' },
        { key: 'originalResinUseCount', label: '原粹树脂刷取次数', type: 'number', source: 'globalDomain', min: 0, masterKey: 'specifyResinUse', masterValue: true, hideWhenDisabled: true },
        { key: 'condensedResinUseCount', label: '浓缩树脂刷取次数', type: 'number', source: 'globalDomain', min: 0, masterKey: 'specifyResinUse', masterValue: true, hideWhenDisabled: true },
        { key: 'transientResinUseCount', label: '须臾树脂刷取次数', type: 'number', source: 'globalDomain', min: 0, masterKey: 'specifyResinUse', masterValue: true, hideWhenDisabled: true },
        { key: 'fragileResinUseCount', label: '脆弱树脂刷取次数', type: 'number', source: 'globalDomain', min: 0, masterKey: 'specifyResinUse', masterValue: true, hideWhenDisabled: true },
      ],
    },
    {
      // 每日秘境：队伍/秘境/周日或限时（勾选开启每日=WeeklyDomainEnabled 存 false；
      // 关闭则使用每周秘境周表）。与每周秘境同样以下拉选秘境 + 奖励联动。
      title: '每日秘境',
      kind: 'weekly-table',
      enableField: {
        key: 'WeeklyDomainEnabled',
        label: '开启每日秘境',
        type: 'bool',
        invert: true,
        help: '开启后按下方每日设置刷取；关闭则使用每周秘境周表（下方每日项冻结）。',
      },
      fields: [],
      weeklyRows: [
        {
          uid: 'daily',
          label: '每日',
          partyKey: 'PartyName',
          domainKey: 'DomainName',
          rewardKey: 'SundayEverySelectedValue',
        },
      ],
    },
    {
      // 每周秘境：默认行 + 周一~周日（开关关闭=走每日，此时每周项冻结）
      // 以周表（周几 × 队伍/秘境/奖励）呈现；奖励列按所选秘境显示三档产出物引导，
      // 实际仍把 0~3 序号写入 SelectedValue（BGI 语义不变）。
      title: '每周秘境',
      kind: 'weekly-table',
      enableField: {
        key: 'WeeklyDomainEnabled',
        label: '启用每周秘境刷取',
        type: 'bool',
        help: '启用后，每日刷取配置将会失效（下方每周项解冻）。',
      },
      fields: [],
      weeklyRows: [
        {
          uid: 'default',
          label: '默认',
          partyKey: 'PartyName',
          domainKey: 'DomainName',
          rewardKey: 'SundayWeeklySelectedValue',
        },
        ...WEEKDAY_KEYS.map(({ key, label }) => ({
          uid: key,
          label,
          partyKey: `${key}PartyName`,
          domainKey: `${key}DomainName`,
          rewardKey: `${key}SelectedValue`,
        })),
      ],
    },
  ],
  自动首领讨伐: [
    {
      title: '讨伐目标',
      fields: [
        { key: 'AutoBossName', label: '选择首领', type: 'boss', help: '部分首领因机制问题未添加。' },
        { key: 'AutoBossTeamName', label: '切换队伍', type: 'text', help: '留空则不更换队伍；例如：首领队。' },
        { key: 'AutoBossStrategyName', label: '选择战斗策略', type: 'strategy', help: '仅用于首领讨伐，不覆盖其他策略设置。' },
      ],
    },
    {
      title: '次数与树脂',
      fields: [
        { key: 'AutoBossSpecifyRunCount', label: '原粹树脂耗尽模式', type: 'bool', invert: true, help: '开启=刷至原粹树脂耗尽后停止，下方次数与树脂冻结；关闭=指定讨伐次数，可按下方配置。' },
        { key: 'AutoBossRunCount', label: '讨伐次数', type: 'number', min: 1, masterKey: 'AutoBossSpecifyRunCount', masterValue: true, help: '指定成功后按成功领取奖励次数停止。' },
        { key: 'AutoBossUseTransientResin', label: '原粹不足时使用须臾树脂', type: 'bool', masterKey: 'AutoBossSpecifyRunCount', masterValue: true, help: '原粹不足时使用须臾树脂补充。' },
        { key: 'AutoBossUseFragileResin', label: '原粹不足时使用脆弱树脂', type: 'bool', masterKey: 'AutoBossSpecifyRunCount', masterValue: true, help: '原粹不足时使用脆弱树脂补充。' },
      ],
    },
    {
      title: '战斗细节',
      fields: [
        { key: 'AutoBossReviveRetryCount', label: '角色死亡后重试次数', type: 'number', min: 0, help: '战斗中存在角色死亡时，复活后重新讨伐当前首领。' },
        { key: 'AutoBossReturnToStatueAfterEachRound', label: '每轮讨伐后返回七天神像', type: 'bool', help: '开启后每次领奖后先回血，再重新前往首领。' },
        { key: 'AutoBossRewardRecognitionEnabled', label: '启用奖励识别', type: 'bool', help: '每轮领取后识别奖励名称与数量，任务结束打印汇总。' },
        { key: 'AutoBossTimeout', label: '战斗超时（秒）', type: 'number', min: 1, help: '单轮战斗超时秒数，超时后按失败处理（默认 240）。' },
      ],
    },
  ],
  领取每日奖励: [
    {
      title: '每日奖励',
      fields: [
        { key: 'AdventurersGuildCountry', label: '领取奖励的冒险者协会', type: 'select', options: ADVENTURERS_GUILD_REGION_OPTIONS, help: '前往指定地区冒险者协会领取。' },
        { key: 'DailyRewardPartyName', label: '领取前切换队伍（好感队）', type: 'text', help: '用于给指定队伍加好感度；填写好感队名称。' },
      ],
    },
  ],
  领取尘歌壶奖励: [
    {
      title: '尘歌壶',
      fields: [
        { key: 'SereniteaPotTpType', label: '进壶方式选择', type: 'select', options: SERENITEA_TP_OPTIONS, help: '地图传送=大地图直达；尘歌壶道具=使用壶道具进入。' },
        { key: 'SecretTreasureObjects', label: '尘歌壶奖励对象', type: 'multi', options: SECRET_TREASURE_OPTIONS, help: '购买日期与商品（日期不影响领取好感和钱币）。' },
      ],
    },
  ],
}

// 当前选中内置组的设置分组（无字段返回空）
const currentGroupSettingSections = computed<DragonSettingSection[]>(() => {
  const sel = selectedGroupIdentity.value
  if (!sel || sel.kind !== 'builtin') return []
  return BUILTIN_GROUP_SETTING_SECTIONS[sel.key] || []
})

// ---- 配置组/脚本/路径：右栏项目编辑面板 ----
// scriptgroup=读取该配置组 json 的 projects；js/pathing=当作单项目配置组展示（双击可弹设置）
const isProjectEditorGroup = computed<boolean>(() => {
  const sel = selectedGroupIdentity.value
  if (!sel) return false
  return sel.kind === 'scriptgroup' || sel.kind === 'js' || sel.kind === 'pathing'
})
// 双击读设置的目标脚本目录：js 时即脚本目录名（key）；scriptgroup/pathing 无目录参数（由 json 内 folderName 决定）
const projectEditorFolder = computed<string>(() => {
  const sel = selectedGroupIdentity.value
  return sel?.kind === 'js' ? sel.key : ''
})
// 可读显示名（scriptgroup 内部用 json 里 name；js/pathing 用当前行 label）
const projectEditorDisplayName = computed<string>(() => {
  const sel = selectedGroupIdentity.value
  return sel ? groupLabel(sel) : ''
})

// 每周秘境秘境候选目录（产出表/tp.json 扫描；只随 scriptId，不随用户/配置组）
const domainCatalog = ref<BetterGIDomainCatalogItem[]>([])
// 当前组是否需要周表秘境目录（仅「自动秘境」的每周秘境表格模式需要）
const needDomainCatalog = computed<boolean>(() =>
  currentGroupSettingSections.value.some(s => s.kind === 'weekly-table')
)

// 一条龙 per-user 设置（每日秘境/每周秘境/首领/地脉花等，随用户与配置组切换）
const dragonSettings = ref<Record<string, unknown>>({})
const dragonSettingsLoading = ref(false)
const dragonSettingsSaving = ref(false)
const dragonSettingsDirty = ref(false)
// 全局 config.json 秘境刷取配置（领奖树脂/分解圣遗物/奖励识别；只随 scriptId，不随用户/配置组）
const globalDomainSettings = ref<Record<string, unknown>>({})
const globalDomainSettingsDirty = ref(false)
// 当前选中内置组是否有设置 schema（含每周秘境周表等非 fields 形态的分组）
const hasGroupSettingFields = computed<boolean>(
  () =>
    currentGroupSettingSections.value.some(
      s =>
        s.fields.length > 0 ||
        s.kind === 'weekly-table' ||
        s.kind === 'weekly-field-table'
    )
)

const dragonConfigName = computed<string>(() => formData.Task.OneDragonConfigName || '默认配置')

// 当前组的字段是否需要全局秘境段（触发 globalDomain 加载/保存）
const needGlobalDomainSettings = computed<boolean>(() =>
  currentGroupSettingSections.value.some(s =>
    s.fields.some(f => f.source === 'globalDomain')
  )
)

// 编辑字段：仅本地待保存（等点「保存设置」统一写回）；按数据来源分流到两个 store
const updateSettingField = (field: DragonSettingField, value: unknown) => {
  if (field.source === 'globalDomain') {
    globalDomainSettings.value = { ...globalDomainSettings.value, [field.key]: value }
    globalDomainSettingsDirty.value = true
  } else {
    dragonSettings.value = { ...dragonSettings.value, [field.key]: value }
    dragonSettingsDirty.value = true
  }
}

// 读取该用户一条龙配置设置项 + （如需要）全局秘境段（切换选中行时刷新）
const loadDragonGroupSettings = async () => {
  const sel = selectedGroupIdentity.value
  if (!sel || sel.kind !== 'builtin' || !userId.value) {
    dragonSettings.value = {}
    dragonSettingsDirty.value = false
    globalDomainSettings.value = {}
    globalDomainSettingsDirty.value = false
    return
  }
  if (!hasGroupSettingFields.value) return
  dragonSettingsLoading.value = true
  try {
    dragonSettings.value = await fetchOneDragonSettings(
      scriptId,
      userId.value,
      dragonConfigName.value
    )
    dragonSettingsDirty.value = false
    if (needGlobalDomainSettings.value) {
      globalDomainSettings.value = await fetchGlobalDomainSettings(scriptId)
    } else {
      globalDomainSettings.value = {}
    }
    globalDomainSettingsDirty.value = false
    if (needDomainCatalog.value) {
      domainCatalog.value = await fetchDomainCatalog(scriptId)
    } else {
      domainCatalog.value = []
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.bettergiGroupSettingsLoadFailed'))
  } finally {
    dragonSettingsLoading.value = false
  }
}

// 保存：一条龙字段写回 per-user 副本；globalDomain 字段写回 BetterGI 全局 config.json 段
const saveDragonGroupSettings = async () => {
  const sel = selectedGroupIdentity.value
  if (!sel || sel.kind !== 'builtin' || !userId.value) return
  if (dragonSettingsSaving.value) return
  dragonSettingsSaving.value = true
  try {
    if (dragonSettingsDirty.value) {
      await saveOneDragonSettings(scriptId, userId.value, dragonConfigName.value, dragonSettings.value)
      dragonSettingsDirty.value = false
    }
    if (globalDomainSettingsDirty.value) {
      await saveGlobalDomainSettings(scriptId, globalDomainSettings.value)
      globalDomainSettingsDirty.value = false
    }
    message.success(t('edit.bettergiGroupSettingsSaved'))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.bettergiGroupSettingsSaveFailed'))
  } finally {
    dragonSettingsSaving.value = false
  }
}

// 切换选中内置组时加载该组的设置项（分组标签页状态由子组件按 sections 变化自动重置）
watch(
  () => selectedGroupIdentity.value?.uid,
  () => {
    void loadDragonGroupSettings()
  }
)

// ---- 一条龙队列行多选（Shift 区间 / Ctrl 逐个）----
// 多选集合按 uid 记录（允许同类多实例时互不干扰）
const multiSelectedUids = ref<Set<number>>(new Set())
// Shift 区间选择的锚点行 uid（普通/Ctrl 点击时更新）
const multiAnchorUid = ref<number>(-1)

// 行是否在多选中
const isRowMultiSelected = (item: ConfigGroupIdentity): boolean =>
  item.uid != null && multiSelectedUids.value.has(item.uid)

// 当前多选中的行（按 dragonList 顺序，用于批量操作）
const multiSelectedRows = computed<ConfigGroupIdentity[]>(() =>
  dragonList.value.filter(i => i.uid != null && multiSelectedUids.value.has(i.uid))
)

// 是否处于多选状态（多于 1 行时展示批量操作）
const hasMultiSelection = computed<boolean>(() => multiSelectedRows.value.length > 1)

// 清空多选（单选切换/清空一条龙时调用）
const clearMultiSelection = () => {
  multiSelectedUids.value = new Set()
  multiAnchorUid.value = -1
}

// 行点击：普通=单选看详情（并作为后续 Shift 区间的锚点）；
// Ctrl=逐个切换多选；Shift=从锚点行到当前行区间多选。
const handleRowClick = (item: ConfigGroupIdentity, index: number, event: MouseEvent) => {
  if (!groupsEditable.value) return
  if (item.uid == null) return
  if (event.shiftKey) {
    // Shift 区间选择：锚点 uid 位于锚点行；按当前队列顺序圈选锚点行到当前行
    const anchorIndex = dragonList.value.findIndex(i => i.uid === multiAnchorUid.value)
    if (anchorIndex < 0) {
      // 无锚点（例如本次会话首次点击即 Shift）：以当前行为锚点，单选当前行
      multiAnchorUid.value = item.uid
      multiSelectedUids.value = new Set([item.uid])
      selectConfigGroup(item)
      return
    }
    const lo = Math.min(anchorIndex, index)
    const hi = Math.max(anchorIndex, index)
    const uids = new Set<number>()
    for (let i = lo; i <= hi; i += 1) {
      const uid = dragonList.value[i]?.uid
      if (uid != null) uids.add(uid)
    }
    multiSelectedUids.value = uids
    return
  }
  if (event.ctrlKey || event.metaKey) {
    multiAnchorUid.value = item.uid
    const next = new Set(multiSelectedUids.value)
    if (next.has(item.uid)) next.delete(item.uid)
    else next.add(item.uid)
    multiSelectedUids.value = next
    return
  }
  // 普通点击：清空多选集合，但保留当前行为后续 Shift 的锚点
  multiSelectedUids.value = new Set()
  multiAnchorUid.value = item.uid
  selectConfigGroup(item)
}

// 批量启停：把选中的每行切到 target（已处于目标状态的行跳过）
const batchToggleEnabled = (target: boolean) => {
  for (const row of multiSelectedRows.value) {
    if (!isGroupFrozen(row) && groupEnabled(row) !== target) {
      toggleConfigGroup(row)
    }
  }
}

// 批量移除选中行（确认后逐行移除）
const batchRemoveSelected = () => {
  const count = multiSelectedRows.value.length
  Modal.confirm({
    title: t('edit.bettergiMultiRemoveTitle'),
    content: t('edit.bettergiMultiRemoveContent', { count }),
    okText: t('edit.bettergiMultiRemove'),
    okButtonProps: { danger: true },
    cancelText: t('edit.cancel'),
    onOk: () => {
      const rows = [...multiSelectedRows.value]
      for (const row of rows) removeFromDragon(row)
      clearMultiSelection()
    },
  })
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

// 候选是否不可添加：重复开关关闭且已在队列，或被体力作战冻结的刷取内置组
const isCandidateBlocked = (candidate: ConfigGroupIdentity): boolean =>
  (!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)) || isGroupFrozen(candidate)

// 候选点击：冻结组给出冻结提示；已在队列（重复开关关闭时）提示已加入；其余填入输入框。
// 多选：Ctrl=逐个追加当前项；Shift=从锚点（上次普通/Ctrl 点击）到当前项的整段候选追加输入框。
const handleListCandidateClick = (
  list: ConfigGroupIdentity[],
  anchor: { value: number },
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) => {
  if (isGroupFrozen(candidate)) {
    message.warning(t('edit.bettergiGroupFrozenTip'))
    return
  }
  if (!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)) {
    warnAlreadyInDragon()
    return
  }
  if (event.shiftKey) {
    // Shift 区间选择：跳过区间内已在气泡中的项，避免与普通点击/Ctrl 点击造成首项重复添加
    const base = anchor.value >= 0 ? anchor.value : index
    const lo = Math.min(base, index)
    const hi = Math.max(base, index)
    for (let i = lo; i <= hi; i += 1) {
      const item = list[i]
      if (item && !isGroupFrozen(item) && !isChipAdded(item)) pickAddCandidate(item)
    }
    return
  }
  anchor.value = index
  pickAddCandidate(candidate)
}

// JS脚本 标签页：自定义组 + JS 脚本候选点击
const handleCandidateClick = (
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) => handleListCandidateClick(addModal.candidates, jsCandidateAnchor, candidate, index, event)

// 配置组 标签页：默认/专项/ScriptGroup 候选点击
const handleGroupCandidateClick = (
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) =>
  handleListCandidateClick(addModal.groupCandidates, groupCandidateAnchor, candidate, index, event)

// ---- 添加弹窗（标签页：配置组/JS脚本/地图追踪）----
// 气泡列表元素：一条龙实例身份 + 弹窗内自增 uid（用于去重展示/删除，与队列行 uid 无关）
type AddChipItem = ConfigGroupIdentity & { chipUid: number }

const addModal = reactive({
  open: false,
  items: [] as AddChipItem[],
  draft: '',
  activeTab: 'scriptgroup' as 'scriptgroup' | 'js' | 'pathing',
  /** true=配置组编辑器内「添加脚本」：冻结「配置组」标签页，仅可从 JS脚本/地图追踪选择加入配置组 */
  addToGroupMode: false,
  /** JS脚本 标签页候选：自定义组 + JS 脚本（不含默认/专项/配置组，那些归「配置组」标签页） */
  candidates: [] as ConfigGroupIdentity[],
  /** 配置组 标签页候选：8 内置（默认）+ 体力作战（专项）+ ScriptGroup 目录内容 */
  groupCandidates: [] as ConfigGroupIdentity[],
})

// 添加弹窗标题/确定按钮文案（按模式分流）
const addModalTitle = computed<string>(() =>
  addModal.addToGroupMode ? t('edit.bettergiAddScriptToGroup') : t('edit.bettergiAddToDragon')
)
const addModalOkText = computed<string>(() =>
  addModal.addToGroupMode
    ? t('edit.bettergiAddScriptToGroupOk')
    : t('edit.bettergiAddToDragonOk')
)

// 配置组编辑器 ref：确认「添加脚本」后把选中的 JS/路径追加进当前配置组 json
const groupProjectEditorRef = ref<{
  addProjects: (rows: unknown[]) => Promise<void>
  reload: () => Promise<void>
} | null>(null)

// 弹窗气泡自增 uid 与行内输入焦点状态
let addChipSeq = 0
const addDraftInputRef = ref<HTMLInputElement | null>(null)
const addDraftFocused = ref(false)

const focusAddDraftInput = () => {
  void nextTick(() => addDraftInputRef.value?.focus())
}

// 追加一个气泡（同一配置重复点击 → 生成独立实例气泡，对应重复添加语义）
const pushAddChip = (item: ConfigGroupIdentity) => {
  addModal.items.push({ ...item, chipUid: ++addChipSeq })
  focusAddDraftInput()
}

// 删除指定气泡（同时从选中集合移除）
const removeAddChip = (chipUid: number) => {
  addModal.items = addModal.items.filter(c => c.chipUid !== chipUid)
  unselectChip(chipUid)
}

// ---- 气泡选择（Shift 区间 / Ctrl 逐个 / 拖动框选）+ 回退键删除 ----
// 选中集合按 chipUid 记录
const chipSelectedUids = ref<Set<number>>(new Set())
// Shift 区间锚点 chipUid（普通/Ctrl 点击时更新）
const chipAnchorUid = ref<number>(-1)
// 鼠标拖动框选：左键按下起点 chipUid 与进行状态
const chipDragAnchorUid = ref<number>(-1)
const chipDragging = ref(false)

const isChipSelected = (chipUid: number): boolean => chipSelectedUids.value.has(chipUid)

// 点击输入区空白：聚焦草稿输入框并清除气泡选中
const handleTagEditorClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (target.closest('.add-dragon-tag-chip')) return
  clearChipSelection()
  focusAddDraftInput()
}

const clearChipSelection = () => {
  chipSelectedUids.value = new Set()
  chipAnchorUid.value = -1
}

const unselectChip = (chipUid: number) => {
  const next = new Set(chipSelectedUids.value)
  next.delete(chipUid)
  chipSelectedUids.value = next
  if (chipAnchorUid.value === chipUid) chipAnchorUid.value = -1
}

const selectChip = (chipUid: number) => {
  const next = new Set(chipSelectedUids.value)
  next.add(chipUid)
  chipSelectedUids.value = next
}

// 区间选择：[from, to]（含两端，按 addModal.items 当前顺序）
const selectChipRange = (fromUid: number, toUid: number) => {
  const indexOf = (uid: number) => addModal.items.findIndex(c => c.chipUid === uid)
  let lo = indexOf(fromUid)
  let hi = indexOf(toUid)
  if (lo < 0 && hi < 0) return
  if (lo < 0) lo = hi
  if (hi < 0) hi = lo
  const next = new Set<number>()
  for (let i = Math.min(lo, hi); i <= Math.max(lo, hi); i += 1) {
    next.add(addModal.items[i].chipUid)
  }
  chipSelectedUids.value = next
}

// 拖动状态：是否真的拖离了起点气泡（用于区分"拖动框选"与"普通单击"）
let chipDragMoved = false
// 拖动结束标记：确实拖动过的 mouseup 之后若紧随 click（松开于气泡上），忽略以免覆盖拖选结果
let chipDragJustFinished = false

// 气泡点击：普通=单选（并作 Shift 锚点）；Ctrl=逐个切换；Shift=区间选择
const handleChipClick = (chip: AddChipItem, event: MouseEvent) => {
  // 拖动框选刚结束的 click 忽略，避免把拖选区间重置为单点
  if (chipDragJustFinished) {
    chipDragJustFinished = false
    return
  }
  if (event.shiftKey) {
    const anchor = chipAnchorUid.value >= 0 ? chipAnchorUid.value : chip.chipUid
    selectChipRange(anchor, chip.chipUid)
    chipAnchorUid.value = chip.chipUid
    focusAddDraftInput()
    return
  }
  if (event.ctrlKey || event.metaKey) {
    if (chipSelectedUids.value.has(chip.chipUid)) unselectChip(chip.chipUid)
    else selectChip(chip.chipUid)
    chipAnchorUid.value = chip.chipUid
    focusAddDraftInput()
    return
  }
  chipSelectedUids.value = new Set([chip.chipUid])
  chipAnchorUid.value = chip.chipUid
  focusAddDraftInput()
}

// 气泡按下左键：进入拖动框选；注册一次 document mouseup 结束拖动
const handleChipMouseDown = (chip: AddChipItem, event: MouseEvent) => {
  if (event.button !== 0) return
  chipDragJustFinished = false
  chipDragMoved = false
  chipDragging.value = true
  chipDragAnchorUid.value = chip.chipUid
  const stop = () => {
    chipDragging.value = false
    chipDragAnchorUid.value = -1
    // 仅当确实拖动（经过其它气泡）时忽略随后的 click；单击选择不受影响
    if (chipDragMoved) {
      chipDragJustFinished = true
      window.setTimeout(() => {
        chipDragJustFinished = false
      }, 0)
    }
    window.removeEventListener('mouseup', stop)
    // 松开后回到输入框焦点，保证随后的 Backspace/Delete 能删除选中气泡
    focusAddDraftInput()
  }
  window.addEventListener('mouseup', stop)
}

// 拖动经过其它气泡：实时区间选择（从按下起点到当前气泡）
const handleChipMouseEnter = (chip: AddChipItem) => {
  if (!chipDragging.value || chipDragAnchorUid.value < 0) return
  if (chip.chipUid !== chipDragAnchorUid.value) chipDragMoved = true
  selectChipRange(chipDragAnchorUid.value, chip.chipUid)
}

// 回退键删除选中气泡；无选中时 Backspace 删除最后一个
const removeSelectedChips = () => {
  if (!chipSelectedUids.value.size) return
  addModal.items = addModal.items.filter(c => !chipSelectedUids.value.has(c.chipUid))
  clearChipSelection()
}

// 某候选是否已在气泡列表中（候选区 picked 高亮用）
const isChipAdded = (candidate: ConfigGroupIdentity): boolean =>
  addModal.items.some(c => c.kind === candidate.kind && c.key === candidate.key)

// JS 候选项 Shift 区间锚点（index in addModal.candidates）
const jsCandidateAnchor = ref(-1)
// 配置组 候选项 Shift 区间锚点（index in addModal.groupCandidates）
const groupCandidateAnchor = ref(-1)
// 地图追踪文件行 Shift 区间锚点（index in selectedPathingFiles）
const pathingFileAnchor = ref(-1)

// 加载可加入一条龙的 BetterGI 自定义 JS 脚本（实时扫描，反映玩家手工放置/订阅的脚本）
const loadJsScripts = async () => {
  try {
    const resp =
      await BetterGiService.getBettergiJsScriptsApiApiScriptsBettergiJsScriptsGet(scriptId)
    jsScriptOptions.value = (resp.data || [])
      .filter((item): item is ComboBoxItem & { label: string; value: string } =>
        item.label != null && item.value != null
      )
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 加载 BetterGI「配置组」候选（{RootPath}/User/ScriptGroup/*.json 文件名）
const loadScriptGroups = async () => {
  try {
    const resp =
      await BetterGiService.getBettergiScriptGroupsApiApiScriptsBettergiScriptGroupsGet(scriptId)
    scriptGroupOptions.value = (resp.data || [])
      .filter((item): item is ComboBoxItem & { label: string; value: string } =>
        item.label != null && item.value != null
      )
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 组装候选项，按标签页拆分：
//  - addModal.candidates（JS脚本 标签页）：JS 脚本 + 不在 ScriptGroup 目录的现有自定义组
//  - addModal.groupCandidates（配置组 标签页）：8 内置（默认）+ 体力作战（专项）+ ScriptGroup 目录内容
// 现有自定义组若命中 ScriptGroup 目录（如「锄地一条龙」），在配置组标签页以 ScriptGroup 形式出现，
// 故 JS脚本 标签页剔除，避免同一配置两个入口。
const buildCandidates = () => {
  // addToGroupMode（配置组内添加脚本）只允许可执行的 JS 脚本目录与地图追踪路径；
  // 原有自定义组（custom）不写入配置组 projects，故 JS脚本 标签仅列 js 候选。
  if (addModal.addToGroupMode) {
    addModal.candidates = jsScriptOptions.value.map(opt => ({ kind: 'js' as const, key: opt.value }))
    addModal.groupCandidates = []
    return
  }
  const jsItems: ConfigGroupIdentity[] = []
  const jsTaken = new Set<string>()
  for (const row of customGroupsTable.value) {
    const name = row.name
    if (!isScriptGroupName(name) && !jsTaken.has(name)) {
      jsItems.push({ kind: 'custom', key: name })
      jsTaken.add(name)
    }
  }
  for (const opt of jsScriptOptions.value) {
    if (!jsTaken.has(opt.value)) {
      jsItems.push({ kind: 'js', key: opt.value })
      jsTaken.add(opt.value)
    }
  }
  addModal.candidates = jsItems

  const groupItems: ConfigGroupIdentity[] = []
  const groupTaken = new Set<string>()
  for (const g of ONE_DRAGON_GROUPS) {
    groupItems.push({ kind: 'builtin', key: g.value })
    groupTaken.add(g.value)
  }
  groupItems.push({ kind: 'stamina', key: STAMINA_COMBAT_KEY })
  groupTaken.add(STAMINA_COMBAT_KEY)
  for (const opt of scriptGroupOptions.value) {
    if (!groupTaken.has(opt.value)) {
      groupItems.push({ kind: 'scriptgroup', key: opt.value })
      groupTaken.add(opt.value)
    }
  }
  addModal.groupCandidates = groupItems
}

// 普通「添加配置组到一条龙」弹窗
const openAddToDragonModal = async () => {
  addModal.addToGroupMode = false
  await openAddModalCommon('scriptgroup')
}

// 配置组编辑器「添加脚本」：复用同一弹窗但冻结「配置组」标签，只可加 JS 脚本/地图追踪到配置组
const openAddScriptToGroup = async () => {
  const sel = selectedGroupIdentity.value
  if (!sel || sel.kind !== 'scriptgroup' || !groupsEditable.value) return
  addModal.addToGroupMode = true
  await openAddModalCommon('js')
}

const openAddModalCommon = async (defaultTab: 'scriptgroup' | 'js' | 'pathing') => {
  addModal.items = []
  addModal.draft = ''
  addModal.activeTab = defaultTab
  jsCandidateAnchor.value = -1
  groupCandidateAnchor.value = -1
  pathingFileAnchor.value = -1
  clearChipSelection()
  addModal.open = true
  await loadCustomGroupsFromBettergi()
  await Promise.all([loadJsScripts(), loadScriptGroups(), loadBettergiDirs(), loadPathingTree()])
  buildCandidates()
}

// 关闭弹窗（两模式共用）
const cancelAddModal = () => {
  addModal.addToGroupMode = false
  clearChipSelection()
  addModal.open = false
}

// 把选中项转成 ScriptGroup json 的 project 行（js=目录名+manifest 名；pathing=相对路径文件夹/文件名）
const toScriptGroupProjectRow = (item: AddChipItem): Record<string, unknown> | null => {
  if (item.kind === 'js') {
    const folder = item.key
    if (!folder) return null
    return {
      name: jsDisplayName(folder),
      folderName: folder,
      index: 0,
      type: 'Javascript',
      status: 'Enabled',
      schedule: 'Daily',
      runNum: 1,
      allowJsNotification: true,
      allowJsHTTPHash: '',
      jsScriptSettingsObject: {},
    }
  }
  if (item.kind === 'pathing') {
    const rel = String(item.key || '').trim()
    if (!rel) return null
    const segments = rel.split('/')
    const file = segments.pop() || rel
    const folder = segments.join('/')
    return {
      name: `${file}.json`,
      folderName: folder,
      index: 0,
      type: 'Pathing',
      status: 'Enabled',
      schedule: 'Daily',
      runNum: 1,
    }
  }
  return null
}

// ---- 地图追踪（AutoPathing）目录树浏览 ----
// 树数据节点：key 为「目录路径」，files 为该目录下路径文件（不含 .json、含目录前缀）
type PathingTreeNode = {
  key: string
  title: string
  files?: string[]
  children?: PathingTreeNode[]
}

// 加载三个常用目录（打开按钮用）与 AutoPathing 目录树
const loadBettergiDirs = async () => {
  try {
    const resp = await BetterGiService.getBettergiScriptDirsApiApiScriptsBettergiDirsGet(scriptId)
    if (resp && resp.repoDir != null) {
      bettergiDirs.value = {
        repoDir: resp.repoDir,
        jsScriptDir: resp.jsScriptDir ?? undefined,
        autoPathingDir: resp.autoPathingDir ?? undefined,
        oneDragonDir: resp.oneDragonDir ?? undefined,
        scriptGroupDir: resp.scriptGroupDir ?? undefined,
        exePath: resp.exePath ?? undefined,
      }
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// BetterGI 官方在线脚本站（本地检出目录无法跳转其内部页面，改用网页版脚本仓库）
const BGI_SCRIPT_SITE = 'https://s.bettergi.com/'

// 打开某目录（脚本目录 / 任务目录 / 一条龙 / 配置组）；脚本仓库走在线网页
const openBettergiDir = async (kind: 'jsScript' | 'autoPathing' | 'oneDragon' | 'scriptGroup') => {
  if (!bettergiDirs.value.jsScriptDir) await loadBettergiDirs()
  const target =
    kind === 'jsScript'
      ? bettergiDirs.value.jsScriptDir
      : kind === 'autoPathing'
        ? bettergiDirs.value.autoPathingDir
        : kind === 'oneDragon'
          ? bettergiDirs.value.oneDragonDir
          : bettergiDirs.value.scriptGroupDir
  if (!target) {
    message.warning(t('edit.bettergiPathingEmptyTree'))
    return
  }
  try {
    await window.electronAPI.openFile(target)
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 打开 BetterGI 在线脚本仓库（官方网页版）
const openBettergiScriptSite = () => {
  void openExternalUrl(BGI_SCRIPT_SITE)
}

// 打开 BetterGI 调度器：启动 BGI 主程序（其 GUI 内置一条龙/调度入口）
const openBettergiScheduler = async () => {
  if (!bettergiDirs.value.exePath) await loadBettergiDirs()
  const exe = bettergiDirs.value.exePath
  if (!exe) {
    message.warning(t('edit.bettergiPathingEmptyTree'))
    return
  }
  try {
    await window.electronAPI.openFile(exe)
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 加载 AutoPathing 目录树
const loadPathingTree = async () => {
  try {
    const resp =
      await BetterGiService.getBettergiAutoPathingTreeApiApiScriptsBettergiAutoPathingTreeGet(
        scriptId
      )
    pathingTreeRoot.value = resp.root || ''
    pathingTreeDirs.value = resp.dirs || []
    // 默认选中第一个顶层目录，让右表立刻有内容
    const first = resp.dirs?.[0]
    if (first) selectedPathingKey.value = first.name
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 把后端目录树转为 a-tree 数据（key=目录相对路径，title=目录名，files 供右表）
const buildPathingTreeData = (
  nodes: BetterGIPathingNode[],
  parentKey = ''
): PathingTreeNode[] =>
  nodes.map(n => {
    const key = parentKey ? `${parentKey}/${n.name}` : n.name
    return {
      key,
      title: n.name,
      files: n.files || [],
      children: buildPathingTreeData(n.dirs || [], key),
    }
  })

const pathingTreeData = computed<PathingTreeNode[]>(() =>
  buildPathingTreeData(pathingTreeDirs.value)
)

// 当前选中的目录节点（展示其下文件）
const selectedPathingNode = computed<PathingTreeNode | null>(() => {
  const findNode = (nodes: PathingTreeNode[], key: string): PathingTreeNode | null => {
    for (const n of nodes) {
      if (n.key === key) return n
      const hit = findNode(n.children || [], key)
      if (hit) return hit
    }
    return null
  }
  return findNode(pathingTreeData.value, selectedPathingKey.value)
})

// 选中目录（含其全部子目录）下的路径文件，去重保序
const selectedPathingFiles = computed<string[]>(() => {
  const collect = (node: PathingTreeNode | null): string[] => {
    if (!node) return []
    const own = node.files || []
    const childFiles = (node.children || []).flatMap(c => collect(c))
    return [...new Set([...own, ...childFiles])]
  }
  return collect(selectedPathingNode.value)
})

const handlePathingSelect = (keys: (string | number)[]) => {
  const first = keys[0]
  selectedPathingKey.value = first != null ? String(first) : ''
  // 目录切换后右侧文件列表变化，重置 Shift 区间锚点
  pathingFileAnchor.value = -1
}

// 点击右表某路径文件：直接生成一个「路径」气泡（同文件多次点击=多个独立实例）
const pickPathingFile = (file: string) => {
  if (!groupsEditable.value) return
  pushAddChip({ kind: 'pathing', key: file })
}

// 地图文件行点击：普通=填入当前文件；Ctrl=逐个；Shift=从锚点区间批量填入输入框
const handlePathingFileClick = (file: string, index: number, event: MouseEvent) => {
  if (!groupsEditable.value) return
  if (event.shiftKey) {
    const anchor = pathingFileAnchor.value >= 0 ? pathingFileAnchor.value : index
    const lo = Math.min(anchor, index)
    const hi = Math.max(anchor, index)
    for (let i = lo; i <= hi; i += 1) {
      const item = selectedPathingFiles.value[i]
      if (item && !isChipAdded({ kind: 'pathing', key: item })) pickPathingFile(item)
    }
    return
  }
  pathingFileAnchor.value = index
  pickPathingFile(file)
}

// 候选点击：直接生成一个气泡（同配置重复点击=多个独立实例）
const pickAddCandidate = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  pushAddChip(item)
}

// 按名称在候选中定位配置组（内置按 value/翻译名，自定义按组名，体力作战按展示名）。
// JS脚本 与 配置组 两个标签页的候选都参与识别，保证行内手动输入也能命中。
// 配置组模式（添加脚本到配置组）下只允许 JS 脚本目录，故仅查 addModal.candidates。
const findCandidateByName = (name: string): ConfigGroupIdentity | undefined => {
  const list = addModal.addToGroupMode
    ? addModal.candidates
    : [...addModal.candidates, ...addModal.groupCandidates]
  return list.find(c => c.key === name || groupLabel(c) === name)
}

// 输入段解析：候选优先，命中 AutoPathing 相对路径（pathingFileSet）则按「路径」加入
const resolveInputName = (name: string): ConfigGroupIdentity | undefined => {
  const candidate = findCandidateByName(name)
  if (candidate) return candidate
  if (pathingFileSet.value.has(name)) return { kind: 'pathing', key: name }
  return undefined
}

// 拆分行内输入内容：支持「;」「；」分隔，返回去空白的组名字面量列表
const splitGroupNames = (raw: string): string[] =>
  (raw || '')
    .split(/[;；]/)
    .map(s => s.trim())
    .filter(Boolean)

// 提交行内草稿：每段必须全部可识别才生成气泡；有未知段则阻止并提示（拼写检查）
const commitAddDraft = (): boolean => {
  const names = splitGroupNames(addModal.draft)
  if (!names.length) return true
  const unknown = names.filter(n => !resolveInputName(n))
  if (unknown.length) {
    message.warning(t('edit.bettergiGroupNamesUnknown', { names: unknown.join('、') }))
    return false
  }
  for (const n of names) {
    const target = resolveInputName(n)
    if (target) pushAddChip(target)
  }
  addModal.draft = ''
  return true
}

// 行内输入按键：Enter 或「;」「；」提交草稿（拼写检查一致）；
// Backspace/Delete：删除选中的气泡（无选中时 Backspace 删除最后一个气泡）；输入法组合期忽略
const handleAddDraftKeydown = (e: KeyboardEvent) => {
  if (e.isComposing) return
  if (e.key === 'Enter' || e.key === ';' || e.key === '；') {
    e.preventDefault()
    commitAddDraft()
    return
  }
  const hasDraft = addModal.draft.trim().length > 0
  if (hasDraft) return
  if (e.key === 'Backspace' || e.key === 'Delete') {
    if (chipSelectedUids.value.size) {
      // 有选中气泡：删除选中的多个
      e.preventDefault()
      removeSelectedChips()
      return
    }
    if (e.key === 'Backspace' && addModal.items.length) {
      // 无选中：回退删除最后一个气泡
      e.preventDefault()
      removeAddChip(addModal.items[addModal.items.length - 1].chipUid)
    }
  }
}

// 确认：加入一条龙 或（配置组模式）作为项目写入当前配置组 json
const confirmAddToDragon = async () => {
  if (addModal.draft.trim() && !commitAddDraft()) return
  if (!addModal.items.length) {
    message.warning(t('edit.bettergiPickCandidateFirst'))
    return
  }
  const items = [...addModal.items]
  addModal.items = []
  addModal.draft = ''
  clearChipSelection()
  // 配置组模式：把 JS/路径转成 project 行，交给右栏编辑器追加并保存
  if (addModal.addToGroupMode) {
    const editor = groupProjectEditorRef.value
    const rows = items.map(toScriptGroupProjectRow).filter((r): r is Record<string, unknown> => r !== null)
    if (!rows.length) {
      addModal.addToGroupMode = false
      addModal.open = false
      message.warning(t('edit.bettergiAddScriptUnsupported'))
      return
    }
    addModal.addToGroupMode = false
    addModal.open = false
    try {
      await editor?.addProjects(rows)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.bettergiProjectSaveFailed'))
    }
    return
  }
  addModal.open = false
  for (const item of items) {
    addToDragon({ kind: item.kind, key: item.key })
  }
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
    // 先加载 JsScript 候选 / ScriptGroup 配置组目录 / AutoPathing 树 / 常用目录，
    // initDragonList 才能把自定义组中命中脚本目录、配置组目录或路径文件的行标为对应来源
    await Promise.all([
      loadJsScripts(),
      loadScriptGroups(),
      loadBettergiDirs(),
      loadPathingTree(),
    ])
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
  grid-template-columns: 4fr 6fr;
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

.group-row-multi {
  background: var(--ant-color-primary-bg);
  outline: 1px solid var(--ant-color-primary);
  outline-offset: -1px;
  box-shadow: inset 2px 0 0 var(--ant-color-primary);
}

.bettergi-groups-multi-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border: 1px solid var(--ant-color-primary-border);
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
}

.bettergi-groups-multi-count {
  font-size: 12px;
  color: var(--ant-color-primary);
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

/* 右栏「任务设置」区 */
.bettergi-groups-settings {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.bettergi-groups-tabs {
  max-width: 100%;
}

/* 无设置项的内置组（领取邮件等）空态提示 */
.bettergi-groups-settings-none {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  padding: 16px;
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
}

.bettergi-groups-settings-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 340px;
  overflow-y: auto;
  padding-right: 4px;
  padding-top: 4px;
}

.bettergi-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  transition: opacity 0.15s ease;
}
/* 受 master 开关联动的冻结行：整体灰显、控件不可点 */
.bettergi-setting-row.bettergi-setting-locked {
  opacity: 0.55;
}
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-switch),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-input-number),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-select),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-input),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-input-affix-wrapper) {
  pointer-events: none;
}

.bettergi-setting-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 1 auto;
  min-width: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
}
.bettergi-setting-label-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bettergi-setting-help-icon {
  flex: 0 0 auto;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  cursor: help;
}
.bettergi-setting-help-icon:hover {
  color: var(--ant-color-primary);
}

.bettergi-setting-row :deep(.ant-input-number),
.bettergi-setting-row :deep(.ant-select),
.bettergi-setting-row :deep(.ant-input),
.bettergi-setting-row :deep(.ant-input-affix-wrapper) {
  flex: 1 1 auto;
  min-width: 0;
}

.bettergi-setting-row :deep(.ant-input-number-input),
.bettergi-setting-row :deep(.ant-select-selection-item),
.bettergi-setting-row :deep(.ant-select-selection-placeholder),
.bettergi-setting-row :deep(.ant-input) {
  font-size: 14px;
}

.bettergi-groups-settings-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.bettergi-groups-detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
}

/* 专项（体力作战/幽境危战）与自定义/JS/路径配置组的无设置项提示 */
.bettergi-groups-detail-note {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  padding: 16px;
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
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

/* 前缀 tag 统一配色（antd 预设风格：浅色底 + 同色系深色文字）：
   默认=灰、专项=紫、自定义&JS=蓝、路径=绿 */
.gi-kind-tag-default {
  background: #f0f0f0;
  border-color: #d9d9d9;
  color: #404040;
}

.gi-kind-tag-stamina {
  background: #f9f0ff;
  border-color: #d3adf7;
  color: #531dab;
}

.gi-kind-tag-custom {
  background: #e6f4ff;
  border-color: #91caff;
  color: #0958d9;
}

.gi-kind-tag-pathing {
  background: #f6ffed;
  border-color: #b7eb8f;
  color: #389e0d;
}

.gi-kind-tag-scriptgroup {
  background: #fff7e6;
  border-color: #ffd591;
  color: #d46b08;
}

.add-dragon-candidates-empty {
  border: 1px dashed var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 24px 12px;
}

.group-row-frozen {
  opacity: 0.6;
}

.add-dragon-modal :deep(.ant-modal-body) {
  max-height: 70vh;
  overflow-y: auto;
}

.add-dragon-input-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.add-dragon-input-row .add-dragon-input {
  flex: 1 1 auto;
  margin-bottom: 0;
}

.add-dragon-dir-buttons {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.add-dragon-dir-buttons .ant-space {
  flex-wrap: wrap;
}

.add-dragon-input {
  margin-bottom: 8px;
}

/* 标签输入（气泡 + 行内草稿）：外观贴合 antd input，内部 chips 自动换行 */
.add-dragon-tag-editor {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 2px 11px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  cursor: text;
  transition: border-color 0.15s ease;
}

.add-dragon-tag-editor:hover {
  border-color: var(--ant-color-primary-hover);
}

.add-dragon-tag-editor-focus {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.add-dragon-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 1px 6px 1px 10px;
  font-size: 13px;
  line-height: 22px;
  border-radius: 11px;
  border: 1px solid transparent;
  cursor: default;
  user-select: none;
}

/* 选中气泡：主色描边 + 浅底（供 Shift/Ctrl/拖动框选后回退删除） */
.add-dragon-tag-chip-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 1px var(--ant-color-primary) inset;
}

.add-dragon-tag-chip-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-dragon-tag-chip-remove {
  flex: 0 0 auto;
  font-size: 10px;
  cursor: pointer;
  opacity: 0.6;
  padding: 2px;
  border-radius: 50%;
  transition:
    opacity 0.15s ease,
    background-color 0.15s ease;
}

.add-dragon-tag-chip-remove:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.08);
}

.add-dragon-tag-draft-input {
  flex: 1 1 120px;
  min-width: 120px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  line-height: 22px;
  color: var(--ant-color-text);
  padding: 1px 0;
}

.add-dragon-tag-draft-input::placeholder {
  color: var(--ant-color-text-quaternary, var(--ant-color-text-tertiary));
}

.add-dragon-input-tip {
  margin: 8px 0 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

/* 通用战斗策略：可点击输入框 + 选择弹窗 */
.bettergi-strategy-input {
  cursor: pointer;
}
.bettergi-strategy-input :deep(input) {
  cursor: pointer;
}
.bettergi-strategy-input.bettergi-strategy-input-disabled {
  cursor: not-allowed;
}
.bettergi-strategy-arrow,
.bettergi-strategy-clear {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  cursor: pointer;
  transition: color 0.15s ease;
}
.bettergi-strategy-arrow:hover,
.bettergi-strategy-clear:hover {
  color: var(--ant-color-primary);
}
.bettergi-strategy-clear {
  font-size: 12px;
}

.strategy-picker-modal :deep(.ant-modal-body) {
  padding-top: 16px;
}
.strategy-picker-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 10px;
}
.strategy-picker-candidate {
  cursor: pointer;
}
.strategy-picker-tip {
  margin: 10px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.add-dragon-pathing-hint {
  margin: 0 0 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.add-dragon-pathing-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 12px;
  min-height: 220px;
}

.add-dragon-pathing-tree {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.add-dragon-pathing-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.add-dragon-pathing-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.add-dragon-pathing-file:hover {
  background: var(--ant-color-fill-tertiary);
}

.add-dragon-pathing-file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-dragon-pathing-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
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
