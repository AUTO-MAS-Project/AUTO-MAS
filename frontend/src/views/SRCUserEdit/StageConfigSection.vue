<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.stageConfiguration') }}</h3>
    </div>

    <!-- 第一行：刷取类型 | 当前生效关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="Channel">
          <template #label>
            <a-tooltip :title="t('edit.pickStageTypeFarm')">
              <span class="form-label">
                {{ t('edit.farmType') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.Channel"
            size="large"
            :placeholder="t('edit.pickFarmType')"
            @change="emitSave('Stage.Channel', formData.Stage.Channel)"
          >
            <a-select-option value="Relic">{{ t('edit.relic') }}</a-select-option>
            <a-select-option value="Materials">{{ t('edit.material') }}</a-select-option>
            <a-select-option value="Ornament">{{ t('edit.ornament') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.activeStageTakenFrom')">
              <span class="form-label">
                {{ t('edit.activeStage') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div class="current-stage-display">
            <a-tag :color="getCurrentStageColor()" size="large" class="stage-tag">
              {{ getCurrentStage() }}
            </a-tag>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第二行：遗器关卡 | 饰品关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="Relic">
          <template #label>
            <a-tooltip :title="t('edit.pickRelicStageFarm')">
              <span class="form-label">
                {{ t('edit.relicStage') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.Relic"
            size="large"
            :placeholder="t('edit.pickRelicStage')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.Relic', formData.Stage.Relic)"
          >
            <a-select-option value="-">{{ t('edit.keepOriginalConfiguration') }}</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Insight"
              >遗器：领航员 & 名冶（观火之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Possession"
              >遗器：魔法少女 & 卜者（魔占之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Hidden_Salvation"
              >遗器：救世主 & 隐士（隐救之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Thundersurge"
              >遗器：烈阳 & 船长（雳涌之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Aria"
              >遗器：英豪 & 诗人（弦歌之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Uncertainty"
              >遗器：司铎 & 学者（迷识之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Cavalier"
              >遗器：铁骑 & 勇烈（勇骑之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Dreamdive"
              >遗器：死水 & 钟表匠（梦潜之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Darkness"
              >遗器：大公 & DoT套（幽冥之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Elixir_Seekers"
              >遗器：莳者 & 信使（药使之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Conflagration"
              >遗器：火套 & 虚数套（野焰之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Holy_Hymn"
              >遗器：防御套 & 雷套（圣颂之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Providence"
              >遗器：铁卫 & 量子套（睿治之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Drifting"
              >遗器：治疗套 & 快枪手（漂泊之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Jabbing_Punch"
              >遗器：物理套 & 怪盗（迅拳之径）</a-select-option
            >
            <a-select-option value="Cavern_of_Corrosion_Path_of_Gelid_Wind"
              >遗器：冰套 & 风套（霜风之径）</a-select-option
            >
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="Ornament">
          <template #label>
            <a-tooltip :title="t('edit.pickOrnamentStageFarm')">
              <span class="form-label">
                {{ t('edit.ornamentStage') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.Ornament"
            size="large"
            :placeholder="t('edit.pickOrnamentStage')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.Ornament', formData.Stage.Ornament)"
          >
            <a-select-option value="-">{{ t('edit.keepOriginalConfiguration') }}</a-select-option>
            <a-select-option value="Divergent_Universe_Bugs_Incoming"
              >饰品：坠星 & 寰宇（虫虫来袭）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Gilded_Recollection"
              >饰品：朋克洛德 & 千星荟萃（鎏金追忆）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Within_the_West_Wind"
              >饰品：翁法罗斯 & 天国（西风丛中）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Moonlit_Blood"
              >饰品：妖精 & 沉醉（月下朱殷）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Unceasing_Strife"
              >饰品：拾骨地 & 巨树（纷争不休）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Famished_Worker"
              >饰品：海域 & 奇想（蠹役饥肠）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Eternal_Comedy"
              >饰品：奔狼 & 火宫（永恒笑剧）</a-select-option
            >
            <a-select-option value="Divergent_Universe_To_Sweet_Dreams"
              >饰品：茨冈尼亚 & 出云（伴你入眠）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Pouring_Blades"
              >饰品：苍穹 & 匹诺康尼（天剑如雨）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Fruit_of_Evil"
              >饰品：繁星 & 龙骨（孽果盘生）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Permafrost"
              >饰品：贝洛伯格 & 萨尔索图（百年冻土）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Gentle_Words"
              >饰品：商业公司 & 差分机（温柔话语）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Smelted_Heart"
              >饰品：盗贼 & 翁瓦克（浴火钢心）</a-select-option
            >
            <a-select-option value="Divergent_Universe_Untoppled_Walls"
              >饰品：太空 & 仙舟（坚城不倒）</a-select-option
            >
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第三行：材料关类别 | 材料关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.filteredByMaterialStage')">
              <span class="form-label">
                {{ t('edit.materialCategory') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="materialCategory" size="large" :placeholder="t('edit.all')">
            <a-select-option value="">{{ t('edit.all') }}</a-select-option>
            <a-select-option value="Calyx_Golden">{{ t('edit.calyxGolden') }}</a-select-option>
            <a-select-option value="Calyx_Crimson">{{ t('edit.calyxCrimson') }}</a-select-option>
            <a-select-option value="Stagnant_Shadow">{{
              t('edit.stagnantShadow')
            }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="Materials">
          <template #label>
            <a-tooltip :title="t('edit.pickMaterialStageFarm')">
              <span class="form-label">
                {{ t('edit.materialStage') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.Materials"
            size="large"
            :placeholder="t('edit.pickMaterialStage')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.Materials', formData.Stage.Materials)"
          >
            <a-select-option value="-">{{ t('edit.keepOriginalConfiguration') }}</a-select-option>
            <template v-for="option in filteredMaterialOptions" :key="option.value">
              <a-select-option :value="option.value">{{ option.label }}</a-select-option>
            </template>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第四行：历战余响 | 模拟宇宙 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="EchoOfWar">
          <template #label>
            <a-tooltip :title="t('edit.pickDivergentUniverseStage3')">
              <span class="form-label">
                {{ t('edit.divergentUniverse') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.EchoOfWar"
            size="large"
            :placeholder="t('edit.pickDivergentUniverseStage2')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.EchoOfWar', formData.Stage.EchoOfWar)"
          >
            <a-select-option value="-">{{ t('edit.disabled') }}</a-select-option>
            <a-select-option value="Echo_of_War_The_Comedy_of_Doom"
              >坏灭的喜剧（二相乐园）</a-select-option
            >
            <a-select-option value="Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass"
              >铁骸的锈冢（翁法罗斯）</a-select-option
            >
            <a-select-option value="Echo_of_War_Glance_of_Twilight"
              >晨昏的回眸（翁法罗斯）</a-select-option
            >
            <a-select-option value="Echo_of_War_Inner_Beast_Battlefield"
              >心兽的战场（仙舟「罗浮」）</a-select-option
            >
            <a-select-option value="Echo_of_War_Salutations_of_Ashen_Dreams"
              >尘梦的赞礼（匹诺康尼）</a-select-option
            >
            <a-select-option value="Echo_of_War_Borehole_Planet_Past_Nightmares"
              >蛀星的旧魇（空间站「黑塔」）</a-select-option
            >
            <a-select-option value="Echo_of_War_Divine_Seed"
              >不死的神实（仙舟「罗浮」）</a-select-option
            >
            <a-select-option value="Echo_of_War_End_of_the_Eternal_Freeze"
              >寒潮的落幕（雅利洛-Ⅵ）</a-select-option
            >
            <a-select-option value="Echo_of_War_Destruction_Beginning"
              >毁灭的开端（空间站「黑塔」）</a-select-option
            >
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="SimulatedUniverseWorld">
          <template #label>
            <a-tooltip :title="t('edit.pickSimulatedUniverseWorld2')">
              <span class="form-label">
                {{ t('edit.simulatedUniverse') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.SimulatedUniverseWorld"
            size="large"
            :placeholder="t('edit.pickSimulatedUniverseWorld')"
            show-search
            :filter-option="filterOption"
            @change="
              emitSave('Stage.SimulatedUniverseWorld', formData.Stage.SimulatedUniverseWorld)
            "
          >
            <a-select-option value="-">{{ t('edit.disabled') }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_3">{{
              t('edit.world3')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_4">{{
              t('edit.world4')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_5">{{
              t('edit.world5')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_6">{{
              t('edit.world6')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_8">{{
              t('edit.world8')
            }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第五行：使用储备开拓力 | 使用燃料 | 保留的燃料数量 -->
    <a-row :gutter="24">
      <a-col :span="formData.Stage.UseFuel ? 8 : 12">
        <a-form-item name="ExtractReservedTrailblazePower">
          <template #label>
            <a-tooltip :title="t('edit.whetherReservedTrailblazePower')">
              <span class="form-label">
                {{ t('edit.useReservedTrailblazePower') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.ExtractReservedTrailblazePower"
            size="large"
            @change="
              emitSave(
                'Stage.ExtractReservedTrailblazePower',
                formData.Stage.ExtractReservedTrailblazePower
              )
            "
          >
            <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="formData.Stage.UseFuel ? 8 : 12">
        <a-form-item name="UseFuel">
          <template #label>
            <a-tooltip :title="t('edit.whetherFuelUsed')">
              <span class="form-label">
                {{ t('edit.useFuel') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Stage.UseFuel"
            size="large"
            @change="emitSave('Stage.UseFuel', formData.Stage.UseFuel)"
          >
            <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col v-if="formData.Stage.UseFuel" :span="8">
        <a-form-item name="FuelReserve">
          <template #label>
            <a-tooltip :title="t('edit.fuelKeepReserveWhen')">
              <span class="form-label">
                {{ t('edit.fuelKeep') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input-number
            v-model:value="formData.Stage.FuelReserve"
            :min="0"
            :max="9999"
            placeholder="5"
            size="large"
            style="width: 100%"
            @blur="emitSave('Stage.FuelReserve', formData.Stage.FuelReserve)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()

const formData = defineModel<any>('formData', { required: true })
defineProps<{
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

// 材料关类别筛选
const materialCategory = ref('')

// 材料关卡选项
const materialOptions = [
  // 拟造花萼（金）
  {
    value: 'Calyx_Golden_Memories_Planarcadia',
    label: t('edit.materialCharacterExp'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Planarcadia',
    label: t('edit.materialLightConeExp'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Planarcadia',
    label: t('edit.materialCredits'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_Amphoreus',
    label: t('edit.materialCharacterExp4'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Amphoreus',
    label: t('edit.materialLightConeExp4'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Amphoreus',
    label: t('edit.materialCredits4'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_Penacony',
    label: t('edit.materialCharacterExp3'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Penacony',
    label: t('edit.materialLightConeExp3'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Penacony',
    label: t('edit.materialCredits3'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_The_Xianzhou_Luofu',
    label: t('edit.materialCharacterExp2'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_The_Xianzhou_Luofu',
    label: t('edit.materialLightConeExp2'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_The_Xianzhou_Luofu',
    label: t('edit.materialCredits2'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_Jarilo_VI',
    label: t('edit.materialCharacterExp5'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Jarilo_VI',
    label: t('edit.materialLightConeExp5'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Jarilo_VI',
    label: t('edit.materialCredits5'),
    category: 'Calyx_Golden',
  },
  // 拟造花萼（赤）
  {
    value: 'Calyx_Crimson_Destruction_Herta_StorageZone',
    label: t('edit.traceMaterialDestruction'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Destruction_Luofu_ScalegorgeWaterscape',
    label: t('edit.traceMaterialDestruction3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Destruction_Planarcadia_InkfordHermitage',
    label: t('edit.traceMaterialDestruction2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Preservation_Herta_SupplyZone',
    label: t('edit.traceMaterialPreservation2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Preservation_Penacony_ClockStudiosThemePark',
    label: t('edit.traceMaterialPreservation'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_The_Hunt_Jarilo_OutlyingSnowPlains',
    label: t('edit.traceMaterialHunt'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_The_Hunt_Penacony_SoulGladScorchsandAuditionVenue',
    label: t('edit.traceMaterialHunt2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_The_Hunt_Amphoreus_MemortisShoreRuinsofTime',
    label: t('edit.traceMaterialHunt3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Abundance_Jarilo_BackwaterPass',
    label: t('edit.traceMaterialAbundance2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Abundance_Luofu_FyxestrollGarden',
    label: t('edit.traceMaterialAbundance'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Erudition_Jarilo_RivetTown',
    label: t('edit.traceMaterialErudition3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Erudition_Penacony_PenaconyGrandTheater',
    label: t('edit.traceMaterialErudition'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Erudition_Planarcadia_SeafeldTVTower',
    label: t('edit.traceMaterialErudition2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Harmony_Jarilo_RobotSettlement',
    label: t('edit.traceMaterialHarmony'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Harmony_Penacony_TheReverieDreamscape',
    label: t('edit.traceMaterialHarmony2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Nihility_Jarilo_GreatMine',
    label: t('edit.traceMaterialNihility2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Nihility_Luofu_AlchemyCommission',
    label: t('edit.traceMaterialNihility'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Nihility_Amphoreus_RadiantScarwoodGroveofEpiphany',
    label: t('edit.traceMaterialNihility3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Remembrance_Amphoreus_StrifeRuinsCastrumKremnos',
    label: t('edit.traceMaterialRemembrance'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Elation_Planarcadia_WorldEndTavern',
    label: t('edit.traceMaterialJoy'),
    category: 'Calyx_Crimson',
  },
  // 凝滞虚影
  {
    value: 'Stagnant_Shadow_Spike',
    label: t('edit.ascensionMaterialPhysical2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Perdition',
    label: t('edit.ascensionMaterialPhysical3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Duty',
    label: t('edit.ascensionMaterialPhysical'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Deepsheaf',
    label: t('edit.ascensionMaterialPhysical4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Blaze',
    label: t('edit.ascensionMaterialFire2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Scorch',
    label: t('edit.ascensionMaterialFire3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Roast',
    label: t('edit.ascensionMaterialQuantum2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Ire',
    label: t('edit.ascensionMaterialFire4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Ashes',
    label: t('edit.ascensionMaterialFire'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Rime',
    label: t('edit.ascensionMaterialIce'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Icicle',
    label: t('edit.ascensionMaterialIce2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Nectar',
    label: t('edit.ascensionMaterialIce3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Sirens',
    label: t('edit.ascensionMaterialIce4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Fulmination',
    label: t('edit.ascensionMaterialLightning4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Doom',
    label: t('edit.ascensionMaterialLightning2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Mechwolf',
    label: t('edit.ascensionMaterialLightning3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Soundburst',
    label: t('edit.ascensionMaterialLightning'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Gust',
    label: t('edit.ascensionMaterialWind'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Celestial',
    label: t('edit.ascensionMaterialWind2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Gloam',
    label: t('edit.ascensionMaterialWindSaber'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Cinders',
    label: t('edit.ascensionMaterialWind3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Quanta',
    label: t('edit.ascensionMaterialQuantum4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Abomination',
    label: t('edit.ascensionMaterialQuantum'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Gelidmoon',
    label: t('edit.ascensionMaterialQuantumArcher'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Devour',
    label: t('edit.ascensionMaterialQuantum3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Mirage',
    label: t('edit.ascensionMaterialImaginary3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Puppetry',
    label: t('edit.ascensionMaterialImaginary'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Timbre',
    label: t('edit.ascensionMaterialImaginary2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Sloggyre',
    label: t('edit.ascensionMaterialImaginaryLv'),
    category: 'Stagnant_Shadow',
  },
]

// 筛选后的材料关卡选项
const filteredMaterialOptions = computed(() => {
  if (!materialCategory.value) {
    return materialOptions
  }
  return materialOptions.filter(option => option.category === materialCategory.value)
})

// 获取当前生效关卡
const getCurrentStage = () => {
  const channel = formData.value.Stage.Channel
  if (channel === 'Relic') {
    return getStageLabel(formData.value.Stage.Relic, 'Relic')
  } else if (channel === 'Materials') {
    return getStageLabel(formData.value.Stage.Materials, 'Materials')
  } else if (channel === 'Ornament') {
    return getStageLabel(formData.value.Stage.Ornament, 'Ornament')
  }
  return '未配置'
}

// 获取当前生效关卡的颜色（根据前缀）
const getCurrentStageColor = () => {
  const channel = formData.value.Stage.Channel
  let value = ''

  if (channel === 'Relic') {
    value = formData.value.Stage.Relic
  } else if (channel === 'Materials') {
    value = formData.value.Stage.Materials
  } else if (channel === 'Ornament') {
    value = formData.value.Stage.Ornament
  }

  if (!value || value === '-') return 'default'

  // 根据关卡前缀返回颜色
  if (value.startsWith('Cavern_of_Corrosion')) return 'purple'
  if (value.startsWith('Divergent_Universe')) return 'cyan'
  if (value.startsWith('Calyx_Golden')) return 'gold'
  if (value.startsWith('Calyx_Crimson')) return 'red'
  if (value.startsWith('Stagnant_Shadow')) return 'volcano'
  if (value.startsWith('Echo_of_War')) return 'magenta'
  if (value.startsWith('Simulated_Universe')) return 'geekblue'

  return 'blue'
}

// 获取关卡标签
const getStageLabel = (value: string, type: string) => {
  if (!value || value === '-') return '禁用'

  const stageMap: Record<string, string> = {
    // 遗器
    Cavern_of_Corrosion_Path_of_Insight: '遗器：领航员 & 名冶（观火之径）',
    Cavern_of_Corrosion_Path_of_Possession: '遗器：魔法少女 & 卜者（魔占之径）',
    Cavern_of_Corrosion_Path_of_Hidden_Salvation: '遗器：救世主 & 隐士（隐救之径）',
    Cavern_of_Corrosion_Path_of_Thundersurge: '遗器：烈阳 & 船长（雳涌之径）',
    Cavern_of_Corrosion_Path_of_Aria: '遗器：英豪 & 诗人（弦歌之径）',
    Cavern_of_Corrosion_Path_of_Uncertainty: '遗器：司铎 & 学者（迷识之径）',
    Cavern_of_Corrosion_Path_of_Cavalier: '遗器：铁骑 & 勇烈（勇骑之径）',
    Cavern_of_Corrosion_Path_of_Dreamdive: '遗器：死水 & 钟表匠（梦潜之径）',
    Cavern_of_Corrosion_Path_of_Darkness: '遗器：大公 & DoT套（幽冥之径）',
    Cavern_of_Corrosion_Path_of_Elixir_Seekers: '遗器：莳者 & 信使（药使之径）',
    Cavern_of_Corrosion_Path_of_Conflagration: '遗器：火套 & 虚数套（野焰之径）',
    Cavern_of_Corrosion_Path_of_Holy_Hymn: '遗器：防御套 & 雷套（圣颂之径）',
    Cavern_of_Corrosion_Path_of_Providence: '遗器：铁卫 & 量子套（睿治之径）',
    Cavern_of_Corrosion_Path_of_Drifting: '遗器：治疗套 & 快枪手（漂泊之径）',
    Cavern_of_Corrosion_Path_of_Jabbing_Punch: '遗器：物理套 & 怪盗（迅拳之径）',
    Cavern_of_Corrosion_Path_of_Gelid_Wind: '遗器：冰套 & 风套（霜风之径）',
    // 饰品
    Divergent_Universe_Bugs_Incoming: '饰品：坠星 & 寰宇（虫虫来袭）',
    Divergent_Universe_Gilded_Recollection: '饰品：朋克洛德 & 千星荟萃（鎏金追忆）',
    Divergent_Universe_Within_the_West_Wind: '饰品：翁法罗斯 & 天国（西风丛中）',
    Divergent_Universe_Moonlit_Blood: '饰品：妖精 & 沉醉（月下朱殷）',
    Divergent_Universe_Unceasing_Strife: '饰品：拾骨地 & 巨树（纷争不休）',
    Divergent_Universe_Famished_Worker: '饰品：海域 & 奇想（蠹役饥肠）',
    Divergent_Universe_Eternal_Comedy: '饰品：奔狼 & 火宫（永恒笑剧）',
    Divergent_Universe_To_Sweet_Dreams: '饰品：茨冈尼亚 & 出云（伴你入眠）',
    Divergent_Universe_Pouring_Blades: '饰品：苍穹 & 匹诺康尼（天剑如雨）',
    Divergent_Universe_Fruit_of_Evil: '饰品：繁星 & 龙骨（孽果盘生）',
    Divergent_Universe_Permafrost: '饰品：贝洛伯格 & 萨尔索图（百年冻土）',
    Divergent_Universe_Gentle_Words: '饰品：商业公司 & 差分机（温柔话语）',
    Divergent_Universe_Smelted_Heart: '饰品：盗贼 & 翁瓦克（浴火钢心）',
    Divergent_Universe_Untoppled_Walls: '饰品：太空 & 仙舟（坚城不倒）',
  }

  // 材料关卡从materialOptions中查找
  if (type === 'Materials') {
    const option = materialOptions.find(opt => opt.value === value)
    return option ? option.label : value
  }

  return stageMap[value] || value
}

// 下拉框过滤函数
const filterOption = (input: string, option: any) => {
  const text = option.children?.[0]?.children || option.label || ''
  return text.toLowerCase().indexOf(input.toLowerCase()) >= 0
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.current-stage-display {
  display: flex;
  align-items: center;
  min-height: 40px;
}

.stage-tag {
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 6px;
  margin: 0;
}
</style>
