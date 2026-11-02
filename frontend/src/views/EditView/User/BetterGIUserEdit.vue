<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">{{ t('core.edit.scripts') }}</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/bettergi`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? t('core.comp.editUser') : t('core.comp.addUser2') }}
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <a-space size="middle">
        <a-button v-if="!!userId" size="large" :loading="folderLoading" @click="handleOpenFolder">
          <template #icon>
            <FolderOpenOutlined />
          </template>
          {{ t('core.comp.openConfigFolder') }}
        </a-button>
        <a-tooltip
          v-if="!showBettergiConfigMask && !pageLoading && masConfigEnabled"
          placement="bottom"
        >
          <template #title>
            <span style="white-space: normal">
              {{ t('core.edit.bettergiMasConfigTooltip') }}
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
            {{ t('core.edit.bettergiConfigure') }}
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
          {{ t('core.edit.bettergiConfigure') }}
        </a-button>
        <a-button v-else type="default" size="large" disabled class="configuring-button">
          <template #icon>
            <SettingOutlined />
          </template>
          {{ t('core.edit.configuring') }}
        </a-button>
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          {{ t('core.edit.back') }}
        </a-button>
      </a-space>
    </div>

    <!-- ══ BetterGI 配置/查看会话遮罩（配置会话保存设置、查看会话只读）══ -->
    <GuiSessionMask
      :open="showBettergiConfigMask"
      :icon="SettingOutlined"
      :title="t('core.edit.bettergiConfiguringTitle')"
      :description="`${t('core.edit.bettergiConfiguringDesc')}\n${t('core.edit.bettergiConfiguringDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="bettergiWebsocketId"
          type="primary"
          size="large"
          :loading="stoppingBettergiConfig"
          @click="handleSaveBettergiConfig"
        >
          {{ t('core.edit.saveSettings') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showBettergiViewMask"
      :icon="EyeOutlined"
      :title="t('core.edit.bettergiViewingTitle')"
      :description="`${t('core.edit.bettergiViewingDesc')}\n${t('core.edit.bettergiViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          type="primary"
          size="large"
          :loading="stoppingBettergiConfig"
          @click="handleSaveBettergiConfig"
        >
          {{ t('core.edit.bettergiViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('core.edit.basicInfo') }}</h3>
            </div>

            <!-- 基本信息布局：用户名:启用状态:剩余天数 = 2:1:1 -->
            <a-row :gutter="24">
              <a-col :span="12">
                <UserNameField
                  v-model="formData.userName"
                  :hint="t('core.edit.bettergiUserNameHint')"
                  :placeholder="t('core.edit.enterUsername')"
                  enhanced
                  @save="saveField('Info.Name', formData.userName)"
                />
              </a-col>
              <a-col :span="6">
                <UserStatusField
                  v-model="formData.Info.Status"
                  :hint="t('core.edit.whetherThisUserEnabled')"
                  @save="saveField('Info.Status', formData.Info.Status)"
                />
              </a-col>
              <a-col :span="6">
                <UserRemainedDayField
                  v-model="formData.Info.RemainedDay"
                  :hint="t('core.edit.daysLeftAccount1')"
                  @save="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                />
              </a-col>
            </a-row>

            <!-- 账户:密码 = 1:1 -->
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.bettergiAccount')"
                      :hint="t('core.edit.bettergiAccountHint')"
                      variant="form"
                    />
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    :placeholder="t('core.edit.bettergiEnterAccount')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.password')"
                      :hint="t('core.edit.bettergiPasswordHint')"
                      variant="form"
                    />
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    :placeholder="t('core.edit.bettergiEnterPasswordPlaceholder')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Password', formData.Info.Password)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 账号 UID:游戏服务器 = 1:1 -->
            <BettergiGameClientSection
              ref="gameClientSection"
              :script-id="scriptId"
              :user-id="userId"
              :config="formData.Switch"
              :loading="pageLoading"
              :locked="configLocked"
              :save-field="saveField"
            >
              <template #uid>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <FieldLabelWithHint
                        :text="t('core.edit.bettergiAccountUid')"
                        :hint="t('core.edit.bettergiUidHint')"
                        variant="form"
                      />
                    </template>
                    <a-input
                      v-model:value="formData.Switch.Uid"
                      :placeholder="t('core.edit.bettergiEnterUid')"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Switch.Uid', formData.Switch.Uid)"
                    />
                  </a-form-item>
                </a-col>
              </template>
            </BettergiGameClientSection>

            <a-row :gutter="24">
              <a-col :span="24">
                <!-- 快速配置开关已隐藏：按配置来源派生（原生来源 = 关，共享 / 独立 = 开），
                     见 handleConfigModeChange 与后端 BetterGIUserConfig.load 的加载归一。
                     派生值仍交给选择器只读展示，让「本次任务生效的配置」与实际运行一致。 -->
                <GeneralConfigModeSelector
                  :model-value="formData.Info.Base"
                  :options="bettergiConfigModeOptions"
                  :disabled="pageLoading"
                  :saving="configModeSaving"
                  :quick-config="formData.Info.IfQuickConfig"
                  :quick-config-readonly="true"
                  @change="handleConfigModeChange"
                />
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :xs="24" :sm="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('core.edit.collectNodeDetails') }}
                      <a-tooltip
                        mouse-enter-delay="0.5"
                        :title="t('core.edit.collectsKeyMomentsFrom')"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Notify.PushLogMode"
                    :options="pushLogModeOptions"
                    size="large"
                    class="modern-select"
                    :disabled="pageLoading"
                    @change="saveField('Notify.PushLogMode', formData.Notify.PushLogMode)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <UserNotesField
              v-model="formData.Info.Notes"
              :hint="t('core.edit.addNoteAboutThis')"
              :placeholder="t('core.edit.enterNote')"
              :rows="4"
              enhanced
              @save="saveField('Info.Notes', formData.Info.Notes)"
            />
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
                {{ t('core.edit.taskConfiguration') }}
                <a-tooltip :title="t('core.edit.bettergiTaskConfigHint')">
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </h3>
              <a-button size="small" @click="openRestore">
                <template #icon>
                  <HistoryOutlined />
                </template>
                {{ t('core.edit.configRestoreTitle') }}
              </a-button>
            </a-flex>

            <a-alert
              v-if="formData.Info.Base === 'native'"
              type="info"
              show-icon
              class="mode-guide-alert"
            >
              <template #message>
                <span class="mode-guide-message">
                  {{ t('core.edit.bettergiDirectModeAlert') }}
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
                <span class="config-flow-title">{{ t('core.edit.bettergiMasConfigHowTo') }}</span>
              </template>
              <template #description>
                <p class="config-flow-desc config-flow-p">
                  {{ t('core.edit.bettergiMasConfigHowTo2') }}
                </p>
              </template>
            </a-alert>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      <span class="required-mark">*</span>
                      {{ t('core.edit.bettergiOneDragonName') }}
                      <a-tooltip :title="t('core.edit.bettergiOneDragonNameHint')">
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
                    :placeholder="t('core.edit.bettergiPickOneDragonName')"
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
              <!-- 独立配置模式：领取奖励队伍；原生来源模式：配置 BetterGI（打开 BGI 原生界面） -->
              <a-col :span="12">
                <a-form-item v-if="masConfigEnabled">
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.bettergiDailyRewardParty')"
                      :hint="t('core.edit.bettergiKeepExistingHint')"
                      variant="form"
                    />
                  </template>
                  <a-input
                    v-model:value="formData.OneDragon.DailyRewardPartyName"
                    :disabled="!masConfigEnabled"
                    :placeholder="t('core.edit.bettergiEnterDailyRewardParty')"
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
                    {{ t('core.edit.bettergiConfigure') }}
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
                      <FieldLabelWithHint
                        :text="t('core.edit.bettergiBattleParty')"
                        :hint="t('core.edit.bettergiKeepExistingHint')"
                        variant="form"
                      />
                    </template>
                    <a-input
                      v-model:value="formData.OneDragon.PartyName"
                      :placeholder="t('core.edit.bettergiEnterBattleParty')"
                      size="large"
                      class="modern-input"
                      @blur="saveField('OneDragon.PartyName', formData.OneDragon.PartyName)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <FieldLabelWithHint
                        :text="t('core.edit.bettergiBattleStrategy')"
                        :hint="t('core.edit.bettergiBattleStrategyHint')"
                        variant="form"
                      />
                    </template>
                    <!-- 通用战斗策略：点击输入框弹出备选弹窗，单选纯文本 -->
                    <a-input
                      :value="formData.OneDragon.AutoBossStrategyName"
                      readonly
                      :placeholder="t('core.edit.bettergiEnterBattleStrategy')"
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
                <BettergiDragonQueueList
                  v-model:rows="dragonListModel"
                  :selected="selectedGroupIdentity"
                  :editable="groupsEditable"
                  :group-label="groupLabel"
                  :group-prefix="groupPrefix"
                  :is-group-frozen="isGroupFrozen"
                  :group-enabled="groupEnabled"
                  :toggle-config-group="toggleConfigGroup"
                  :remove-from-dragon="removeFromDragon"
                  :clear="clearDragon"
                  :persist="persistDragonQueue"
                  @select="selectConfigGroup"
                  @add="openAddToDragonModal"
                  @duplicate="openDuplicateModal"
                  @rename="openRenameModal"
                  @copy="duplicateSameGroup"
                />

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
                        :title="t('core.edit.bettergiGroupFrozenTip')"
                      >
                        <a-tag color="orange">{{ t('core.edit.bettergiGroupFrozen') }}</a-tag>
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
                      {{ t('core.edit.bettergiGroupSettingsNone') }}
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
            :title="t('core.edit.bettergiBattleStrategy')"
            :footer="null"
            :cancel-text="t('core.edit.cancel')"
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
            <p class="strategy-picker-tip">{{ t('core.edit.bettergiStrategyPickerTip') }}</p>
          </a-modal>

          <!-- 另存为弹窗：以当前行为前名（基名），用户输入后名，生成「前名-后名」的新引用行（不复制真实配置组 JSON） -->
          <a-modal
            v-model:open="duplicateModal.open"
            :title="t('core.edit.bettergiDuplicateAsNew')"
            :ok-text="t('core.edit.bettergiDuplicateOk')"
            :cancel-text="t('core.edit.cancel')"
            :confirm-loading="duplicateModal.saving"
            :z-index="1500"
            width="480px"
            class="duplicate-group-modal"
            @ok="confirmDuplicateGroup"
            @cancel="duplicateModal.open = false"
          >
            <div class="duplicate-group-form">
              <p v-if="duplicateModal.source" class="duplicate-group-source">
                {{ t('core.edit.bettergiDuplicateSource', { name: duplicateSourceLabel }) }}
              </p>
              <a-input
                v-model:value="duplicateModal.suffix"
                :placeholder="t('core.edit.bettergiDuplicateNamePlaceholder')"
                :status="duplicateModal.error ? 'error' : ''"
                size="large"
                :maxlength="40"
                @input="duplicateModal.error = ''"
                @press-enter="confirmDuplicateGroup"
              />
              <p v-if="duplicateModal.error" class="duplicate-group-error">
                {{ duplicateModal.error }}
              </p>
              <p class="duplicate-group-tip">{{ t('core.edit.bettergiDuplicateTip') }}</p>
            </div>
          </a-modal>

          <!-- 修改名称弹窗：前名（配置组名称，仅前端展示的组级别名）与后名（名称备注，区分同名实例）分栏编辑。
               默认/专项两类的前名沿用系统固定名，窗口内锁定只读；两者都不进入 key，运行仍按原配置组执行。 -->
          <a-modal
            v-model:open="renameModal.open"
            :title="t('core.edit.bettergiRenameTitle')"
            :ok-text="t('core.edit.bettergiRenameOk')"
            :cancel-text="t('core.edit.cancel')"
            :confirm-loading="renameModal.saving"
            :z-index="1500"
            width="480px"
            class="rename-group-modal"
            @ok="confirmRename"
            @cancel="renameModal.open = false"
          >
            <div class="rename-group-form">
              <p v-if="renameModal.source" class="rename-group-source">
                {{ t('core.edit.bettergiRenameSource', { name: renameModal.source.key }) }}
              </p>
              <a-form layout="horizontal" :label-col="{ span: 6 }" :wrapper-col="{ span: 18 }">
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('core.edit.bettergiRenameNameLabel') }}</span>
                  </template>
                  <a-input
                    v-model:value="renameModal.name"
                    :placeholder="t('core.edit.bettergiRenameNamePlaceholder')"
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
                    <span class="form-label">{{ t('core.edit.bettergiRenameSuffixLabel') }}</span>
                  </template>
                  <a-input
                    v-model:value="renameModal.suffix"
                    :placeholder="t('core.edit.bettergiRenamePlaceholder')"
                    size="large"
                    :maxlength="40"
                    @input="renameModal.error = ''"
                    @press-enter="confirmRename"
                  />
                </a-form-item>
              </a-form>
              <p v-if="renameNameLocked" class="rename-group-note">
                {{ t('core.edit.bettergiRenameLockedTip') }}
              </p>
              <p v-if="renameModal.error" class="rename-group-error">
                {{ renameModal.error }}
              </p>
              <p class="rename-group-tip">{{ t('core.edit.bettergiRenameTip') }}</p>
            </div>
          </a-modal>

          <!-- 添加配置组弹窗：加入一条龙 或（配置组编辑器内）添加脚本到当前配置组
               后开的弹窗显示在之前弹窗之上：z-index 高于编辑器放大弹窗(1000)/设置弹窗(1100) -->
          <BettergiAddGroupModal
            ref="addGroupModal"
            :catalogs="catalogs"
            :locked="configLocked"
            :editable="groupsEditable"
            :custom-groups="customGroupsTable"
            :group-label="groupLabel"
            :group-prefix="groupPrefix"
            :is-group-frozen="isGroupFrozen"
            :in-dragon="inDragon"
            :resolve-stored-row-kind="resolveStoredRowKind"
            :list-custom-groups="listBgiCustomGroups"
            :add-to-queue="addToDragon"
            :add-projects="addProjects"
          />
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
            :domain-catalog-error="domainCatalogError"
            :boss-catalog="AUTO_BOSS_CATALOG"
            :leyline-country-options="LEY_LINE_COUNTRY_OPTIONS"
            :leyline-type-options="LEY_LINE_TYPE_OPTIONS"
            @save="saveField"
            @reload-domain-catalog="loadDomainCatalog"
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
      :user-desc="t('core.edit.bettergiConfigRestoreUserDesc')"
      :script-desc="t('core.edit.bettergiConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- mas 备份为字段侧车分区 + 副本文件摘要、native 备份为文件粒度 -->
      <template #preview="{ raw }">
        <NoData
          v-if="!previewSections(raw).length"
          :description="t('core.edit.configRestorePreviewEmpty')"
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
import UserNameField from '@/views/EditView/User/components/UserNameField.vue'
import UserNotesField from '@/views/EditView/User/components/UserNotesField.vue'
import UserRemainedDayField from '@/views/EditView/User/components/UserRemainedDayField.vue'
import UserStatusField from '@/views/EditView/User/components/UserStatusField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useBettergiDragonQueue } from './BetterGIUserEdit/useBettergiDragonQueue'
import BettergiDragonQueueList from './BetterGIUserEdit/BettergiDragonQueueList.vue'

import {
  AUTO_BOSS_CATALOG,
  LEY_LINE_COUNTRY_OPTIONS,
  LEY_LINE_TYPE_OPTIONS,
  type DragonSettingField,
} from './BetterGIUserEdit/bettergiGroupSettingsSchema'
import { useBettergiGroupSettings } from './BetterGIUserEdit/useBettergiGroupSettings'

import BettergiAddGroupModal from './BetterGIUserEdit/BettergiAddGroupModal.vue'

import {
  ONE_DRAGON_GROUPS,
  kindTagClass,
  pathingDisplayName,
  type ConfigGroupIdentity,
} from './BetterGIUserEdit/bettergiQueueIdentity'
import { useBettergiCatalogs } from './BetterGIUserEdit/useBettergiCatalogs'

import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  CloseOutlined,
  CopyOutlined,
  EditOutlined,
  DownOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { BetterGiService, type ComboBoxItem, type BetterGIUserConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useBettergiGuiSession } from '@/composables/useBettergiGuiSession'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'
import BettergiDragonGroupSettings from './BettergiDragonGroupSettings.vue'
import BettergiGroupProjectEditor from './BettergiGroupProjectEditor.vue'
import BettergiTeamSettings from './BettergiTeamSettings.vue'
import BettergiGameClientSection from './BetterGIUserEdit/BettergiGameClientSection.vue'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'

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
const { getScript, error: scriptApiError } = useScriptApi()

const scriptId = route.params.scriptId as string

const handleOpenFolder = async () => {
  if (!userId.value) return
  await openUserConfigFolder(scriptId, userId.value)
}
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const catalogs = useBettergiCatalogs(scriptId, userId)
const {
  jsDisplayName,
  loadJsScripts,
  loadScriptGroups,
  loadKeyMouseScripts,
  loadBettergiDirs,
  openBettergiDir,
  loadPathingTree,
} = catalogs
const gameClientSection = ref<InstanceType<typeof BettergiGameClientSection> | null>(null)
const { configLocked } = useScriptConfigLock(() => scriptId)
const scriptName = ref(t('core.edit.bettergiScriptFallbackName'))

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
    title: t('core.edit.script'),
    description: t('core.edit.useSharedScriptLevel'),
    value: 'shared',
    icon: 'file',
    // 「共享」运行时与「独立」同分支（均按 per-user MAS 配置运行），选了不生效——禁用并说明
    disabled: true,
    disabledReason: t('core.edit.scriptModeDisabled'),
  },
  {
    title: t('core.edit.perUserConfiguration'),
    description: t('core.edit.perUserConfiguration'),
    value: 'independent',
    icon: 'database',
  },
  {
    title: t('core.edit.scriptDirectControl'),
    description: t('core.edit.useScriptSCurrent'),
    value: 'native',
    icon: 'setting',
  },
]
// 面板可见性由**配置来源**决定（维护者决策：放弃把快速配置当作来源开关）：原生来源 = 用 BGI
// 所选原生配置（显示原生「一条龙名称」与「配置 BetterGI」，MAS 不接管）；脚本/用户 = MAS 面板。
const masConfigEnabled = computed(() => formData.Info.Base !== 'native')

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type BetterGIUserFormData = {
  userName: string
  Info: FormSection<NonNullable<BetterGIUserConfig['Info']>>
  Task: FormSection<NonNullable<BetterGIUserConfig['Task']>>
  Switch: FormSection<NonNullable<BetterGIUserConfig['Switch']>>
  OneDragon: FormSection<NonNullable<BetterGIUserConfig['OneDragon']>>
  Notify: FormSection<NonNullable<BetterGIUserConfig['Notify']>>
}

// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('core.edit.pushLogModeOff'), value: '关闭' },
  { label: t('core.edit.pushLogModeList'), value: '逐条' },
  { label: t('core.edit.pushLogModeSummary'), value: '汇总' },
]

