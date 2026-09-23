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
        <a-button v-if="!!userId" size="large" :loading="folderLoading" @click="handleOpenFolder">
          <template #icon>
            <FolderOpenOutlined />
          </template>
          {{ t('comp.openConfigFolder') }}
        </a-button>
        <a-tooltip
          v-if="!showBettergiConfigMask && !pageLoading && masConfigEnabled"
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
            :disabled="pageLoading || !userId || configLocked"
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
          :disabled="pageLoading || !userId || configLocked"
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

    <!-- ══ BetterGI 配置/查看会话遮罩（配置会话保存设置、查看会话只读）══ -->
    <GuiSessionMask
      :open="showBettergiConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.bettergiConfiguringTitle')"
      :description="`${t('edit.bettergiConfiguringDesc')}\n${t('edit.bettergiConfiguringDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="bettergiWebsocketId"
          type="primary"
          size="large"
          :loading="stoppingBettergiConfig"
          @click="handleSaveBettergiConfig"
        >
          {{ t('edit.saveSettings') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showBettergiViewMask"
      :icon="EyeOutlined"
      :title="t('edit.bettergiViewingTitle')"
      :description="`${t('edit.bettergiViewingDesc')}\n${t('edit.bettergiViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          type="primary"
          size="large"
          :loading="stoppingBettergiConfig"
          @click="handleSaveBettergiConfig"
        >
          {{ t('edit.bettergiViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.basicInfo') }}</h3>
            </div>

            <!-- 基本信息布局：用户名:启用状态:剩余天数 = 2:1:1 -->
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
              <a-col :span="6">
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
              <a-col :span="6">
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

            <!-- 账户:密码 = 1:1 -->
            <a-row :gutter="24">
              <a-col :span="12">
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

            <!-- 账号 UID:游戏服务器 = 1:1 -->
            <a-row :gutter="24">
              <a-col :span="12">
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
                    @change="handleResourceChange"
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
            </a-row>

            <!-- 游戏客户端（用户级覆盖）：官服/B服/国际服是三个互相隔离的客户端；
                 渠道可识别时自动联动游戏服务器，无法识别或不一致时气泡提醒 -->
            <a-row :gutter="24">
              <a-col :span="24">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.bettergiGameClient') }}
                      <a-tooltip :title="t('edit.bettergiGameClientHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="gamePathInput"
                      :placeholder="gamePathPlaceholder"
                      size="large"
                      class="path-input"
                      @blur="handleGamePathSaved"
                    />
                    <a-button size="large" class="path-button" @click="selectGameClient">
                      <template #icon>
                        <FolderOpenOutlined />
                      </template>
                      {{ t('edit.pickFile') }}
                    </a-button>
                    <a-button
                      size="large"
                      class="path-button"
                      :disabled="!gamePathInput"
                      @click="clearGameClient"
                    >
                      {{ t('edit.bettergiGameClientRestore') }}
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="24">
                <!-- 快速配置开关已隐藏：按配置来源派生（直控 = 关，脚本 / 用户 = 开），
                     见 handleConfigModeChange 与后端 BetterGIUserConfig.load 的加载归一。 -->
                <GeneralConfigModeSelector
                  :model-value="formData.Info.Mode"
                  :options="bettergiConfigModeOptions"
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
            <a-flex
              class="section-header"
              justify="space-between"
              align="center"
              wrap="wrap"
              gap="small"
            >
              <h3>
                {{ t('edit.taskConfiguration') }}
                <a-tooltip :title="t('edit.bettergiTaskConfigHint')">
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </h3>
              <a-button size="small" @click="restoreOpen = true">
                <template #icon>
                  <HistoryOutlined />
                </template>
                {{ t('edit.configRestoreTitle') }}
              </a-button>
            </a-flex>

            <a-alert
              v-if="formData.Info.Mode === '直控'"
              type="info"
              show-icon
              class="mode-guide-alert"
            >
              <template #message>
                <span class="mode-guide-message">
                  {{ t('edit.bettergiDirectModeAlert') }}
                </span>
              </template>
            </a-alert>

            <a-alert
              v-if="masConfigEnabled"
              type="info"
              show-icon
              class="mode-guide-alert config-flow-hint"
            >
              <template #message>
                <span class="config-flow-title">{{ t('edit.bettergiMasConfigHowTo') }}</span>
              </template>
              <template #description>
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
                    :value="
                      masConfigEnabled
                        ? MAS_ONE_DRAGON_SLOT_NAME
                        : formData.Task.OneDragonConfigName
                    "
                    :options="
                      masConfigEnabled
                        ? [{ label: MAS_ONE_DRAGON_SLOT_NAME, value: MAS_ONE_DRAGON_SLOT_NAME }]
                        : oneDragonConfigOptions
                    "
                    :placeholder="t('edit.bettergiPickOneDragonName')"
                    size="large"
                    :disabled="masConfigEnabled"
                    show-search
                    option-filter-prop="label"
                    class="modern-input"
                    @dropdown-visible-change="
                      (open: boolean) => {
                        if (open && !masConfigEnabled) void loadOneDragonConfigs()
                      }
                    "
                    @change="
                      (v: string) => {
                        formData.Task.OneDragonConfigName = v
                        saveField('Task.OneDragonConfigName', v)
                      }
                    "
                  />
                </a-form-item>
              </a-col>
              <!-- 独立配置模式：领取奖励队伍；脚本直控模式：配置 BetterGI（打开 BGI 原生界面） -->
              <a-col :span="12">
                <a-form-item v-if="masConfigEnabled">
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
                    :disabled="!masConfigEnabled"
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
                <a-form-item v-else>
                  <template #label>
                    <!-- 空 label 占位：与左侧「一条龙名称」的下拉行高对齐 -->
                    <span class="form-label"></span>
                  </template>
                  <a-button
                    type="primary"
                    size="large"
                    block
                    :loading="bettergiConfigLoading"
                    :disabled="pageLoading || !userId"
                    @click="handleBettergiConfig"
                  >
                    <template #icon><SettingOutlined /></template>
                    {{ t('edit.bettergiConfigure') }}
                  </a-button>
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 战斗队伍/战斗策略与一条龙队列：仅「用户独立配置」下按用户可配 -->
            <template v-if="masConfigEnabled">
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
                        <!-- 行尾操作（右对齐）：左=另存为新配置组（scriptgroup/js/pathing 内容可复制成新组），
                           右=复制相同（所有可编辑行直接加一份相同配置组入队，无弹窗；内置/专项同此） -->
                        <span v-if="groupsEditable" class="group-row-actions" @click.stop>
                          <a-tooltip
                            v-if="canDuplicateGroup(item)"
                            :title="t('edit.bettergiDuplicateAsNew')"
                          >
                            <a-button
                              class="group-row-action-btn"
                              type="text"
                              size="small"
                              :disabled="isGroupFrozen(item)"
                              aria-label="另存为新配置组"
                              @click.stop="openDuplicateModal(item)"
                            >
                              <template #icon><SaveOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip :title="t('edit.bettergiRenameAsNew')">
                            <a-button
                              class="group-row-action-btn"
                              type="text"
                              size="small"
                              :disabled="isGroupFrozen(item) || !canRenameGroup(item)"
                              aria-label="修改配置组名称"
                              @click.stop="openRenameModal(item)"
                            >
                              <template #icon><EditOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip :title="t('edit.bettergiCopySameAs')">
                            <a-button
                              class="group-row-action-btn"
                              type="text"
                              size="small"
                              :disabled="isGroupFrozen(item)"
                              aria-label="复制相同配置组"
                              @click.stop="duplicateSameGroup(item)"
                            >
                              <template #icon><CopyOutlined /></template>
                            </a-button>
                          </a-tooltip>
                        </span>
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
                        <a-tag size="small" :class="kindTagClass(selectedGroupIdentity.kind)">
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
                        :global-stygian-settings="globalStygianSettings"
                        :domain-catalog="domainCatalog"
                        :boss-catalog="AUTO_BOSS_CATALOG"
                        :loading="dragonSettingsLoading"
                        :saving="dragonSettingsSaving"
                        :dirty="
                          dragonSettingsDirty ||
                          globalDomainSettingsDirty ||
                          globalStygianSettingsDirty
                        "
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
                      :group-name="projectEditorGroupName"
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
            </template>
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

          <!-- 另存为弹窗：以当前行为前名（基名），用户输入后名，生成「前名-后名」的新引用行（不复制真实配置组 JSON） -->
          <a-modal
            v-model:open="duplicateModal.open"
            :title="t('edit.bettergiDuplicateAsNew')"
            :ok-text="t('edit.bettergiDuplicateOk')"
            :cancel-text="t('edit.cancel')"
            :confirm-loading="duplicateModal.saving"
            :z-index="1500"
            width="480px"
            class="duplicate-group-modal"
            @ok="confirmDuplicateGroup"
            @cancel="duplicateModal.open = false"
          >
            <div class="duplicate-group-form">
              <p v-if="duplicateModal.source" class="duplicate-group-source">
                {{ t('edit.bettergiDuplicateSource', { name: duplicateSourceLabel }) }}
              </p>
              <a-input
                v-model:value="duplicateModal.suffix"
                :placeholder="t('edit.bettergiDuplicateNamePlaceholder')"
                :status="duplicateModal.error ? 'error' : ''"
                size="large"
                :maxlength="40"
                @input="duplicateModal.error = ''"
                @press-enter="confirmDuplicateGroup"
              />
              <p v-if="duplicateModal.error" class="duplicate-group-error">
                {{ duplicateModal.error }}
              </p>
              <p class="duplicate-group-tip">{{ t('edit.bettergiDuplicateTip') }}</p>
            </div>
          </a-modal>

          <!-- 修改名称弹窗：前名（配置组名称，仅前端展示的组级别名）与后名（名称备注，区分同名实例）分栏编辑。
               默认/专项两类的前名沿用系统固定名，窗口内锁定只读；两者都不进入 key，运行仍按原配置组执行。 -->
          <a-modal
            v-model:open="renameModal.open"
            :title="t('edit.bettergiRenameTitle')"
            :ok-text="t('edit.bettergiRenameOk')"
            :cancel-text="t('edit.cancel')"
            :confirm-loading="renameModal.saving"
            :z-index="1500"
            width="480px"
            class="rename-group-modal"
            @ok="confirmRename"
            @cancel="renameModal.open = false"
          >
            <div class="rename-group-form">
              <p v-if="renameModal.source" class="rename-group-source">
                {{ t('edit.bettergiRenameSource', { name: renameModal.source.key }) }}
              </p>
              <a-form layout="horizontal" :label-col="{ span: 6 }" :wrapper-col="{ span: 18 }">
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('edit.bettergiRenameNameLabel') }}</span>
                  </template>
                  <a-input
                    v-model:value="renameModal.name"
                    :placeholder="t('edit.bettergiRenameNamePlaceholder')"
                    :status="renameModal.error ? 'error' : ''"
                    :disabled="renameNameLocked"
                    size="large"
                    :maxlength="40"
                    @input="renameModal.error = ''"
                    @press-enter="confirmRename"
                  />
                </a-form-item>
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('edit.bettergiRenameSuffixLabel') }}</span>
                  </template>
                  <a-input
                    v-model:value="renameModal.suffix"
                    :placeholder="t('edit.bettergiRenamePlaceholder')"
                    size="large"
                    :maxlength="40"
                    @input="renameModal.error = ''"
                    @press-enter="confirmRename"
                  />
                </a-form-item>
              </a-form>
              <p v-if="renameNameLocked" class="rename-group-note">
                {{ t('edit.bettergiRenameLockedTip') }}
              </p>
              <p v-if="renameModal.error" class="rename-group-error">
                {{ renameModal.error }}
              </p>
              <p class="rename-group-tip">{{ t('edit.bettergiRenameTip') }}</p>
            </div>
          </a-modal>

          <!-- 添加配置组弹窗：加入一条龙 或（配置组编辑器内）添加脚本到当前配置组
               后开的弹窗显示在之前弹窗之上：z-index 高于编辑器放大弹窗(1000)/设置弹窗(1100) -->
          <a-modal
            v-model:open="addModal.open"
            :title="addModalTitle"
            :ok-text="addModalOkText"
            :ok-button-props="addModalOkButtonProps"
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
                    <a-button size="small" @click="openBettergiDir('keyMouse')">
                      <template #icon><FolderOpenOutlined /></template>
                      {{ t('edit.bettergiOpenKeyMouseDir') }}
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
              <a-tab-pane
                key="scriptgroup"
                :tab="t('edit.bettergiTabScriptGroup')"
                :disabled="addModal.addToGroupMode"
              >
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
                    <a-tag
                      v-else-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)"
                      color="default"
                      size="small"
                    >
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
                    <a-tag
                      v-else-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)"
                      color="default"
                      size="small"
                    >
                      {{ t('edit.bettergiInQueue') }}
                    </a-tag>
                  </div>
                </div>
              </a-tab-pane>

              <!-- Tab4：录制（KeyMouseScript 键鼠脚本） -->
              <a-tab-pane key="keymouse" :tab="t('edit.bettergiTabKeyMouse')">
                <div v-if="!addModal.keyMouseCandidates.length" class="add-dragon-candidates-empty">
                  <a-empty :description="t('edit.bettergiKeyMouseEmptyDir')" />
                </div>
                <div v-else class="add-dragon-candidates">
                  <div
                    v-for="(candidate, index) in addModal.keyMouseCandidates"
                    :key="`${candidate.kind}:${candidate.key}`"
                    class="add-dragon-candidate"
                    :class="{
                      'add-dragon-candidate-picked': isChipAdded(candidate),
                      'add-dragon-candidate-disabled': isCandidateBlocked(candidate),
                    }"
                    @click="handleKeyMouseCandidateClick(candidate, index, $event)"
                  >
                    <a-tag
                      size="small"
                      class="add-dragon-candidate-tag"
                      :class="kindTagClass(candidate.kind)"
                    >
                      {{ groupPrefix(candidate) }}
                    </a-tag>
                    <span class="add-dragon-candidate-label">{{ groupLabel(candidate) }}</span>
                    <a-tag
                      v-if="!ALLOW_DUPLICATE_GROUPS && inDragon(candidate)"
                      color="default"
                      size="small"
                    >
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
                        <span class="add-dragon-pathing-file-name">{{
                          pathingDisplayName(file)
                        }}</span>
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

      <!-- 队伍配置：位于「任务配置」下方，胶囊开关控制启停；开启后按「战斗场景」为战斗任务选队 -->
      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <BettergiTeamSettings
            :form-data="formData"
            :editable="formData.Info.IfUseMasConfig"
            :strategy-options="strategyOptions"
            :domain-catalog="domainCatalog"
            :boss-catalog="AUTO_BOSS_CATALOG"
            :leyline-country-options="LEY_LINE_COUNTRY_OPTIONS"
            :leyline-type-options="LEY_LINE_TYPE_OPTIONS"
            @save="saveField"
            @open-strategy-dir="openBettergiDir('autoFight')"
          />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="pageLoading"
            :script-id="scriptId"
            :user-id="userId"
            show-drop-statistics
            @save="saveField"
          />
        </a-form>
      </a-card>
    </ConfigLockPanel>

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、BetterGI 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :disabled="configLocked"
      :script-name="BETTERGI_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :user-desc="t('edit.bettergiConfigRestoreUserDesc')"
      :script-desc="t('edit.bettergiConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- mas 备份为字段侧车分区 + 副本文件摘要、native 备份为文件粒度 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewSections(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="s in previewSections(raw)" :key="s.name">
            <h4 class="bettergi-preview-title">{{ s.label }}</h4>
            <a-descriptions
              v-if="s.rows && s.rows.length"
              :column="1"
              size="small"
              bordered
              class="bettergi-preview-box"
            >
              <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </template>
        </div>
      </template>
    </ConfigRestoreSection>
  </div>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import draggable from 'vuedraggable'