const getDefaultUserData = (): Omit<BetterGIUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    RemainedDay: -1,
    Base: 'independent',
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
    PushLogMode: '汇总',
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
    message.error(userApiError.value || t('core.edit.couldNotCreateUser'))
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

// 自动战斗策略选项（「根据队伍自动选择」+ {RootPath}/User/AutoFight/*.txt、*.json），由后端实时读取
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

const {
  customGroupsTable,
  syncCustomGroupsFromForm,
  loadCustomGroupsFromBettergi,
  listBgiCustomGroups,
  dragonList,
  selectedGroupIdentity,
  groupsEditable,
  stepNameOf,
  isNameLocked,
  isGroupFrozen,
  groupEnabled,
  inDragon,
  persistDragonQueue,
  initDragonList,
  resolveStoredRowKind,
  dragonListModel,
  clearDragon,
  toggleConfigGroup,
  addToDragon,
  removeFromDragon,
  selectConfigGroup,
} = useBettergiDragonQueue({
  scriptId,
  userId,
  oneDragon: () => formData.OneDragon,
  configName: () => formData.Task.OneDragonConfigName,
  masEnabled: masConfigEnabled,
  locked: configLocked,
  catalogs,
  saveField,
})

// 内置组的显示名表（key=中文组名 value）
const builtinGroupLabels = computed<Record<string, string>>(() =>
  Object.fromEntries(ONE_DRAGON_GROUPS.map(g => [g.value, t(g.labelKey)]))
)