import {
  ArrowLeftOutlined,
  ClearOutlined,
  CloseOutlined,
  CopyOutlined,
  EditOutlined,
  DownOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  GlobalOutlined,
  HistoryOutlined,
  HolderOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import {
  BetterGiService,
  Service,
  type BetterGIDomainCatalogItem,
  type BetterGIPathingNode,
  type ComboBoxItem,
  type BetterGIUserConfig,
} from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useBettergiGuiSession } from '@/composables/useBettergiGuiSession'
import { useBettergiCustomGroups } from '@/composables/useBettergiCustomGroups'
import {
  fetchDomainCatalog,
  fetchGlobalDomainSettings,
  fetchGlobalStygianSettings,
  fetchOneDragonSettings,
  saveGlobalDomainSettings,
  saveGlobalStygianSettings,
  saveOneDragonSettings,
} from '@/composables/useBettergiOneDragonSettings'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { openExternalUrl } from '@/utils/openExternal'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'
import BettergiDragonGroupSettings from './BettergiDragonGroupSettings.vue'
import BettergiGroupProjectEditor from './BettergiGroupProjectEditor.vue'
import BettergiTeamSettings from './BettergiTeamSettings.vue'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI用户编辑')
const route = useRoute()
const router = useRouter()
const {
  addUser,
  getUsers,
  updateUser,
  error: userApiError,
  openUserConfigFolder,
  loading: folderLoading,
} = useUserApi()
const { getScript } = useScriptApi()

const scriptId = route.params.scriptId as string

const handleOpenFolder = async () => {
  if (!userId.value) return
  await openUserConfigFolder(scriptId, userId.value)
}
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const { configLocked } = useScriptConfigLock(() => scriptId)
const scriptName = ref(t('edit.bettergiScriptFallbackName'))

const pageLoading = ref(true)
const isInitializing = ref(true)
const configModeSaving = ref(false)
const bettergiConfigModeOptions: Array<{
  title: string
  description: string
  value: string
  icon: 'database' | 'file' | 'setting'
  disabled?: boolean
  disabledReason?: string
}> = [
  {
    title: t('edit.scriptConfiguration'),
    description: t('edit.scriptConfiguration'),
    value: '脚本',
    icon: 'file',
    // 「脚本」运行时与「用户」同分支（均按 per-user MAS 配置运行），选了不生效——禁用并说明
    disabled: true,
    disabledReason: t('edit.scriptModeDisabled'),
  },
  {
    title: t('edit.perUserConfiguration'),
    description: t('edit.perUserConfiguration'),
    value: '用户',
    icon: 'database',
  },
  {
    title: t('edit.scriptDirectControl'),
    description: t('edit.useScriptSCurrent'),
    value: '直控',
    icon: 'setting',
  },
]
// 面板可见性由**配置来源**决定（维护者决策：放弃把快速配置当作来源开关）：直控 = 用 BGI
// 所选原生配置（显示原生「一条龙名称」与「配置 BetterGI」，MAS 不接管）；脚本/用户 = MAS 面板。
const masConfigEnabled = computed(() => formData.Info.Mode !== '直控')

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
// 顺序为 MAS 默认一条龙顺序（体力作战插在「自动幽境危战」之前，见 initDragonList）：
// 领取邮件 → 领取尘歌壶奖励 → 合成树脂 → 自动幽境危战 → 自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取每日奖励
const ONE_DRAGON_GROUPS = [
  { value: '领取邮件', labelKey: 'edit.bettergiGroupMail' },
  { value: '领取尘歌壶奖励', labelKey: 'edit.bettergiGroupTeapot' },
  { value: '合成树脂', labelKey: 'edit.bettergiGroupResin' },
  { value: '自动幽境危战', labelKey: 'edit.bettergiGroupStygian' },
  { value: '自动地脉花', labelKey: 'edit.bettergiGroupLeyLine' },
  { value: '自动首领讨伐', labelKey: 'edit.bettergiGroupBoss' },
  { value: '自动秘境', labelKey: 'edit.bettergiGroupDomain' },
  { value: '领取每日奖励', labelKey: 'edit.bettergiGroupDailyReward' },
]

const getDefaultUserData = (): Omit<BetterGIUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    RemainedDay: -1,
    Mode: '用户',
    IfQuickConfig: true,
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
    GamePath: '',
  },
  OneDragon: {
    Groups: ONE_DRAGON_GROUPS.map(group => group.value),
    DailyRewardPartyName: '',
    PartyName: '',
    AutoBossStrategyName: '',
    IfUseCustomGroups: false,
    CustomGroups: '[]',
    Queue: '[]',
    Plan: '',
    UseExecutionLayer: true,
    IfUseTeams: false,
    Teams: '[]',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendDropStatistics: true,
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
  if (configLocked.value) return false

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
const { enqueue, isSaving } = useSaveQueue()

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

  return enqueue(persist)
}

// ══ 游戏客户端（用户级覆盖）：透传 BetterGI 配置 + config.ini 渠道识别 ══
// 输入框直接以 BGI 维护的路径为默认值（可编辑）；存值规则：输入值与 BGI 当前
// 路径一致 → 存空（跟随语义，BGI 改了自动跟），否则存显式覆盖值。
// 渠道可识别时自动联动「游戏服务器」（国际服分不出区服，弹提示手选）；
// 渠道无法识别、或手选服务器与识别渠道不一致时气泡提醒（check() 运行时仍硬拦截）。
const gameClientInfo = ref<{
  installPath: string
  globalPath: string
  channel: string
} | null>(null)

const gamePathInput = ref('')

// BGI 全局路径缺失时的兜底提示（正常情况输入框默认值直接显示 BGI 路径）
const gamePathPlaceholder = computed(
  () => gameClientInfo.value?.globalPath || t('edit.bettergiGameClientPlaceholder')
)

const normalizePath = (path: string) =>
  path.replace(/\\/g, '/').replace(/\/+$/, '').trim().toLowerCase()

/** 用户服务器（Switch.Resource）→ 应使用的客户端渠道（与后端校验同口径） */
const RESOURCE_EXPECTED_CHANNEL: Record<string, string> = {
  官服: '官服',
  B服: 'B服',
  亚服: '国际服',
  欧服: '国际服',
  美服: '国际服',
  港澳台服: '国际服',
}

const channelLabel = (channel: string) => {
  switch (channel) {
    case '官服':
      return t('edit.bettergiChannelOfficial')
    case 'B服':
      return t('edit.bettergiChannelBili')
    case '国际服':
      return t('edit.bettergiChannelGlobal')
    default:
      return channel
  }
}

const syncGamePathInput = () => {
  gamePathInput.value =
    formData.Switch.GamePath || gameClientInfo.value?.globalPath || ''
}

/**
 * 渠道可识别时联动「游戏服务器」：
 * - 官服/B服客户端 → 自动切换（弹气泡告知）；
 * - 国际服客户端分不出区服 → 不猜，当前不是四服之一时提示手动指定；
 * - 渠道无法识别 → 提示手动指定区服。
 */
const syncResourceWithChannel = async () => {
  const channel = gameClientInfo.value?.channel
  if (!channel) {
    message.warning(t('edit.bettergiGameClientUnknownWarning'))
    return
  }
  if (channel === '国际服') {
    const intlServers = ['亚服', '欧服', '美服', '港澳台服']
    if (!intlServers.includes(formData.Switch.Resource)) {
      message.warning(t('edit.bettergiGameClientIntlWarning'))
    }
    return
  }
  if (formData.Switch.Resource !== channel) {
    formData.Switch.Resource = channel
    await saveField('Switch.Resource', channel)
    message.success(
      t('edit.bettergiGameClientSynced', {
        server:
          channel === '官服'
            ? t('edit.bettergiServerCn')
            : t('edit.bettergiServerBili'),
      })
    )
  }
}

const loadGameClientInfo = async () => {
  try {
    const resp = await BetterGiService.getBettergiGameInfoApiApiScriptsBettergiGameInfoGet(
      scriptId,
      formData.Switch.GamePath || ''
    )
    if (resp.status === 'success') {
      gameClientInfo.value = {
        installPath: resp.installPath || '',
        globalPath: resp.globalPath || '',
        channel: resp.channel || '',
      }
    } else {
      gameClientInfo.value = null
    }
  } catch {
    // 展示旁路：识别失败不影响配置编辑
    gameClientInfo.value = null
  }
  // 输入框默认值：用户配置优先，否则直接显示 BGI 维护的路径（可编辑）
  syncGamePathInput()
}

const handleGamePathSaved = async () => {
  const input = (gamePathInput.value || '').trim()
  const globalPath = gameClientInfo.value?.globalPath || ''
  // 输入值与 BGI 当前路径一致 → 存空（跟随），否则存显式覆盖
  const followsGlobal =
    !!globalPath && normalizePath(input) === normalizePath(globalPath)
  const next = followsGlobal ? '' : input
  if (next !== formData.Switch.GamePath) {
    formData.Switch.GamePath = next
    await saveField('Switch.GamePath', next)
  }
  await loadGameClientInfo()
  await syncResourceWithChannel()
}

/** 弹出文件选择并校验为原神主程序，取消/选错返回 null */
const pickGenshinExe = async (): Promise<string | null> => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'YuanShen.exe / GenshinImpact.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return null
  const fileName = path.split(/[\\/]/).pop()?.toLowerCase()
  if (fileName !== 'yuanshen.exe' && fileName !== 'genshinimpact.exe') {
    message.error(t('edit.bettergiGameClientInvalid'))
    return null
  }
  return path
}

const selectGameClient = async () => {
  const path = await pickGenshinExe()
  if (!path) return
  gamePathInput.value = path
  await handleGamePathSaved()
}

const clearGameClient = async () => {
  gamePathInput.value = gameClientInfo.value?.globalPath || ''
  await handleGamePathSaved()
}

const handleResourceChange = async (value: string) => {
  await saveField('Switch.Resource', value)
  const channel = gameClientInfo.value?.channel
  const expected = RESOURCE_EXPECTED_CHANNEL[value]
  if (!channel || !expected || expected === channel) return
  message.warning(
    t('edit.bettergiServerMismatchWarning', {
      server: channelLabel(value),
      channel: channelLabel(channel),
    })
  )
}