// 前缀 tag 文案
const groupPrefix = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return t('core.edit.bettergiGroupPrefixDefault')
  if (item.kind === 'stamina') return t('core.edit.bettergiGroupKindStamina')
  if (item.kind === 'pathing') return t('core.edit.bettergiGroupKindPathing')
  if (item.kind === 'scriptgroup') return t('core.edit.bettergiGroupKindScriptGroup')
  if (item.kind === 'keymouse') return t('core.edit.bettergiGroupKindKeyMouse')
  // JS 脚本与现有自定义组同属「共享」来源（按需求：JS 的 tag 改为脚本）
  return t('core.edit.bettergiGroupKindCustom')
}

// 前名（配置组名称）按来源类型回退的默认显示名（未自定义别名时使用）
const defaultGroupBaseLabel = (item: ConfigGroupIdentity): string => {
  if (item.kind === 'builtin') return builtinGroupLabels.value[item.key] ?? item.key
  if (item.kind === 'stamina') return t('core.edit.bettergiGroupStamina')
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

const {
  currentGroupSettingSections,
  MAS_ONE_DRAGON_SLOT_NAME,
  dragonConfigName,
  domainCatalog,
  domainCatalogError,
  loadDomainCatalog,
  dragonSettings,
  dragonSettingsLoading,
  dragonSettingsSaving,
  dragonSettingsDirty,
  globalDomainSettings,
  globalDomainSettingsDirty,
  globalStygianSettings,
  globalStygianSettingsDirty,
  updateSettingField,
  saveDragonGroupSettings,
  flushPending: flushGroupSettings,
  invalidateReads: invalidateGroupReads,
} = useBettergiGroupSettings({
  scriptId,
  userId,
  selected: selectedGroupIdentity,
  masEnabled: masConfigEnabled,
  locked: configLocked,
  configName: () => formData.Task.OneDragonConfigName,
  stepName: stepNameOf,
})

const flushPending = async (allDirty = false): Promise<boolean> => {
  do {
    await gameClientSection.value?.waitForPendingSaves()
    if (!(await flushGroupSettings(allDirty))) return false
    await enqueue(() => Promise.resolve(true))
    // 等待组设置/队列期间可能又改了路径，下一轮仍需完成其渠道联动。
  } while (gameClientSection.value?.hasPendingSaves())
  return true
}

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

// 配置组编辑器 ref：确认「添加脚本」后把选中的 JS/路径追加进当前配置组 json
const groupProjectEditorRef = ref<{
  addProjects: (rows: unknown[]) => Promise<boolean>
  reload: () => Promise<void>
} | null>(null)

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
  message.success(t('core.edit.bettergiDuplicateSameDone', { name: groupLabel(item) }))
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
    message.success(t('core.edit.bettergiDuplicateDone', { name: groupLabel(newItem) }))
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
    message.success(t('core.edit.bettergiRenameDone', { name: groupLabel(source) }))
  } finally {
    renameModal.saving = false
  }
}

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['shared', 'independent', 'native'].includes(value)) return
  if (
    isInitializing.value ||
    configModeSaving.value ||
    !userId.value ||
    formData.Info.Base === value
  )
    return
  const previousValue = formData.Info.Base
  const previousQuickConfig = formData.Info.IfQuickConfig
  // 快速配置按来源派生（开关已隐藏）：原生来源 = 关，共享 / 独立 = 开
  const nextQuickConfig = value !== 'native'
  if (!nextQuickConfig) {
    // 切到原生来源后 MAS 面板会隐藏：先把未落盘的一条龙组设置刷下去，避免改动丢失
    // （原「关闭快速配置」开关的同款处理）
    if (!(await flushPending(true))) return
  }
  formData.Info.Base = value as 'shared' | 'independent' | 'native'
  formData.Info.IfQuickConfig = nextQuickConfig
  configModeSaving.value = true
  try {
    const saved = await updateUser(scriptId, userId.value, {
      Info: { Base: formData.Info.Base, IfQuickConfig: nextQuickConfig },
    })
    if (!saved) {
      formData.Info.Base = previousValue
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
  void startSession(userId.value, false, 'user')
}

const handleSaveBettergiConfig = async () => {
  // 查看会话：只读关闭，不冲刷右栏配置（避免写盘）
  if (currentSessionViewOnly.value) {
    await saveSession()
    return
  }
  // 整体保存前先冲刷未决的右栏自动保存，确保不丢编辑
  if (!(await flushPending())) return
  await saveSession()
}

const handleCancel = async () => {
  if (!(await flushPending(true))) return
  await stopSession()
  await router.push('/scripts')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：BetterGI 统一叫「bettergi」
const BETTERGI_DISPLAY_NAME = 'bettergi'
const restoreOpen = ref(false)
const openRestore = async () => {
  if (!(await flushPending(true))) return
  restoreOpen.value = true
}

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、BetterGI 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const { restoreApi, ensureBackup } = useConfigBackupApi({
  scriptId,
  userId: () => userId.value,
  logger,
})

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
      title: t('core.edit.configRestoreDetailView'),
      content: h(
        'p',
        { style: { color: 'var(--ant-color-error)', margin: 0 } },
        t('core.edit.configRestoreDetailConfirm', { script: BETTERGI_DISPLAY_NAME })
      ),
      okText: t('core.edit.configRestoreConfirmOk'),
      okType: 'danger',
      cancelText: t('core.edit.cancel'),
      onOk: async () => {
        if (configLocked.value) {
          message.error(t('core.edit.configLocked'))
          resolve(false)
          return
        }

        try {
          const resp = await restoreApi.restore(target, item.time)
          // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：备份不存在/
          // 路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
          if (resp.code !== 200) {
            throw new Error(resp.message || t('core.edit.configRestoreFailed'))
          }
          restoreOpen.value = false
          if (target === 'mas') {
            // 恢复后重拉表单：后端 UserData 已回填，不重拉会让旧表单值在
            // 下次保存时整块写回、覆盖恢复结果（对齐一键恢复 handleRestored）
            await loadUser()
            await startSession(userId.value, true, 'user')
          } else {
            await startSession(scriptId, true, 'script')
          }
          resolve(true)
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('core.edit.configRestoreFailed'))
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
const ensureBettergiBackup = ensureBackup

const loadScriptInfo = async (): Promise<boolean> => {
  const detail = await getScript(scriptId)
  if (!detail || detail.type !== 'BetterGI') {
    if (!scriptApiError.value) message.error(t('core.edit.bettergiScriptNotFound'))
    handleCancel()
    return false
  }

  scriptName.value = detail.name
  return true
}

const loadUser = async () => {
  isInitializing.value = true
  invalidateGroupReads()
  catalogs.invalidateReads()
  selectedGroupIdentity.value = null
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
    // 快速配置开关已隐藏、按来源派生：存量数据可能残留与来源相左的值（如「原生来源 + 开」），
    // 以 Mode 为准归一，与保存路径（handleConfigModeChange）及后端 BetterGIUserConfig.load 一致。
    formData.Info.IfQuickConfig = formData.Info.Base !== 'native'
    await loadScriptGroups()
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
    if (!userApiError.value) message.error(t('core.edit.couldNotLoadUser'))
    handleCancel()
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
  // Card 的加载骨架会重建客户端区块；首次加载与恢复回填均需重新识别。
  await nextTick()
  await gameClientSection.value?.reload()
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
      loadDomainCatalog(),
    ])
    await loadUser()
    // 编辑界面进入：归档 BGI 全局配置当前状态（须在 userId 就绪后）
    void ensureBettergiBackup('native')
  }
})