// 快速配置开关已隐藏（按配置来源派生），原先「关闭前先落盘一条龙组设置」的处理
// 移到了 handleConfigModeChange：切到直控时 MAS 面板会隐藏，效果等同。
const toggleGroup = (value: string) => {
  if (!masConfigEnabled.value) return
  const set = new Set(formData.OneDragon.Groups)
  if (set.has(value)) {
    set.delete(value)
  } else {
    set.add(value)
  }
  // 按内置顺序排序，保持后端一条龙 TaskOrder 稳定
  const groups = ONE_DRAGON_GROUPS.map(g => g.value).filter(v => set.has(v))
  const prev = formData.OneDragon.Groups
  formData.OneDragon.Groups = groups
  void saveField('OneDragon.Groups', groups).then(ok => {
    // 保存失败必须回滚并提示：否则界面显示与后端数据脱节（运行时按旧数据执行，
    // 出现「界面开着、实际没跑」的静默不一致，直到重新进入页面才被发现）
    if (!ok) {
      formData.OneDragon.Groups = prev
      message.error(`组开关「${value}」保存失败，已还原，请重试`)
    }
  })
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
// 弹窗高亮的当前值：按目标字段来源取（顶部字段 / 右栏字段：dragon/globalDomain/globalStygian）
const strategyPickerCurrentValue = computed<string>(() => {
  const field = strategyPickerTargetField.value
  if (!field) return String(formData.OneDragon.AutoBossStrategyName ?? '')
  if (field.source === 'globalStygian') {
    return String(globalStygianSettings.value[field.key] ?? '')
  }
  if (field.source === 'globalDomain') {
    return String(globalDomainSettings.value[field.key] ?? '')
  }
  return String(dragonSettings.value[field.key] ?? '')
})
const openStrategyPicker = async () => {
  if (!masConfigEnabled.value) return
  strategyPickerTargetField.value = null
  await loadStrategyOptions()
  strategyPickerOpen.value = true
}
// 右栏「首领讨伐-讨伐目标」字段发起：把弹窗目标指向该字段再打开
const openStrategyPickerForField = async (field: DragonSettingField) => {
  if (!masConfigEnabled.value) return
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
  listFromBettergi: listBgiCustomGroups,
  toggleMaster: toggleCustomGroupsMaster,
  deleteSelected: deleteSelectedCustomGroups,
  toggleEnabled: toggleCustomGroupEnabled,
  addByName: addCustomGroupByName,
} = useBettergiCustomGroups({
  scriptId,
  userId: () => userId.value,
  oneDragon: () => formData.OneDragon,
  configName: () => dragonConfigName.value,
  masConfig: () => masConfigEnabled.value,
  editable: () => masConfigEnabled.value,
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
// 说明：队列顺序与成员（含重复实例）持久化在 OneDragon.Queue（JSON 数组，元素
// {kind, name}），运行时后端按队列顺序重建一条龙 TaskOrder；行启停仍由
// Groups / CustomGroups 承载，体力作战为本地虚拟项不落库。
const STAMINA_COMBAT_KEY = '__mas_stamina_combat__'

type ConfigGroupKind =
  | 'builtin'
  | 'stamina'
  | 'custom'
  | 'js'
  | 'pathing'
  | 'scriptgroup'
  | 'keymouse'

type ConfigGroupIdentity = {
  kind: ConfigGroupKind
  key: string // builtin/custom/js/pathing: 组名字面量或相对路径；stamina: STAMINA_COMBAT_KEY
  /** 前名（配置组名称）：仅前端展示的组级别名，不进入 key、不影响运行；留空按来源类型回退默认名 */
  displayName?: string
  /** 后名（后缀别名）：仅作显示用，不进入 key；执行仍按 key（前名/基名）归一。留空即旧式「自动秘境」 */
  suffix?: string
  /** 队列行唯一实例标识：允许同一配置组重复添加时，每行都有独立 uid（拖拽/删除按行实例） */
  uid?: number
  /** 每实例独立启用状态：战斗 4 项走执行层 Plan，按此启停；其余组不使用此字段 */
  enabled?: boolean
  /**
   * 绑定的执行层 Plan 步骤 uid：同名多实例（如「自动秘境」×3）靠它定向排序——
   * 后端 build_combat_steps 按 planUid 精确匹配 Plan 步骤，队列拖拽顺序才能逐实例生效。
   * 由 persistDragonQueue 按行实例的 Plan 步骤名（stepNameIn）自动解析写入。
   */
  planUid?: string
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

// 「体力作战」专项暂未开展制作：功能开关保持关闭，队列与添加面板均不展示该虚拟项，
// 避免误导用户（待专项完成后置 true 即可恢复，相关逻辑保留在后文）。
const STAMINA_COMBAT_VISIBLE = false
// 体力作战是否已加入一条龙（本地虚拟项，默认加入）
const staminaInDragon = ref(STAMINA_COMBAT_VISIBLE)
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
const groupsEditable = computed(() => masConfigEnabled.value)
const groupsShowCustom = computed(
  () => formData.OneDragon.IfUseCustomGroups && masConfigEnabled.value
)

// 前缀 tag 文案
const groupPrefix = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return t('edit.bettergiGroupPrefixDefault')
  if (item.kind === 'stamina') return t('edit.bettergiGroupKindStamina')
  if (item.kind === 'pathing') return t('edit.bettergiGroupKindPathing')
  if (item.kind === 'scriptgroup') return t('edit.bettergiGroupKindScriptGroup')
  if (item.kind === 'keymouse') return t('edit.bettergiGroupKindKeyMouse')
  // JS 脚本与现有自定义组同属「脚本」来源（按需求：JS 的 tag 改为脚本）
  return t('edit.bettergiGroupKindCustom')
}

// 前缀 tag 颜色（队列行/右栏详情/候选弹窗统一走同一套）：默认=灰、专项=紫、配置组=橘、
// 脚本&JS=蓝、路径=绿、配置组=橙、录制=绯红
const kindTagClass = (kind: ConfigGroupKind): string => {
  if (kind === 'stamina') return 'gi-kind-tag-stamina'
  if (kind === 'pathing') return 'gi-kind-tag-pathing'
  if (kind === 'scriptgroup') return 'gi-kind-tag-scriptgroup'
  if (kind === 'keymouse') return 'gi-kind-tag-keymouse'
  if (kind === 'custom' || kind === 'js') return 'gi-kind-tag-custom'
  return 'gi-kind-tag-default'
}

// 可加入一条龙的 BetterGI 自定义 JS 脚本候选。
// value=脚本目录名（BetterGI 按目录名定位任务，落库/执行用它）；label=manifest 中文显示名（展示用）。
const jsScriptOptions = ref<{ label: string; value: string }[]>([])

// CustomGroups 中某名字是否命中 BetterGI JsScript 目录（来源为 JS 脚本时队列行标为 js 前缀）
const isJsScriptName = (name: string): boolean => jsScriptOptions.value.some(o => o.value === name)

// BetterGI「配置组」候选：{RootPath}/User/ScriptGroup/*.json 的文件名（即组名）。
// value/label 均用文件名（不含 .json），BetterGI 一条龙按该名引用配置组。
const scriptGroupOptions = ref<{ label: string; value: string }[]>([])

// CustomGroups 中某名字是否命中 BetterGI ScriptGroup 配置组目录
const isScriptGroupName = (name: string): boolean =>
  scriptGroupOptions.value.some(o => o.value === name)

// MAS 自建的配置组：运行期物化产物（MAS-{短id}-自定义配置组N / MAS-{短id}-执行层段N）
// 与切号组（MAS切换账号）、执行层资源模板组（MAS一条龙）。它们只应存在于运行期或
// BGI 副本目录，不该出现在「添加配置组」弹窗的「配置组」候选里。
const isMasOwnGroup = (name: string): boolean =>
  name.startsWith('MAS-') || name === 'MAS切换账号' || name === 'MAS一条龙'

// BetterGI「录制」候选：{RootPath}/User/KeyMouseScript/*.json 的文件名（即脚本名）。
const keyMouseOptions = ref<{ label: string; value: string }[]>([])

// CustomGroups 中某名字是否命中 BetterGI KeyMouseScript 录制目录（来源为录制时队列行标为录制前缀）
const isKeyMouseName = (name: string): boolean => keyMouseOptions.value.some(o => o.value === name)

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
  keyMouseScriptDir?: string
  autoFightDir?: string
  exePath?: string
}>({})
// 当前选中的目录节点 key（相对路径）
const selectedPathingKey = ref('')

// 地图追踪相对路径（不含 .json）→ 展示文件名（取路径最后一段）
const pathingDisplayName = (rel: string): string => {
  const seg = String(rel || '')
    .split('/')
    .filter(Boolean)
    .pop()
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

// 前名（配置组名称）按来源类型回退的默认显示名（未自定义别名时使用）
const defaultGroupBaseLabel = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return builtinGroupLabels.value[item.key] ?? item.key
  if (item.kind === 'stamina') return t('edit.bettergiGroupStamina')
  if (item.kind === 'js') return jsDisplayName(item.key)
  if (item.kind === 'pathing') return pathingDisplayName(item.key)
  return item.key
}

// 前名：用户自定义的「配置组名称」优先，未设置时回退默认名
const groupBaseLabel = (item: ConfigGroupIdentity): string =>
  item.displayName || defaultGroupBaseLabel(item)

const groupLabel = (item: ConfigGroupIdentity): string => {
  const base = groupBaseLabel(item)
  // 后名（后缀）仅作显示别名，与旧式「自动秘境」并存：有后缀显示「前名-后名」，无则仅前名
  return item.suffix ? `${base}-${item.suffix}` : base
}

// 战斗 4 项（秘境/地脉花/幽境危战/首领讨伐）支持「同组多实例」：每个实例独立开关与设置，
// 运行时经执行层（Plan）逐实例生效。其余组仍走全局开关（Groups / 自定义表），不进入 Plan。
const COMBAT_BUILTIN_SET = new Set<string>([
  '自动秘境',
  '自动地脉花',
  '自动幽境危战',
  '自动首领讨伐',
])

// 某队列实例在执行层 Plan 中的步骤名。
// 与「后名」彻底解耦：后名仅作前端展示区分，身份由**行实例 uid** 决定——
//   1) 未设后名的重复实例同样各自独立（否则同名会落到同一 Plan 步骤而共享设置）；
//   2) 改后名不会改变步骤名，已保存的每实例设置不会丢失。
// uid 最小者沿用基名（兼容旧 Plan 中已存在的「自动秘境」步骤），其余为「基名-uid」。
const stepNameIn = (row: ConfigGroupIdentity, rows: ConfigGroupIdentity[]): string => {
  // 体力作战是本地虚拟项，无实例概念
  if (row.kind === 'stamina') return row.key
  // 战斗组的实例命名规则推广到全部可重复配置组：uid 最小者沿用基名（兼容旧 Plan 中
  // 已存在的「自动秘境」步骤），其余为「基名-{uid}」。自定义组由此获得每实例身份，
  // 开关与设置各自独立（与「后名」解耦：后名仅作显示别名）。
  const uids = rows.filter(i => i.kind === row.kind && i.key === row.key).map(i => i.uid ?? 0)
  const firstUid = uids.length ? Math.min(...uids) : (row.uid ?? 0)
  return row.uid === firstUid ? row.key : `${row.key}-${row.uid}`
}
const stepNameOf = (row: ConfigGroupIdentity): string => stepNameIn(row, dragonList.value)

// 解析 OneDragon.Plan 中的步骤数组（兼容字符串 JSON / 对象 / 裸数组）
const parsePlanSteps = (raw: unknown): Array<Record<string, any>> => {
  if (!raw) return []
  let obj: any = raw
  if (typeof raw === 'string') {
    try {
      obj = JSON.parse(raw)
    } catch {
      return []
    }
  }
  if (Array.isArray(obj)) return obj
  if (obj && Array.isArray(obj.steps)) return obj.steps
  return []
}

// 读取 Plan 中各步骤的启用状态（按步骤名索引），用于初始化队列行的 per-instance 启停
const readPlanEnabled = (): Map<string, boolean> => {
  const m = new Map<string, boolean>()
  for (const s of parsePlanSteps((formData.OneDragon as any)?.Plan)) {
    if (s && typeof s.name === 'string') m.set(s.name, s.enabled !== false)
  }
  return m
}

// 乐观更新内存中的 Plan 步骤启用状态（下次读取/落库前保持界面一致）
const updatePlanStepEnabled = (name: string, enabled: boolean) => {
  const steps = parsePlanSteps((formData.OneDragon as any)?.Plan)
  let changed = false
  for (const s of steps) {
    if (s && s.name === name) {
      s.enabled = enabled
      changed = true
      break
    }
  }
  if (changed) (formData.OneDragon as any).Plan = JSON.stringify({ version: 1, steps })
}

// 调用后端：按步骤名翻转 Plan 中某战斗实例的启用状态
const setPlanStepEnabled = async (name: string, enabled: boolean): Promise<void> => {
  if (!scriptId || !userId.value || configLocked.value) return
  try {
    const resp =
      await BetterGiService.setOneDragonPlanStepEnabledApiScriptsBettergiOneDragonPlanStepEnabledPost(
        scriptId,
        userId.value,
        name,
        enabled
      )
    // 后端以 HTTP 200 + body.code 表达失败，需显式判定，否则开关静默不落库
    if (resp.code !== 200) {
      logger.error(resp.message || '一条龙步骤启用状态保存失败')
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 「配置组名称」（前名）是否锁定：默认（内置 8 组）与专项（体力作战）沿用系统固定名，
// 只允许改「名称备注」；其余来源（配置组 / JS 脚本 / 路径 / 录制 / 自定义）可自定义前名。
const isNameLocked = (item: ConfigGroupIdentity): boolean =>
  item.kind === 'builtin' || item.kind === 'stamina'

// 是否被体力作战冻结（启用体力作战时三个刷取内置组冻结）
const isGroupFrozen = (item: ConfigGroupIdentity): boolean =>
  item.kind === 'builtin' &&
  staminaCombatEnabled.value &&
  STAMINA_FROZEN_BUILTINS.includes(item.key)

const groupEnabled = (item: ConfigGroupIdentity): boolean => {
  // 战斗 4 项：每实例独立启停（来自 Plan step.enabled）
  if (item.kind === 'builtin' && COMBAT_BUILTIN_SET.has(item.key)) {
    return item.enabled !== false
  }
  if (item.kind === 'builtin') return formData.OneDragon.Groups.includes(item.key)
  if (item.kind === 'stamina') return staminaCombatEnabled.value
  // 自定义组：每实例独立启停（行实例自带 enabled），与战斗组实例行为一致
  return item.enabled !== false
}

// 队列是否包含某配置组
const inDragon = (item: ConfigGroupIdentity): boolean =>
  dragonList.value.some(i => i.kind === item.kind && i.key === item.key)

// 同步后端内置组启用集合（当前 Groups 含 enabled 列表 + 冻结时剔除冻结项）
const applyGroupsPatch = (next: string[]) => {
  const prev = formData.OneDragon.Groups
  formData.OneDragon.Groups = next
  void saveField('OneDragon.Groups', next).then(ok => {
    // 保存失败回滚并提示，避免界面与后端静默脱节（与 toggleGroup 同理）
    if (!ok) {
      formData.OneDragon.Groups = prev
      message.error('组开关保存失败，已还原，请重试')
    }
  })
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
  enabled: item.enabled ?? true,
  // 持久化过的 uid 必须沿用：它是每实例设置/启停的身份，重开会撞号导致设置串台
  uid: item.uid ?? ++dragonRowSeq,
})

// 队列行去重辅助（仅用于初始化；允许重复时不用此函数）
const pushDragon = (list: ConfigGroupIdentity[], item: ConfigGroupIdentity) => {
  if (!list.some(i => i.kind === item.kind && i.key === item.key)) list.push(makeDragonRow(item))
}

// 队列是否已初始化（初始化前的 appendCustomRows 不落库，避免把半成品队列写回）
let dragonListReady = false

// 读取已持久化的一条龙队列（OneDragon.Queue：JSON 数组，元素 {kind, name}）。
// 生成 API 模型重新生成前该字段尚无类型声明，这里做宽松读取；缺失/非法按未持久化处理。
const readStoredQueue = (): ConfigGroupIdentity[] => {
  const raw = (formData.OneDragon as unknown as Record<string, unknown>).Queue
  if (typeof raw !== 'string') return []
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(data)) return []
  const builtinNames = new Set(ONE_DRAGON_GROUPS.map(g => g.value))
  const rows: ConfigGroupIdentity[] = []
  for (const entry of data) {
    if (typeof entry !== 'object' || entry === null) continue
    const rec = entry as Record<string, unknown>
    const name = typeof rec.name === 'string' ? rec.name.trim() : ''
    if (!name) continue
    if (name === STAMINA_COMBAT_KEY) continue // 体力作战为本地虚拟项，不入持久化队列
    let kind: ConfigGroupKind
    if (builtinNames.has(name)) {
      kind = 'builtin' // 后端也会把内置组名强制归一为 builtin，这里双保险
    } else if (
      rec.kind === 'js' ||
      rec.kind === 'pathing' ||
      rec.kind === 'scriptgroup' ||
      rec.kind === 'keymouse'
    ) {
      kind = rec.kind
    } else {
      kind = resolveStoredRowKind(name)
    }
    const displayName = typeof rec.displayName === 'string' ? rec.displayName : undefined
    const suffix = typeof rec.suffix === 'string' ? rec.suffix : undefined
    const uid = typeof rec.uid === 'number' ? rec.uid : undefined
    const planUid = typeof rec.planUid === 'string' ? rec.planUid : undefined
    const enabled = typeof rec.enabled === 'boolean' ? rec.enabled : undefined
    rows.push(makeDragonRow({ kind, key: name, displayName, suffix, uid, planUid, enabled }))
  }
  // 第二遍：战斗组每实例启用状态来自 Plan；自定义组来自队列条目自带的 enabled。
  // 存量数据无该字段时回退按名查自定义组管理表，避免把用户已关闭的组误判为启用。
  const planEnabled = readPlanEnabled()
  for (const r of rows) {
    if (r.kind === 'builtin' && COMBAT_BUILTIN_SET.has(r.key)) {
      r.enabled = planEnabled.get(stepNameIn(r, rows)) ?? true
    } else if (r.kind !== 'builtin' && r.kind !== 'stamina' && r.enabled === undefined) {
      r.enabled = customGroupsTable.value.find(x => x.name === r.key)?.enabled ?? true
    }
  }
  // uid 已持久化：让自增序号跳过已用值，避免新行与既有行 uid 撞号
  for (const r of rows) {
    if (typeof r.uid === 'number' && r.uid > dragonRowSeq) dragonRowSeq = r.uid
  }
  return rows
}

// 把当前队列顺序/成员落库（体力作战行不持久化；运行时后端按此重建 TaskOrder）
const persistDragonQueue = () => {
  if (!dragonListReady || !groupsEditable.value) return
  // 战斗实例解析其 Plan 步骤 uid（按行实例的步骤名精确对应）；非战斗行无 planUid。
  // 后端 build_combat_steps 按 planUid 精确匹配 Plan 步骤——同名多实例（「自动秘境」×3）
  // 的拖拽顺序据此逐实例生效，不再退化为按 Plan 原顺序 FIFO。
  const planSteps = parsePlanSteps((formData.OneDragon as any)?.Plan)
  const entries = dragonList.value
    .filter(i => i.kind !== 'stamina')
    .map(i => {
      let planUid: string | undefined
      const stepName = stepNameIn(i, dragonList.value)
      if (i.kind === 'builtin' && COMBAT_BUILTIN_SET.has(i.key)) {
        planUid = planSteps.find(s => s && s.name === stepName)?.uid
      }
      const entry: Record<string, unknown> = {
        kind: i.kind,
        name: i.key,
        displayName: i.displayName,
        suffix: i.suffix,
        uid: i.uid,
        planUid,
      }
      // 实例名（组名-{uid}）：非首实例才有，供后端定位该实例独立的设置副本。
      // 内置组不写：BGI 一条龙只认内置基名，实例名会导致任务无法识别。
      if (stepName !== i.key && i.kind !== 'builtin') entry.step = stepName
      // 自定义组每实例开关（战斗组启用状态走 Plan，不写此字段）
      if (i.kind !== 'builtin') entry.enabled = i.enabled !== false
      return entry
    })
  void saveField('OneDragon.Queue', JSON.stringify(entries))
  // 存在战斗实例时确保执行层开启：否则 Plan 中的 per-instance 设置/启停不会被运行时消费
  const oneDragon = formData.OneDragon as unknown as Record<string, unknown>
  const hasCombat = dragonList.value.some(
    i => i.kind === 'builtin' && COMBAT_BUILTIN_SET.has(i.key)
  )
  if (hasCombat && oneDragon.UseExecutionLayer !== true) {
    oneDragon.UseExecutionLayer = true
    void saveField('OneDragon.UseExecutionLayer', true)
  }
}

// 依据用户数据初始化一条龙队列（loadUser 后调用一次，随后由增删/拖拽维护）：
// 已持久化队列优先（顺序与成员、含重复实例原样恢复）；否则种子 =
// 8 内置（默认在列，enabled 由 Groups 表达）+ 体力作战（默认在列，默认关闭）。
// 默认顺序：领取邮件 → 领取尘歌壶奖励 → 合成树脂 → 体力作战 → 自动幽境危战 →
//           自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取每日奖励
const initDragonList = () => {
  const stored = readStoredQueue()
  if (stored.length) {
    dragonList.value = stored
  } else {
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
        // 仅真实自定义组并入队列；路径/录制/ScriptGroup 各有独立入队口径，不在此镜像
        if (resolveStoredRowKind(row.name) !== 'custom') continue
        pushDragon(order, { kind: 'custom', key: row.name })
      }
    }
    // 与 readStoredQueue 第二遍一致：战斗组每实例启用态来自 Plan，自定义组缺省按管理表回退。
    // 新用户（无持久化队列）必须在此回显，否则战斗开关恒为默认开启、关闭后刷新即回弹
    // （一旦手动加一项使队列非空、走 if 分支才会正确显示，正是此 bug 的表象）。
    const planEnabledInit = readPlanEnabled()
    for (const r of order) {
      if (r.kind === 'builtin' && COMBAT_BUILTIN_SET.has(r.key)) {
        r.enabled = planEnabledInit.get(stepNameIn(r, order)) ?? true
      } else if (r.kind !== 'builtin' && r.kind !== 'stamina' && r.enabled === undefined) {
        r.enabled = customGroupsTable.value.find(x => x.name === r.key)?.enabled ?? true
      }
    }
    dragonList.value = order
  }
  dragonListReady = true
  // 持久化队列里没有、而 BetterGI 侧新增的自定义组仍补入队列末尾
  appendCustomRows()
}

// 由存储的自定义组名推断队列行来源类型：命中 JS 脚本目录→js；命中录制目录→keymouse；
// 命中 AutoPathing 文件→pathing；命中 ScriptGroup 配置组目录→scriptgroup；其余→custom
const resolveStoredRowKind = (name: string): ConfigGroupKind => {
  if (isJsScriptName(name)) return 'js'
  if (isKeyMouseName(name)) return 'keymouse'
  if (isPathingName(name)) return 'pathing'
  if (isScriptGroupName(name)) return 'scriptgroup'
  return 'custom'
}

// 把 BetterGI 侧新增的自定义组补入队列末尾（保留用户已删除的自定义组不回来）
const appendCustomRows = () => {
  if (!dragonListReady || !groupsShowCustom.value) return
  let appended = false
  for (const row of customGroupsTable.value) {
    // 仅真实自定义组镜像进队列；路径/录制/ScriptGroup 名各有独立入队口径，避免被当成配置组补进一条龙
    if (resolveStoredRowKind(row.name) !== 'custom') continue
    const item: ConfigGroupIdentity = { kind: 'custom', key: row.name }
    if (!inDragon(item)) {
      dragonList.value.push(makeDragonRow(item))
      appended = true
    }
  }
  if (appended) persistDragonQueue()
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
  persistDragonQueue()
}

// 行开关：内置写 Groups、体力作战本地翻转（互斥）、自定义交给 composable 持久化
const toggleConfigGroup = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (isGroupFrozen(item)) return
  // 战斗 4 项：每实例独立启停（写入 Plan step.enabled），基名仍保留在 Groups 供运行时纳入
  if (item.kind === 'builtin' && COMBAT_BUILTIN_SET.has(item.key)) {
    const next = !(item.enabled !== false)
    item.enabled = next
    updatePlanStepEnabled(stepNameOf(item), next)
    void setPlanStepEnabled(stepNameOf(item), next)
    return
  }
  if (item.kind === 'builtin') {
    toggleGroup(item.key)
  } else if (item.kind === 'stamina') {
    toggleStaminaCombat()
  } else {
    // 自定义组：翻转本行实例的 enabled 并落库（每实例独立，不再按名共用开关）
    item.enabled = !(item.enabled !== false)
    persistDragonQueue()
  }
}

// ---- 添加：把配置组加入一条龙（放到队列末尾）----
const addToDragon = (item: ConfigGroupIdentity): boolean => {
  if (configLocked.value) {
    message.error(t('edit.configLocked'))
    return false
  }
  if (!groupsEditable.value) return false
  if (!ALLOW_DUPLICATE_GROUPS && inDragon(item)) return false
  // 体力作战开启时刷取类官方内置组被冻结，禁止再次加入一条龙（防止把被接管的组写回后端 Groups）
  if (item.kind === 'builtin' && isGroupFrozen(item)) {
    message.warning(t('edit.bettergiGroupFrozenTip'))
    return false
  }
  if (item.kind === 'builtin') {
    if (!formData.OneDragon.Groups.includes(item.key)) {
      applyGroupsPatch([...formData.OneDragon.Groups, item.key])
    }
  } else if (item.kind === 'stamina') {
    staminaInDragon.value = true
  } else if (item.kind === 'pathing' || item.kind === 'keymouse') {
    // 路径/录制为独立队列项，不写入 CustomGroups（避免被当成自定义配置组污染一条龙）
  } else {
    // 自定义组：确保进入 CustomGroups（启用）并打开总开关
    if (addCustomGroupByName(item.key)) {
      if (!formData.OneDragon.IfUseCustomGroups) toggleCustomGroupsMaster()
    } else {
      const row = customGroupsTable.value.find(r => r.name === item.key)
      if (row && !row.enabled) toggleCustomGroupEnabled(row)
    }
  }
  // 追加到队列末尾：生成带唯一 uid 的行实例（重复开关开启时允许同一配置多次添加）。
  // 同组已有自定义前名时沿用到新实例，避免队列里同一个配置组显示两个名字。
  const alias = dragonList.value.find(i => i.kind === item.kind && i.key === item.key)?.displayName
  dragonList.value.push(makeDragonRow(alias ? { ...item, displayName: alias } : item))
  persistDragonQueue()
  return true
}

// 队列中是否仍存在同类配置组（删除某实例后判断是否还保留后端启用）
const hasSameKindRow = (item: ConfigGroupIdentity, exceptUid?: number): boolean =>
  dragonList.value.some(i => i.uid !== exceptUid && i.kind === item.kind && i.key === item.key)

// ---- 右键删除：从一条龙移除（按行实例 uid，一次只删一行）----
const removeFromDragon = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (configLocked.value) {
    message.error(t('edit.configLocked'))
    return
  }
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
  if (selectedGroupIdentity.value && selectedGroupIdentity.value.uid === item.uid) {
    selectedGroupIdentity.value = null
  }
  // 被移除的行若在多选中，同步剔除
  if (item.uid != null && multiSelectedUids.value.has(item.uid)) {
    const next = new Set(multiSelectedUids.value)
    next.delete(item.uid)
    multiSelectedUids.value = next
  }
  persistDragonQueue()
}

// 右侧选中行：展示该配置组详情
const selectConfigGroup = (item: ConfigGroupIdentity) => {
  selectedGroupIdentity.value = { ...item }
}

// ---- 右栏「任务设置」：内置组 → BGI 一条龙可设置字段（按任务分组）----
// 字段 key 与 BGI 一条龙 JSON 顶层 camelCase 键一致（对应 res/templates 默认配置.json）；
// 少数字段来自 BGI 全局 config.json 段（source: 'globalDomain'，见「自动秘境-刷取设置/次数与树脂」）。
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
  /** 数据来源：默认一条龙 per-user JSON；globalDomain/globalStygian 走 BGI 全局 config.json 段 */
  source?: 'dragon' | 'globalDomain' | 'globalStygian'
  /** 供模板 v-for key 去重：同一数据 key 可派生出多个界面字段（如互斥双开关） */
  id?: string
  /** 受控字段：仅当 masterKey 对应值 === masterValue 时可编辑（masterInvert=true 则取反判断） */
  masterKey?: string
  masterValue?: unknown
  masterInvert?: boolean
  /** 受控不可编辑时是否隐藏（默认禁用+灰显，true 则隐藏） */
  hideWhenDisabled?: boolean
}