onUnmounted(() => {
  // 退出编辑页：先停会话再归档 MAS 用户配置终态——并行会与 final_task 的
  // 收尾撞车、归档到半程状态；会话未开时 dispose 立即返回，不影响归档时机
  void (async () => {
    await flushPending(true)
    await disposeGuiSession()
    await ensureBettergiBackup('mas')
  })()
})

onBeforeRouteLeave(() => flushPending(true))

const addGroupModal = ref<InstanceType<typeof BettergiAddGroupModal> | null>(null)
const openAddToDragonModal = () => addGroupModal.value?.open()
const openAddScriptToGroup = () => {
  const sel = selectedGroupIdentity.value
  if (
    !sel ||
    !['scriptgroup', 'keymouse', 'js', 'pathing'].includes(sel.kind) ||
    !groupsEditable.value
  )
    return
  return addGroupModal.value?.openForGroup()
}
const addProjects = (rows: unknown[]) =>
  groupProjectEditorRef.value?.addProjects(rows) ?? Promise.resolve(false)
</script>

<style scoped>
@import './BetterGIUserEdit/bettergiQueueCapsule.css';

@import './BetterGIUserEdit/bettergiGroupTags.css';

@import './BetterGIUserEdit/bettergiFormControls.css';
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

.section-header {
  border-bottom-width: 1px;
}

.section-header h3 {
  gap: 8px;
}

.required-mark {
  color: var(--ant-color-error);
  margin-right: 4px;
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

.custom-groups-master-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ant-color-text);
  min-width: 0;
}

/* 拖拽热区：占整行左 2/3（名称区），右侧胶囊保持可点击 */

/* 行内操作按钮组（右对齐：左=另存为新配置组，右=复制相同） */
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

/* 前缀 tag 统一配色（antd 预设风格：浅色底 + 同色系深色文字）：
   默认=灰、专项=紫、脚本&JS=蓝、路径=绿、配置组=橙、录制=绯红 */

/* 标签输入（气泡 + 行内草稿）：外观贴合 antd input，内部 chips 自动换行 */

/* 选中气泡：主色描边 + 浅底（供 Shift/Ctrl/拖动框选后回退删除） */

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
</style>