/** 每周秘境周表行：默认（兜底）或某天，队伍/秘境/奖励/执行 key 与 BGI 一条龙顶层键一致；
    strategyKey / runKey 为 MAS 扩展（BGI 原生一条龙无 per-任务策略键与 per-天执行开关）。
    runKey 仅周一~周日行持有（default 行无此列），留空=该行不渲染执行开关 */
type WeeklyDomainTableRow = {
  uid: string
  label: string
  partyKey: string
  strategyKey: string
  domainKey: string
  rewardKey: string
  runKey?: string
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
  /** 每周秘境表格模式、地脉花「每周刷取」表格模式、或地脉花「每日地脉花」单日统一配置模式 */
  kind?: 'weekly-table' | 'weekly-field-table' | 'daily-leyline'
  enableField?: DragonSettingField
  weeklyRows?: WeeklyDomainTableRow[]
  /** 地脉花「每周刷取」表格模式（周一~周日，列=地区/任务类型/执行） */
  weeklyFieldRows?: WeeklyFieldTableRow[]
  /** 地脉花「每日地脉花」模式：单行统一配置（队伍/策略/地区/任务类型） */
  dailyFieldRow?: WeeklyFieldTableRow
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

// 幽境危战刷取战场：BGI AutoStygianOnslaughtConfig.BossNum = 1/2/3（三个 Boss 位）
const STYGIAN_BOSS_NUM_OPTIONS = [
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
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
        {
          key: 'CraftingBenchCountry',
          label: '合成台地区',
          type: 'select',
          options: CRAFTING_BENCH_REGION_OPTIONS,
          help: '前往指定地区合成台合成浓缩树脂',
        },
        {
          key: 'MinResinToKeep',
          label: '合成后保留原粹树脂',
          type: 'number',
          min: 0,
          max: 200,
          help: '合成浓缩树脂后保留的原粹树脂数量',
        },
      ],
    },
  ],
  自动幽境危战: [
    {
      // 刷取战场(bossNum)/战斗队伍(fightTeamName)/战斗策略(strategyName)/分解圣遗物(autoArtifactSalvage)：
      // 均存于 BGI 全局 config.json 的 autoStygianOnslaughtConfig 段（source: 'globalStygian'）。
      // 分解星级不在此配置：BGI 幽境 Param（AutoStygianOnslaughtParam）无 maxArtifactStar 参数，
      // 分解档位由全局 autoArtifactSalvageConfig 统一生效（在「自动秘境」面板配置）。
      // 队伍/策略与顶部「通用战斗队伍/策略」同段——面板非空运行时覆盖通用值，留空由通用兜底。
      title: '刷取设置',
      fields: [
        {
          key: 'bossNum',
          label: '刷取战场',
          type: 'select',
          source: 'globalStygian',
          options: STYGIAN_BOSS_NUM_OPTIONS,
          help: '选择要挑战的 Boss（1/2/3），不同编号对应幽境危战的不同战场。',
        },
        {
          key: 'fightTeamName',
          label: '战斗队伍',
          type: 'text',
          source: 'globalStygian',
          help: '填游戏内队伍名；留空不指定（由顶部「通用战斗队伍」兜底）。',
        },
        {
          key: 'strategyName',
          label: '战斗策略',
          type: 'strategy',
          source: 'globalStygian',
          help: '选择战斗策略；留空由顶部「通用战斗策略」兜底。',
        },
        {
          key: 'autoArtifactSalvage',
          label: '分解圣遗物',
          type: 'bool',
          source: 'globalStygian',
          help: '任务结束后自动分解圣遗物。',
        },
      ],
    },
    {
      // 次数与树脂：specifyResinUse=false=刷取至树脂耗尽 / true=按下方指定次数（两个互斥开关 UI）
      title: '次数与树脂',
      fields: [
        {
          id: 'stygian-exhaust',
          key: 'specifyResinUse',
          label: '刷取至树脂耗尽',
          type: 'bool',
          source: 'globalStygian',
          invert: true,
          help: '开启=刷至可用树脂耗尽后停止（与「指定树脂刷取次数」互斥）。',
        },
        {
          id: 'stygian-specify',
          key: 'specifyResinUse',
          label: '指定树脂刷取次数',
          type: 'bool',
          source: 'globalStygian',
          help: '开启=按下方指定次数刷取（与「刷取至树脂耗尽」互斥）。',
        },
        {
          key: 'originalResinUseCount',
          label: '原粹树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用原粹树脂的刷取次数。',
        },
        {
          key: 'condensedResinUseCount',
          label: '浓缩树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用浓缩树脂的刷取次数。',
        },
        {
          key: 'transientResinUseCount',
          label: '须臾树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用须臾树脂的刷取次数。',
        },
        {
          key: 'fragileResinUseCount',
          label: '脆弱树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用脆弱树脂的刷取次数。',
        },
      ],
    },
  ],
  自动地脉花: [
    {
      title: '刷取设置',
      fields: [
        {
          key: 'useAdventurerHandbook',
          label: '不使用冒险之证寻路',
          type: 'bool',
          help: '勾选后改用内置路线，不通过冒险之证定位地脉花。',
        },
        {
          key: 'LeyLineTimeout',
          label: '战斗超时(秒)',
          type: 'number',
          min: 0,
          help: '单次执行最长等待时间（秒）；0 表示不限制（使用 BetterGI 默认）。',
        },
      ],
    },
    {
      title: '次数与树脂',
      fields: [
        {
          key: 'LeyLineResinExhaustionMode',
          label: '树脂耗尽模式',
          type: 'bool',
          help: '按当前树脂与库存自动计算可刷次数，结束后自动停止。',
        },
        {
          key: 'LeyLineOpenModeCountMin',
          label: '刷取次数最小值',
          type: 'bool',
          help: '与手动次数取最小值，避免超过树脂可用次数。',
        },
        {
          key: 'LeyLineRunCount',
          label: '刷取次数',
          type: 'number',
          min: 0,
          help: '填 0 则使用独立任务配置。',
        },
        {
          key: 'useFragileResin',
          label: '使用脆弱树脂',
          type: 'bool',
          help: '原粹与浓缩耗尽后，允许使用脆弱树脂继续刷取。',
        },
        {
          key: 'useTransientResin',
          label: '使用须臾树脂',
          type: 'bool',
          help: '原粹与浓缩耗尽后，允许使用须臾树脂继续刷取。',
        },
      ],
    },
    {
      // 每日地脉花：与「每周刷取」互斥（共用 leyLineDailyEnabled 开关，invert 区分）。
      // 开启后使用每日统一的一套配置（队伍/策略/地区/任务类型/执行）。
      title: '每日地脉花',
      kind: 'daily-leyline',
      enableField: {
        key: 'leyLineDailyEnabled',
        label: '开启每日地脉花',
        type: 'bool',
        help: '开启后使用每日统一配置（队伍/策略/地区/任务类型/执行），与「每周刷取」互斥。',
      },
      fields: [
        {
          key: 'friendshipTeam',
          label: '领取前切换队伍（好感队）',
          type: 'text',
          masterKey: 'team',
          masterValue: '',
          masterInvert: true,
          help: '进入战斗前切换到该队伍，留空则不切换。必须填写战斗队伍后才能填写。',
        },
      ],
      dailyFieldRow: {
        uid: 'daily',
        label: '每日',
        fields: [
          { key: 'team', label: '队伍', type: 'text' },
          { key: 'combatStrategyPath', label: '策略', type: 'strategy' },
          { key: 'country', label: '地区', type: 'select', options: LEY_LINE_COUNTRY_OPTIONS },
          {
            key: 'leyLineOutcropType',
            label: '任务类型',
            type: 'select',
            options: LEY_LINE_TYPE_OPTIONS,
          },
        ],
      },
    },
    {
      // 每周地脉花：与「每日地脉花」互斥（共用 leyLineDailyEnabled 开关，invert 区分）。
      // 表格最前为「默认」行（无执行开关），当天某字段为空时按默认行兜底；
      // 列=队伍/策略/地区/任务类型/执行。执行开关默认关闭，全部关闭=当天不执行。
      title: '每周地脉花',
      kind: 'weekly-field-table',
      enableField: {
        key: 'leyLineDailyEnabled',
        label: '开启每周地脉花',
        type: 'bool',
        invert: true,
        help: '开启后按周一~周日分别配置，与「每日地脉花」互斥。',
      },
      fields: [
        {
          key: 'friendshipTeam',
          label: '领取前切换队伍（好感队）',
          type: 'text',
          masterKey: 'LeyLineDefaultTeam',
          masterValue: '',
          masterInvert: true,
          help: '进入战斗前切换到该队伍，留空则不切换。必须填写默认战斗队伍后才能填写。',
        },
      ],
      weeklyFieldRows: [
        {
          uid: 'default',
          label: '默认',
          fields: [
            { key: 'LeyLineDefaultTeam', label: '队伍', type: 'text' },
            { key: 'LeyLineDefaultStrategy', label: '策略', type: 'strategy' },
            {
              key: 'LeyLineDefaultCountry',
              label: '地区',
              type: 'select' as const,
              options: LEY_LINE_COUNTRY_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
            {
              key: 'LeyLineDefaultType',
              label: '任务类型',
              type: 'select' as const,
              options: LEY_LINE_TYPE_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
          ],
        },
        ...WEEKDAY_KEYS.map(({ key, label }) => ({
          uid: key,
          label,
          fields: [
            { key: `LeyLine${key}Team`, label: '队伍', type: 'text' as const },
            { key: `LeyLine${key}Strategy`, label: '策略', type: 'strategy' as const },
            {
              key: `LeyLine${key}Country`,
              label: '地区',
              type: 'select' as const,
              options: LEY_LINE_COUNTRY_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
            {
              key: `LeyLine${key}Type`,
              label: '任务类型',
              type: 'select' as const,
              options: LEY_LINE_TYPE_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
            {
              key: `LeyLineRun${key}`,
              label: '执行',
              type: 'bool' as const,
              help: '仅勾选的星期执行；未勾选则不执行。',
            },
          ],
        })),
      ],
    },
  ],
  自动秘境: [
    {
      // 分解圣遗物 / 启用奖励识别：存于 BGI 全局 config.json 段（autoDomainConfig/autoArtifactSalvageConfig）
      title: '刷取设置',
      fields: [
        {
          key: 'autoArtifactSalvage',
          label: '分解圣遗物',
          type: 'bool',
          source: 'globalDomain',
          help: '领取奖励后自动分解圣遗物。',
        },
        {
          key: 'maxArtifactStar',
          label: '分解圣遗物星级',
          type: 'select',
          source: 'globalDomain',
          options: ARTIFACT_STAR_OPTIONS,
          help: '分解的最高星级。',
        },
        {
          key: 'rewardRecognitionEnabled',
          label: '启用奖励识别',
          type: 'bool',
          source: 'globalDomain',
          help: '每轮领取后识别奖励名称与数量，任务结束打印汇总。',
        },
      ],
    },
    {
      // 次数与树脂：specifyResinUse=false=刷取至树脂耗尽 / true=按下方指定次数（两个互斥开关 UI）
      title: '次数与树脂',
      fields: [
        {
          id: 'domain-exhaust',
          key: 'specifyResinUse',
          label: '刷取至树脂耗尽',
          type: 'bool',
          source: 'globalDomain',
          invert: true,
          help: '开启=刷至可用树脂耗尽后停止（与「指定树脂刷取次数」互斥）。',
        },
        {
          id: 'domain-specify',
          key: 'specifyResinUse',
          label: '指定树脂刷取次数',
          type: 'bool',
          source: 'globalDomain',
          help: '开启=按下方指定次数刷取（与「刷取至树脂耗尽」互斥）。',
        },
        {
          key: 'originalResinUseCount',
          label: '原粹树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用原粹树脂的刷取次数。',
        },
        {
          key: 'condensedResinUseCount',
          label: '浓缩树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用浓缩树脂的刷取次数。',
        },
        {
          key: 'transientResinUseCount',
          label: '须臾树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用须臾树脂的刷取次数。',
        },
        {
          key: 'fragileResinUseCount',
          label: '脆弱树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用脆弱树脂的刷取次数。',
        },
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
          strategyKey: 'StrategyName',
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
          strategyKey: 'StrategyName',
          domainKey: 'DomainName',
          rewardKey: 'SundayWeeklySelectedValue',
        },
        ...WEEKDAY_KEYS.map(({ key, label }) => ({
          uid: key,
          label,
          partyKey: `${key}PartyName`,
          strategyKey: `${key}StrategyName`,
          domainKey: `${key}DomainName`,
          rewardKey: `${key}SelectedValue`,
          runKey: `DomainRun${key}`,
        })),
      ],
    },
  ],
  自动首领讨伐: [
    {
      title: '刷取设置',
      fields: [
        {
          key: 'AutoBossName',
          label: '选择首领',
          type: 'boss',
          help: '部分首领因机制问题未添加。',
        },
        {
          key: 'AutoBossTeamName',
          label: '切换队伍',
          type: 'text',
          help: '留空则不更换队伍；例如：首领队。',
        },
        {
          key: 'AutoBossStrategyName',
          label: '选择战斗策略',
          type: 'strategy',
          help: '仅用于首领讨伐，不覆盖其他策略设置。',
        },
        {
          key: 'AutoBossReviveRetryCount',
          label: '角色死亡后重试次数',
          type: 'number',
          min: 0,
          help: '战斗中存在角色死亡时，复活后重新讨伐当前首领。',
        },
        {
          key: 'AutoBossReturnToStatueAfterEachRound',
          label: '每轮讨伐后返回七天神像',
          type: 'bool',
          help: '开启后每次领奖后先回血，再重新前往首领。',
        },
        {
          key: 'AutoBossRewardRecognitionEnabled',
          label: '启用奖励识别',
          type: 'bool',
          help: '每轮领取后识别奖励名称与数量，任务结束打印汇总。',
        },
        {
          key: 'AutoBossTimeout',
          label: '战斗超时（秒）',
          type: 'number',
          min: 1,
          help: '单轮战斗超时秒数，超时后按失败处理（默认 240）。',
        },
      ],
    },
    {
      title: '次数与树脂',
      fields: [
        // AutoBossSpecifyRunCount 同一布尔的两个互斥界面（参考幽境危战）：
        // 刷取至原粹树脂耗尽=界面勾选时存 false（invert）；指定讨伐次数=界面勾选时存 true。
        {
          id: 'boss-exhaust',
          key: 'AutoBossSpecifyRunCount',
          label: '刷取至原粹树脂耗尽',
          type: 'bool',
          invert: true,
          help: '开启=刷至原粹树脂耗尽后停止，下方次数与树脂冻结（与「指定讨伐次数」互斥）。',
        },
        {
          id: 'boss-specify',
          key: 'AutoBossSpecifyRunCount',
          label: '指定讨伐次数',
          type: 'bool',
          help: '开启=按下方「讨伐次数」执行（与「刷取至原粹树脂耗尽」互斥）。',
        },
        {
          key: 'AutoBossRunCount',
          label: '讨伐次数',
          type: 'number',
          min: 1,
          masterKey: 'AutoBossSpecifyRunCount',
          masterValue: true,
          help: '指定成功后按成功领取奖励次数停止。',
        },
        {
          key: 'AutoBossUseTransientResin',
          label: '原粹不足时使用须臾树脂',
          type: 'bool',
          masterKey: 'AutoBossSpecifyRunCount',
          masterValue: true,
          help: '原粹不足时使用须臾树脂补充。',
        },
        {
          key: 'AutoBossUseFragileResin',
          label: '原粹不足时使用脆弱树脂',
          type: 'bool',
          masterKey: 'AutoBossSpecifyRunCount',
          masterValue: true,
          help: '原粹不足时使用脆弱树脂补充。',
        },
      ],
    },
  ],
  领取每日奖励: [
    {
      title: '每日奖励',
      fields: [
        {
          key: 'AdventurersGuildCountry',
          label: '领取奖励的冒险者协会',
          type: 'select',
          options: ADVENTURERS_GUILD_REGION_OPTIONS,
          help: '前往指定地区冒险者协会领取。',
        },
        {
          key: 'DailyRewardPartyName',
          label: '领取前切换队伍（好感队）',
          type: 'text',
          help: '用于给指定队伍加好感度；填写好感队名称。',
        },
      ],
    },
  ],
  领取尘歌壶奖励: [
    {
      title: '尘歌壶',
      fields: [
        {
          key: 'SereniteaPotTpType',
          label: '进壶方式选择',
          type: 'select',
          options: SERENITEA_TP_OPTIONS,
          help: '地图传送=大地图直达；尘歌壶道具=使用壶道具进入。',
        },
        {
          key: 'SecretTreasureObjects',
          label: '尘歌壶奖励对象',
          type: 'multi',
          options: SECRET_TREASURE_OPTIONS,
          help: '购买日期与商品（日期不影响领取好感和钱币）。',
        },
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
  return (
    sel.kind === 'scriptgroup' ||
    sel.kind === 'js' ||
    sel.kind === 'pathing' ||
    sel.kind === 'keymouse'
  )
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
// 右栏设置的读写键：按「实例名」（首实例=基名，其余=基名-{uid}）定位 per-user 副本，
// 使同一配置组的多份各自保存设置、互不串台。首实例实例名即基名，兼容存量设置副本。
// 注意：读设置 UI/目录（projectEditorFolder）仍用基名——BGI 目录只认基名。
const projectEditorGroupName = computed<string>(() => {
  const sel = selectedGroupIdentity.value
  return sel ? stepNameOf(sel) : ''
})

// 每周秘境秘境候选目录（官方 tp.json 扫描；只随 scriptId，不随用户/配置组）
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
// 全局 config.json 幽境危战段设置（刷取战场/队伍/策略/次数与树脂；autoStygianOnslaughtConfig 段）
const globalStygianSettings = ref<Record<string, unknown>>({})
const globalStygianSettingsDirty = ref(false)
const hasDragonGroupSettingsDirty = computed(
  () =>
    dragonSettingsDirty.value || globalDomainSettingsDirty.value || globalStygianSettingsDirty.value
)
// 当前选中内置组是否有设置 schema（含每周秘境周表等非 fields 形态的分组）
const hasGroupSettingFields = computed<boolean>(() =>
  currentGroupSettingSections.value.some(
    s =>
      s.fields.length > 0 ||
      s.kind === 'weekly-table' ||
      s.kind === 'weekly-field-table' ||
      s.kind === 'daily-leyline'
  )
)

// BetterGI 一条龙独立模式专属配置名（MAS 槽位；开启「用户独立配置」时固定使用，
// 一条龙名称下拉冻结，不再让用户选择 BGI 实配名）。与后端 one_dragon.launch_slot_name() 一致。
const MAS_ONE_DRAGON_SLOT_NAME = 'MAS独立配置'
// 右栏任务设置读写的配置名：独立模式固定为 MAS 槽位名；否则用户所选一条龙名（默认配置兜底）
const dragonConfigName = computed<string>(() =>
  masConfigEnabled.value
    ? MAS_ONE_DRAGON_SLOT_NAME
    : formData.Task.OneDragonConfigName || '默认配置'
)

// 当前组的字段是否需要全局秘境段（触发 globalDomain 加载/保存）
const needGlobalDomainSettings = computed<boolean>(() =>
  currentGroupSettingSections.value.some(s => s.fields.some(f => f.source === 'globalDomain'))
)
// 当前组的字段是否需要全局幽境段（触发 globalStygian 加载/保存）
const needGlobalStygianSettings = computed<boolean>(() =>
  currentGroupSettingSections.value.some(s => s.fields.some(f => f.source === 'globalStygian'))
)

// 右栏设置自动保存：debounce 合并连击（如文本逐字输入），串行队列避免并发丢保存。
// dragonGroupSaveSel 锁定「正在编辑的配置组」：自动保存 / 切换前冲刷都在该组落库，
// 避免切换组后定时器才触发、把旧组数据误写进新组的配置。
let dragonGroupAutoSaveTimer: ReturnType<typeof setTimeout> | null = null
let dragonGroupSaveChain: Promise<boolean> = Promise.resolve(true)
let dragonGroupSaveSel: ConfigGroupIdentity | null = null

const scheduleDragonGroupAutoSave = (silent = true) => {
  dragonGroupSaveSel = selectedGroupIdentity.value ?? null
  if (dragonGroupAutoSaveTimer) clearTimeout(dragonGroupAutoSaveTimer)
  dragonGroupAutoSaveTimer = setTimeout(() => {
    dragonGroupAutoSaveTimer = null
    void saveDragonGroupSettings(silent, dragonGroupSaveSel)
  }, 400)
}

// 编辑字段：本地即时更新并自动落库（无需点「保存设置」）；按数据来源分流到对应 store，
// 再经 debounce 写回。字段来源必须与 DragonSettingField.source 对齐。
const updateSettingField = (field: DragonSettingField, value: unknown) => {
  if (field.source === 'globalDomain') {
    globalDomainSettings.value = { ...globalDomainSettings.value, [field.key]: value }
    globalDomainSettingsDirty.value = true
  } else if (field.source === 'globalStygian') {
    globalStygianSettings.value = { ...globalStygianSettings.value, [field.key]: value }
    globalStygianSettingsDirty.value = true
  } else {
    dragonSettings.value = { ...dragonSettings.value, [field.key]: value }
    dragonSettingsDirty.value = true
  }
  void scheduleDragonGroupAutoSave(true)
}

// 读取该用户一条龙配置设置项 + （如需要）全局秘境/幽境段（切换选中行时刷新）
const loadDragonGroupSettings = async () => {
  const sel = selectedGroupIdentity.value
  dragonGroupSaveSel = sel ?? null
  if (!sel || sel.kind !== 'builtin' || !userId.value) {
    dragonSettings.value = {}
    dragonSettingsDirty.value = false
    globalDomainSettings.value = {}
    globalDomainSettingsDirty.value = false
    globalStygianSettings.value = {}
    globalStygianSettingsDirty.value = false
    return
  }
  if (!hasGroupSettingFields.value) return
  dragonSettingsLoading.value = true
  try {
    // 四份数据互不依赖，并行拉取
    const globalUserId = masConfigEnabled.value ? userId.value : undefined
    const [dragon, globalDomain, globalStygian, catalog] = await Promise.all([
      fetchOneDragonSettings(scriptId, userId.value, dragonConfigName.value, stepNameOf(sel)),
      needGlobalDomainSettings.value
        ? fetchGlobalDomainSettings(scriptId, globalUserId, stepNameOf(sel))
        : Promise.resolve<Record<string, unknown>>({}),
      needGlobalStygianSettings.value
        ? fetchGlobalStygianSettings(scriptId, globalUserId, stepNameOf(sel))
        : Promise.resolve<Record<string, unknown>>({}),
      needDomainCatalog.value
        ? fetchDomainCatalog(scriptId)
        : Promise.resolve<BetterGIDomainCatalogItem[]>([]),
    ])
    dragonSettings.value = dragon
    dragonSettingsDirty.value = false
    globalDomainSettings.value = globalDomain
    globalDomainSettingsDirty.value = false
    globalStygianSettings.value = globalStygian
    globalStygianSettingsDirty.value = false
    domainCatalog.value = catalog
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : t('edit.bettergiGroupSettingsLoadFailed'))
  } finally {
    dragonSettingsLoading.value = false
  }
}

// 保存：一条龙字段写回 per-user 副本；globalDomain/globalStygian 字段写回 BetterGI 全局 config.json 段。
// 经串行队列执行（避免并发丢保存，优于原 `if (saving) return` 直接丢弃）；silent=true 时不弹成功提示
// （自动保存场景）。返回 Promise<boolean> 便于调用方（切换组 / 整体保存前）await 冲刷未决编辑。
const saveDragonGroupSettings = (
  silent = false,
  selOverride?: ConfigGroupIdentity | null
): Promise<boolean> => {
  const sel = selOverride ?? selectedGroupIdentity.value
  const run = dragonGroupSaveChain.then(async () => {
    if (configLocked.value) {
      if (hasDragonGroupSettingsDirty.value) {
        message.error(t('edit.configLocked'))
        return false
      }
      return true
    }
    if (!sel || sel.kind !== 'builtin' || !userId.value) return false
    const tasks: Promise<unknown>[] = []
    if (dragonSettingsDirty.value) {
      const settings = dragonSettings.value
      tasks.push(
        saveOneDragonSettings(
          scriptId,
          userId.value,
          dragonConfigName.value,
          settings,
          stepNameOf(sel)
        ).then(() => {
          if (dragonSettings.value === settings) dragonSettingsDirty.value = false
        })
      )
    }
    if (globalDomainSettingsDirty.value) {
      const settings = globalDomainSettings.value
      tasks.push(
        saveGlobalDomainSettings(
          scriptId,
          masConfigEnabled.value ? userId.value : undefined,
          settings,
          stepNameOf(sel)
        ).then(() => {
          if (globalDomainSettings.value === settings) globalDomainSettingsDirty.value = false
        })
      )
    }
    if (globalStygianSettingsDirty.value) {
      const settings = globalStygianSettings.value
      tasks.push(
        saveGlobalStygianSettings(
          scriptId,
          masConfigEnabled.value ? userId.value : undefined,
          settings,
          stepNameOf(sel)
        ).then(() => {
          if (globalStygianSettings.value === settings) globalStygianSettingsDirty.value = false
        })
      )
    }
    if (tasks.length === 0) return true
    try {
      await Promise.all(tasks)
      if (!silent) message.success(t('edit.bettergiGroupSettingsSaved'))
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.bettergiGroupSettingsSaveFailed'))
      return false
    }
  })
  dragonGroupSaveChain = run.catch(() => false)
  return run
}

// 切换选中内置组时加载该组的设置项（分组标签页状态由子组件按 sections 变化自动重置）
watch(
  () => selectedGroupIdentity.value?.uid,
  async () => {
    // 切换组前先冲刷未决的自动保存，避免 debounce 未触发时编辑被跳过而丢失
    if (dragonGroupAutoSaveTimer) {
      clearTimeout(dragonGroupAutoSaveTimer)
      dragonGroupAutoSaveTimer = null
      if (!(await saveDragonGroupSettings(true, dragonGroupSaveSel))) return
    }
    await loadDragonGroupSettings()
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
  // 拖拽结果按行实例顺序持久化到 OneDragon.Queue，运行时后端据此重建 TaskOrder
  persistDragonQueue()
  logger.debug(`一条龙队列顺序已调整: ${dragonList.value.map(i => i.key).join(',')}`)
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
const handleCandidateClick = (candidate: ConfigGroupIdentity, index: number, event: MouseEvent) =>
  handleListCandidateClick(addModal.candidates, jsCandidateAnchor, candidate, index, event)

// 配置组 标签页：默认/专项/ScriptGroup 候选点击
const handleGroupCandidateClick = (
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) =>
  handleListCandidateClick(addModal.groupCandidates, groupCandidateAnchor, candidate, index, event)

// 录制 标签页：KeyMouseScript 候选点击
const handleKeyMouseCandidateClick = (
  candidate: ConfigGroupIdentity,
  index: number,
  event: MouseEvent
) =>
  handleListCandidateClick(
    addModal.keyMouseCandidates,
    keyMouseCandidateAnchor,
    candidate,
    index,
    event
  )

// ---- 添加弹窗（标签页：配置组/JS脚本/地图追踪）----
// 气泡列表元素：一条龙实例身份 + 弹窗内自增 uid（用于去重展示/删除，与队列行 uid 无关）
type AddChipItem = ConfigGroupIdentity & { chipUid: number }

const addModal = reactive({
  open: false,
  items: [] as AddChipItem[],
  draft: '',
  activeTab: 'scriptgroup' as 'scriptgroup' | 'js' | 'pathing' | 'keymouse',
  /** true=配置组编辑器内「添加脚本」：冻结「配置组」标签页，仅可从 JS脚本/地图追踪选择加入配置组 */
  addToGroupMode: false,
  /** JS脚本 标签页候选：自定义组 + JS 脚本（不含默认/专项/配置组，那些归「配置组」标签页） */
  candidates: [] as ConfigGroupIdentity[],
  /** 配置组 标签页候选：8 内置（默认）+ 体力作战（专项）+ ScriptGroup 目录内容 */
  groupCandidates: [] as ConfigGroupIdentity[],
  /** 录制 标签页候选：KeyMouseScript 目录下的键鼠脚本 */
  keyMouseCandidates: [] as ConfigGroupIdentity[],
})

// 添加弹窗标题/确定按钮文案（按模式分流）
const addModalTitle = computed<string>(() =>
  addModal.addToGroupMode ? t('edit.bettergiAddScriptToGroup') : t('edit.bettergiAddToDragon')
)
const addModalOkText = computed<string>(() =>
  addModal.addToGroupMode ? t('edit.bettergiAddScriptToGroupOk') : t('edit.bettergiAddToDragonOk')
)
const addModalOkButtonProps = computed(() => ({
  disabled: configLocked.value || (!addModal.items.length && !addModal.draft.trim()),
}))

// 配置组编辑器 ref：确认「添加脚本」后把选中的 JS/路径追加进当前配置组 json
const groupProjectEditorRef = ref<{
  addProjects: (rows: unknown[]) => Promise<boolean>
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
// 录制 候选项 Shift 区间锚点（index in addModal.keyMouseCandidates）
const keyMouseCandidateAnchor = ref(-1)
// 地图追踪文件行 Shift 区间锚点（index in selectedPathingFiles）
const pathingFileAnchor = ref(-1)
// BetterGI 现有自定义组名（仅作弹窗候选；打开弹窗不再合并进管理表，避免自动入队）
const bgiCustomCandidates = ref<string[]>([])

// 加载可加入一条龙的 BetterGI 自定义 JS 脚本（实时扫描，反映玩家手工放置/订阅的脚本）
const loadJsScripts = async () => {
  try {
    const resp =
      await BetterGiService.getBettergiJsScriptsApiApiScriptsBettergiJsScriptsGet(scriptId)
    jsScriptOptions.value = (resp.data || [])
      .filter(
        (item): item is ComboBoxItem & { label: string; value: string } =>
          item.label != null && item.value != null
      )
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 加载 BetterGI「配置组」候选（BGI User/ScriptGroup + 该用户 per-user 副本的文件名并集）。
// userId 非空时后端把 MAS 独立配置下用户自建的副本名一并返回，复制出的新组才能被识别为可编辑 scriptgroup。
const loadScriptGroups = async () => {
  try {
    const resp = await BetterGiService.getBettergiScriptGroupsApiApiScriptsBettergiScriptGroupsGet(
      scriptId,
      userId.value || undefined
    )
    scriptGroupOptions.value = (resp.data || [])
      .filter(
        (item): item is ComboBoxItem & { label: string; value: string } =>
          item.label != null && item.value != null
      )
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 加载 BetterGI「录制」候选（BGI User/KeyMouseScript 下的键鼠脚本文件名）。
const loadKeyMouseScripts = async () => {
  try {
    const resp =
      await BetterGiService.getBettergiKeyMouseScriptsApiApiScriptsBettergiKeyMouseScriptsGet(
        scriptId
      )
    keyMouseOptions.value = (resp.data || [])
      .filter(
        (item): item is ComboBoxItem & { label: string; value: string } =>
          item.label != null && item.value != null
      )
      .map(item => ({ label: item.label, value: item.value }))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// 组装候选项，按标签页拆分：
//  - addModal.candidates（JS脚本 标签页）：JS 脚本 + 仅 custom 来源的现有自定义组
//  - addModal.groupCandidates（配置组 标签页）：8 内置（默认）+ 体力作战（专项）+ ScriptGroup 目录内容
// 现有自定义组若命中 ScriptGroup 目录（如「锄地一条龙」），在配置组标签页以 ScriptGroup 形式出现，
// 故 JS脚本 标签页剔除，避免同一配置两个入口。
const buildCandidates = () => {
  // 录制 标签页候选：KeyMouseScript 目录下的键鼠脚本（与其他标签页一样可加入队列）
  addModal.keyMouseCandidates = keyMouseOptions.value.map(opt => ({
    kind: 'keymouse' as const,
    key: opt.value,
  }))
  // addToGroupMode（配置组内添加脚本）只允许可执行的 JS 脚本目录与地图追踪路径；
  // 原有自定义组（custom）不写入配置组 projects，故 JS脚本 标签仅列 js 候选。
  if (addModal.addToGroupMode) {
    addModal.candidates = jsScriptOptions.value.map(opt => ({
      kind: 'js' as const,
      key: opt.value,
    }))
    addModal.groupCandidates = []
    return
  }
  const jsItems: ConfigGroupIdentity[] = []
  const jsTaken = new Set<string>()
  for (const row of customGroupsTable.value) {
    const name = row.name
    // 现有自定义组按真实来源归类：仅「自定义组(custom)」入列 JS脚本 标签页；
    // 命中 JS脚本/路径/录制/ScriptGroup 目录的名字各有专属标签页，避免同一配置多处出现。
    const kind = resolveStoredRowKind(name)
    if (kind === 'custom' && !jsTaken.has(name)) {
      jsItems.push({ kind: 'custom', key: name })
      jsTaken.add(name)
    }
  }
  // BetterGI 现有、但尚未入管理表的自定义组仅作候选：用户显式确认才入队（不再打开即自动入队）
  for (const name of bgiCustomCandidates.value) {
    if (!jsTaken.has(name) && !customGroupsTable.value.some(r => r.name === name)) {
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
  // 「体力作战」未开展制作时不出现在添加候选
  if (STAMINA_COMBAT_VISIBLE) {
    groupItems.push({ kind: 'stamina', key: STAMINA_COMBAT_KEY })
    groupTaken.add(STAMINA_COMBAT_KEY)
  }
  for (const opt of scriptGroupOptions.value) {
    if (groupTaken.has(opt.value)) continue
    // 「配置组」候选只应有三类：默认组、专项组、BGI User/ScriptGroup 里真实存在的配置组。
    // 后端为识别队列行会把该用户的 per-user 副本名一并返回，其中：
    //   1) 「脚本/录制」类自定义项的副本名与脚本目录名/录制名同名（OCRCountResin、
    //      提瓦特记事本DHXYHO…）——它们归属「脚本」「录制」标签页，不是配置组；
    //   2) MAS 自建组（MAS-{短id}-自定义配置组N / MAS-{短id}-执行层段N / MAS切换账号 /
    //      MAS一条龙）——运行期物化产物，用户不该在这里看到。
    // 二者在此剔除（2026-09-16 实机：添加自定义配置组后它们会冒进候选列表）。
    if (isMasOwnGroup(opt.value)) continue
    if (isJsScriptName(opt.value) || isKeyMouseName(opt.value)) continue
    groupItems.push({ kind: 'scriptgroup', key: opt.value })
    groupTaken.add(opt.value)
  }
  addModal.groupCandidates = groupItems
}

// 普通「添加配置组到一条龙」弹窗
const openAddToDragonModal = async () => {
  addModal.addToGroupMode = false
  await openAddModalCommon('scriptgroup')
}

// 配置组编辑器「添加脚本」：复用同一弹窗但冻结「配置组」标签，只可加 JS 脚本/地图追踪/录制到配置组。
// 适用 scriptgroup / 录制(keymouse) / 脚本(js) / 路径(pathing) 四类：后两者以 per-user ScriptGroup 副本充当配置组。
const openAddScriptToGroup = async () => {
  const sel = selectedGroupIdentity.value
  if (
    !sel ||
    (sel.kind !== 'scriptgroup' &&
      sel.kind !== 'keymouse' &&
      sel.kind !== 'js' &&
      sel.kind !== 'pathing') ||
    !groupsEditable.value
  )
    return
  addModal.addToGroupMode = true
  await openAddModalCommon('js')
}

const openAddModalCommon = async (defaultTab: 'scriptgroup' | 'js' | 'pathing' | 'keymouse') => {
  addModal.items = []
  addModal.draft = ''
  addModal.activeTab = defaultTab
  jsCandidateAnchor.value = -1
  groupCandidateAnchor.value = -1
  keyMouseCandidateAnchor.value = -1
  pathingFileAnchor.value = -1
  clearChipSelection()
  addModal.open = true
  // 仅读取 BetterGI 现有自定义组作为弹窗候选；不再合并进管理表，避免打开弹窗即自动入队
  const bgiGroups = await listBgiCustomGroups()
  bgiCustomCandidates.value = bgiGroups
    .map(r => r.name)
    .filter(n => resolveStoredRowKind(n) === 'custom')
  await Promise.all([
    loadJsScripts(),
    loadScriptGroups(),
    loadKeyMouseScripts(),
    loadBettergiDirs(),
    loadPathingTree(),
  ])
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
  if (item.kind === 'keymouse') {
    const rec = String(item.key || '').trim()
    if (!rec) return null
    return {
      name: rec,
      folderName: rec,
      index: 0,
      type: 'KeyMouse',
      status: 'Enabled',
      schedule: 'Daily',
      runNum: 1,
      allowJsNotification: true,
      allowJsHTTPHash: '',
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
        keyMouseScriptDir: resp.keyMouseScriptDir ?? undefined,
        autoFightDir: resp.autoFightDir ?? undefined,
        exePath: resp.exePath ?? undefined,
      }
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// BetterGI 官方在线脚本站（本地检出目录无法跳转其内部页面，改用网页版脚本仓库）
const BGI_SCRIPT_SITE = 'https://s.bettergi.com/'

// 打开某目录（脚本目录 / 路径目录 / 录制 / 配置组）；脚本仓库走在线网页
const openBettergiDir = async (
  kind: 'jsScript' | 'autoPathing' | 'keyMouse' | 'scriptGroup' | 'autoFight'
) => {
  if (!bettergiDirs.value.jsScriptDir) await loadBettergiDirs()
  const target =
    kind === 'jsScript'
      ? bettergiDirs.value.jsScriptDir
      : kind === 'autoPathing'
        ? bettergiDirs.value.autoPathingDir
        : kind === 'keyMouse'
          ? bettergiDirs.value.keyMouseScriptDir
          : kind === 'autoFight'
            ? bettergiDirs.value.autoFightDir
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
const buildPathingTreeData = (nodes: BetterGIPathingNode[], parentKey = ''): PathingTreeNode[] =>
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
  if (configLocked.value) {
    message.error(t('edit.configLocked'))
    return
  }
  if (addModal.draft.trim() && !commitAddDraft()) return
  if (!addModal.items.length) {
    message.warning(t('edit.bettergiPickCandidateFirst'))
    return
  }
  const items = [...addModal.items]
  // 配置组模式：把 JS/路径转成 project 行，交给右栏编辑器追加并保存
  if (addModal.addToGroupMode) {
    const editor = groupProjectEditorRef.value
    const rows = items
      .map(toScriptGroupProjectRow)
      .filter((r): r is Record<string, unknown> => r !== null)
    if (!rows.length) {
      addModal.items = []
      addModal.draft = ''
      clearChipSelection()
      addModal.addToGroupMode = false
      addModal.open = false
      message.warning(t('edit.bettergiAddScriptUnsupported'))
      return
    }
    try {
      const added = (await editor?.addProjects(rows)) ?? false
      if (!added) return
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.bettergiProjectSaveFailed'))
      return
    }
    addModal.items = []
    addModal.draft = ''
    clearChipSelection()
    addModal.addToGroupMode = false
    addModal.open = false
    return
  }
  for (const item of items) {
    if (!addToDragon({ kind: item.kind, key: item.key })) return
  }
  addModal.items = []
  addModal.draft = ''
  clearChipSelection()
  addModal.open = false
}

// ---- 行尾双操作 ----
// 左图标=另存为新配置组（仅 scriptgroup/js/pathing 有独立内容可另存，走弹窗）；
// 右图标=复制相同（所有可编辑行直接复制一份相同配置组入队，无弹窗；内置 8 组与体力作战同此）。
const canDuplicateGroup = (item: ConfigGroupIdentity): boolean => {
  if (!item) return false
  // 所有可编辑配置组均可「另存为（前名-后名）」：不复制真实 JSON，仅以当前行为前名生成带后名的新引用
  return item.kind !== 'stamina'
}

// 是否可重命名：专项（体力作战）是本地虚拟项、不落库，改名无法保存故不提供入口；
// 默认（内置）与其余来源都可打开弹窗，其中「配置组名称」是否可改由 isNameLocked 决定。
const canRenameGroup = (item: ConfigGroupIdentity): boolean => {
  if (!item) return false
  return item.kind !== 'stamina'
}

// 直接复制相同：把当前行作为新实例追加到队列末尾（不改名、不写新副本，等同再添加一次该组）
const duplicateSameGroup = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value || isGroupFrozen(item)) return
  addToDragon({ kind: item.kind, key: item.key })
  message.success(t('edit.bettergiDuplicateSameDone', { name: groupLabel(item) }))
}

const duplicateModal = reactive<{
  open: boolean
  saving: boolean
  suffix: string
  error: string
  source: ConfigGroupIdentity | null
}>({
  open: false,
  saving: false,
  suffix: '',
  error: '',
  source: null,
})

const duplicateSourceLabel = computed<string>(() =>
  duplicateModal.source ? duplicateModal.source.key : ''
)

const openDuplicateModal = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value || !canDuplicateGroup(item)) return
  duplicateModal.source = { ...item }
  duplicateModal.suffix = ''
  duplicateModal.error = ''
  duplicateModal.open = true
}

const confirmDuplicateGroup = () => {
  if (duplicateModal.saving) return
  const source = duplicateModal.source
  if (!source) return
  duplicateModal.error = ''
  // 后名（后缀）仅作显示别名，不复制真实配置组 JSON；执行仍按前名（基名）归一。
  // 与「复制相同」不同，另存为会生成一条带新后名、指向同一前名的新引用行。
  const clean = (duplicateModal.suffix || '').trim().replace(/^-+|-+$/g, '')
  duplicateModal.saving = true
  try {
    const newItem: ConfigGroupIdentity = {
      kind: source.kind,
      key: source.key,
      suffix: clean || undefined,
    }
    addToDragon(newItem)
    duplicateModal.open = false
    message.success(t('edit.bettergiDuplicateDone', { name: groupLabel(newItem) }))
  } finally {
    duplicateModal.saving = false
  }
}

// ---- 修改名称：前名（配置组名称，仅前端展示）与后名（名称备注）分栏编辑 ----
const renameModal = reactive<{
  open: boolean
  saving: boolean
  name: string
  suffix: string
  error: string
  source: ConfigGroupIdentity | null
}>({
  open: false,
  saving: false,
  name: '',
  suffix: '',
  error: '',
  source: null,
})

// 弹窗内「配置组名称」是否锁定：默认/专项两类沿用系统固定名，只开放「名称备注」
const renameNameLocked = computed<boolean>(
  () => !!renameModal.source && isNameLocked(renameModal.source)
)

const openRenameModal = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value || !canRenameGroup(item)) return
  renameModal.source = item
  // 预填当前生效名（自定义别名优先，否则来源默认名），便于在现名基础上修改
  renameModal.name = groupBaseLabel(item)
  renameModal.suffix = item.suffix ?? ''
  renameModal.error = ''
  renameModal.open = true
}

const confirmRename = () => {
  if (renameModal.saving) return
  const source = renameModal.source
  if (!source) return
  renameModal.error = ''
  const name = (renameModal.name || '').trim().replace(/-+$/, '')
  const suffix = (renameModal.suffix || '').trim().replace(/^-+|-+$/g, '')
  // 前名填回来源默认名时视为未自定义（清空别名），默认名日后变化仍可跟随
  const nextDisplay = name && name !== defaultGroupBaseLabel(source) ? name : undefined
  renameModal.saving = true
  try {
    // 前名是组级别名：同 kind+key 的所有队列行统一显示；后名（名称备注）仅当前行实例。
    // 两者都不进入 key，实际运行仍按原配置组执行。
    if (!isNameLocked(source)) {
      for (const row of dragonList.value) {
        if (row.kind === source.kind && row.key === source.key) row.displayName = nextDisplay
      }
    }
    source.suffix = suffix || undefined
    renameModal.open = false
    persistDragonQueue()
    message.success(t('edit.bettergiRenameDone', { name: groupLabel(source) }))
  } finally {
    renameModal.saving = false
  }
}

// ---- 监听：BetterGI 现有自定义组在总开关开启时并入队列末尾 ----
watch(
  () => customGroupsTable.value.map(r => r.name).join('\u0001'),
  () => appendCustomRows(),
  { immediate: true }
)

watch(
  () => masConfigEnabled.value,
  () => {
    if (!masConfigEnabled.value) selectedGroupIdentity.value = null
  }
)

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  if (
    isInitializing.value ||
    configModeSaving.value ||
    !userId.value ||
    formData.Info.Mode === value
  )
    return
  const previousValue = formData.Info.Mode
  const previousQuickConfig = formData.Info.IfQuickConfig
  // 快速配置按来源派生（开关已隐藏）：直控 = 关，脚本 / 用户 = 开
  const nextQuickConfig = value !== '直控'
  if (!nextQuickConfig) {
    // 切到直控后 MAS 面板会隐藏：先把未落盘的一条龙组设置刷下去，避免改动丢失
    // （原「关闭快速配置」开关的同款处理）
    if (dragonGroupAutoSaveTimer) {
      clearTimeout(dragonGroupAutoSaveTimer)
      dragonGroupAutoSaveTimer = null
    }
    while (hasDragonGroupSettingsDirty.value) {
      if (!(await saveDragonGroupSettings(true, dragonGroupSaveSel))) return
    }
  }
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  formData.Info.IfQuickConfig = nextQuickConfig
  configModeSaving.value = true
  try {
    const saved = await updateUser(scriptId, userId.value, {
      Info: { Mode: formData.Info.Mode, IfQuickConfig: nextQuickConfig },
    })
    if (!saved) {
      formData.Info.Mode = previousValue
      formData.Info.IfQuickConfig = previousQuickConfig
    }
  } finally {
    configModeSaving.value = false
  }
}

// ----- 原生 GUI 设置会话（composable）-----
const {
  bettergiConfigLoading,
  bettergiWebsocketId,
  showBettergiConfigMask,
  showBettergiViewMask,
  currentSessionViewOnly,
  stoppingBettergiConfig,
  startSession,
  saveSession,
  stopSession,
  dispose: disposeGuiSession,
} = useBettergiGuiSession()

const handleBettergiConfig = () => {
  if (configLocked.value) return
  if (!userId.value) return
  void startSession(userId.value)
}

const handleSaveBettergiConfig = async () => {
  // 查看会话：只读关闭，不冲刷右栏配置（避免写盘）
  if (currentSessionViewOnly.value) {
    await saveSession()
    return
  }
  // 整体保存前先冲刷未决的右栏自动保存，确保不丢编辑
  if (dragonGroupAutoSaveTimer) {
    clearTimeout(dragonGroupAutoSaveTimer)
    dragonGroupAutoSaveTimer = null
    if (!(await saveDragonGroupSettings(true, dragonGroupSaveSel))) return
  }
  await saveSession()
}

const handleCancel = async () => {
  await stopSession()
  await router.push('/scripts')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：BetterGI 统一叫「bettergi」
const BETTERGI_DISPLAY_NAME = 'bettergi'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、BetterGI 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId.value, target),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
      scriptId,
      userId.value,
      time,
      target
    ),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId: userId.value,
      time,
      target,
    }),
  readFile: async (target: string, time: string, path: string) =>
    Service.getConfigBackupFileApiApiScriptsBackupFileGet(
      scriptId,
      userId.value,
      time,
      target,
      path
    ),
}

interface BettergiPreviewRow {
  key: string
  value: string
}
interface BettergiPreviewSection {
  name: string
  label: string
  rows?: BettergiPreviewRow[]
}
const previewSections = (raw: unknown): BettergiPreviewSection[] =>
  (raw as { sections?: BettergiPreviewSection[] } | null)?.sections ?? []

// 一键恢复成功：mas 恢复回填页面字段（OneDragon 段等），需重拉表单；
// native 恢复写 BGI 全局 config.json，MAS 表单不受影响
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    await loadUser()
  }
}

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// mas 备份：恢复到 per-user 副本后启动用户级查看会话（BGI GUI 所见即
// 副本）；原生备份：恢复到 BGI 全局后启动脚本级查看会话（打开 BGI 看
// 原生配置）。查看会话结束不回写（BetterGI 配置会话本就无回写）。
const handleRestoreView = (target: string, item: { time: string }) => {
  if (configLocked.value) return Promise.resolve(false)

  return new Promise<boolean>(resolve => {
    Modal.confirm({
      title: t('edit.configRestoreDetailView'),
      content: h(
        'p',
        { style: { color: 'var(--ant-color-error)', margin: 0 } },
        t('edit.configRestoreDetailConfirm', { script: BETTERGI_DISPLAY_NAME })
      ),
      okText: t('edit.configRestoreConfirmOk'),
      okType: 'danger',
      cancelText: t('edit.cancel'),
      onOk: async () => {
        if (configLocked.value) {
          message.error(t('edit.configLocked'))
          resolve(false)
          return
        }

        try {
          const resp = await Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
            scriptId,
            userId: userId.value,
            time: item.time,
            target,
          })
          // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：备份不存在/
          // 路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
          if (resp.code !== 200) {
            throw new Error(resp.message || t('edit.configRestoreFailed'))
          }
          restoreOpen.value = false
          if (target === 'mas') {
            // 恢复后重拉表单：后端 UserData 已回填，不重拉会让旧表单值在
            // 下次保存时整块写回、覆盖恢复结果（对齐一键恢复 handleRestored）
            await loadUser()
            await startSession(userId.value, true)
          } else {
            await startSession(scriptId, true)
          }
          resolve(true)
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
          resolve(false)
        }
      },
      onCancel: () => resolve(false),
    })
  })
}

// 编辑会话归档（进入/退出时机，指纹去重）：与运行物化前的双池归档
// （AutoProxy）配合——进入归档 BGI 全局配置当前状态（MAS 触碰前原始态），
// 退出归档 MAS 用户配置终态（per-user 副本 + 页面字段，编辑会话包络）
const ensureBettergiBackup = async (target: 'mas' | 'native') => {
  if (!userId.value) return
  try {
    const resp = await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId: userId.value,
      target,
    })
    if (resp.code !== 200) throw new Error(resp.message || t('edit.configRestoreEnsureFailed'))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.warning(t('edit.configRestoreEnsureFailed'))
  }
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
    // 快速配置开关已隐藏、按来源派生：存量数据可能残留与来源相左的值（如「直控 + 开」），
    // 以 Mode 为准归一，与保存路径（handleConfigModeChange）及后端 BetterGIUserConfig.load 一致。
    formData.Info.IfQuickConfig = formData.Info.Mode !== '直控'
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
      // 刷新配置组候选（含该用户 per-user ScriptGroup 副本名），使复制出的新组
      // 在 initDragonList/右栏编辑器里能被识别为可编辑的 scriptgroup；
      // 没有复制时 onMounted 里那一次已经拉过，不重复请求
      await loadScriptGroups()
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
    // 先加载 JsScript 候选 / ScriptGroup 配置组目录 / KeyMouseScript 录制目录 / AutoPathing 树 / 常用目录，
    // initDragonList 才能把自定义组中命中脚本目录、配置组目录、录制目录或路径文件的行标为对应来源
    await Promise.all([
      loadJsScripts(),
      loadScriptGroups(),
      loadKeyMouseScripts(),
      loadBettergiDirs(),
      loadPathingTree(),
      loadStrategyOptions(),
      loadOneDragonConfigs(),
    ])
    await loadUser()
    // 游戏客户端信息（生效路径 + 渠道标注）：用户数据就绪后按用户路径识别
    await loadGameClientInfo()
    // 编辑界面进入：归档 BGI 全局配置当前状态（须在 userId 就绪后）
    void ensureBettergiBackup('native')
  }
})

onUnmounted(() => {
  // 退出编辑页：先停会话再归档 MAS 用户配置终态——并行会与 final_task 的
  // 收尾撞车、归档到半程状态；会话未开时 dispose 立即返回，不影响归档时机
  void (async () => {
    await disposeGuiSession()
    await ensureBettergiBackup('mas')
  })()
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

/* 配置恢复预览（分区行；弹窗内滚动由通用组件负责） */
.bettergi-preview-title {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--ant-color-text);
}

.bettergi-preview-box {
  margin-bottom: 8px;
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

/* 行内操作按钮组（右对齐：左=另存为新配置组，右=复制相同） */
.group-row-actions {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.group-row-action-btn {
  color: var(--ant-color-text-tertiary);
  transition: color 0.15s ease;
}
.group-row-action-btn:hover {
  color: var(--ant-color-primary);
}
.group-row-action-btn[disabled] {
  color: var(--ant-color-text-quaternary);
}
/* 复制为新配置组弹窗 */
.duplicate-group-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.duplicate-group-source {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}
.duplicate-group-tip {
  margin: 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  line-height: 1.6;
}
.duplicate-group-error {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-error);
  line-height: 1.5;
}

/* 修改配置组名称弹窗：前名（配置组名称）+ 后名（名称备注） */
.rename-group-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rename-group-form :deep(.ant-form-item) {
  margin-bottom: 0;
}
.rename-group-source {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}
.rename-group-note {
  margin: 0;
  font-size: 12px;
  color: var(--ant-color-warning);
  line-height: 1.6;
}
.rename-group-tip {
  margin: 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  line-height: 1.6;
}
.rename-group-error {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-error);
  line-height: 1.5;
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
   默认=灰、专项=紫、脚本&JS=蓝、路径=绿、配置组=橙、录制=绯红 */
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

.gi-kind-tag-keymouse {
  background: #fff1f0;
  border-color: #ffa39e;
  color: #dc143c;
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

/* 游戏客户端路径（用户级覆盖）：输入组与信息行 */
.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}
</style>
