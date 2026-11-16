<template>
  <div class="form-section">
    <!-- 第一行：刷取类型 | 当前生效关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="Channel">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.farmType')"
              :hint="t('core.edit.pickStageTypeFarm')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.Channel"
            size="large"
            :placeholder="t('core.edit.pickFarmType')"
            @change="emitSave('Stage.Channel', formData.Stage.Channel)"
          >
            <a-select-option value="Relic">{{ t('core.edit.relic') }}</a-select-option>
            <a-select-option value="Materials">{{ t('core.edit.material') }}</a-select-option>
            <a-select-option value="Ornament">{{ t('core.edit.ornament') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.activeStage')"
              :hint="t('core.edit.activeStageTakenFrom')"
              variant="form"
            />
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
            <FieldLabelWithHint
              :text="t('core.edit.relicStage')"
              :hint="t('core.edit.pickRelicStageFarm')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.Relic"
            size="large"
            :placeholder="t('core.edit.pickRelicStage')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.Relic', formData.Stage.Relic)"
          >
            <a-select-option value="-">{{
              t('core.edit.keepOriginalConfiguration')
            }}</a-select-option>
            <a-select-option v-for="(label, value) in relicStageLabels" :key="value" :value="value">
              {{ label }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="Ornament">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.ornamentStage')"
              :hint="t('core.edit.pickOrnamentStageFarm')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.Ornament"
            size="large"
            :placeholder="t('core.edit.pickOrnamentStage')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.Ornament', formData.Stage.Ornament)"
          >
            <a-select-option value="-">{{
              t('core.edit.keepOriginalConfiguration')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Bugs_Incoming">{{
              t('core.edit.srcStage17')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Gilded_Recollection">{{
              t('core.edit.srcStage18')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Within_the_West_Wind">{{
              t('core.edit.srcStage19')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Moonlit_Blood">{{
              t('core.edit.srcStage20')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Unceasing_Strife">{{
              t('core.edit.srcStage21')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Famished_Worker">{{
              t('core.edit.srcStage22')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Eternal_Comedy">{{
              t('core.edit.srcStage23')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_To_Sweet_Dreams">{{
              t('core.edit.srcStage24')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Pouring_Blades">{{
              t('core.edit.srcStage25')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Fruit_of_Evil">{{
              t('core.edit.srcStage26')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Permafrost">{{
              t('core.edit.srcStage27')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Gentle_Words">{{
              t('core.edit.srcStage28')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Smelted_Heart">{{
              t('core.edit.srcStage29')
            }}</a-select-option>
            <a-select-option value="Divergent_Universe_Untoppled_Walls">{{
              t('core.edit.srcStage30')
            }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第三行：材料关类别 | 材料关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.materialCategory')"
              :hint="t('core.edit.filteredByMaterialStage')"
              variant="form"
            />
          </template>
          <a-select v-model:value="materialCategory" size="large" :placeholder="t('core.edit.all')">
            <a-select-option value="">{{ t('core.edit.all') }}</a-select-option>
            <a-select-option value="Calyx_Golden">{{ t('core.edit.calyxGolden') }}</a-select-option>
            <a-select-option value="Calyx_Crimson">{{
              t('core.edit.calyxCrimson')
            }}</a-select-option>
            <a-select-option value="Stagnant_Shadow">{{
              t('core.edit.stagnantShadow')
            }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="Materials">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.materialStage')"
              :hint="t('core.edit.pickMaterialStageFarm')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.Materials"
            size="large"
            :placeholder="t('core.edit.pickMaterialStage')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.Materials', formData.Stage.Materials)"
          >
            <a-select-option value="-">{{
              t('core.edit.keepOriginalConfiguration')
            }}</a-select-option>
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
            <FieldLabelWithHint
              :text="t('core.edit.echoOfWar')"
              :hint="t('core.edit.pickDivergentUniverseStage3')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.EchoOfWar"
            size="large"
            :placeholder="t('core.edit.pickDivergentUniverseStage2')"
            show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.EchoOfWar', formData.Stage.EchoOfWar)"
          >
            <a-select-option value="-">{{ t('core.edit.disabled') }}</a-select-option>
            <a-select-option value="Echo_of_War_The_Comedy_of_Doom">{{
              t('core.edit.srcStage31')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass">{{
              t('core.edit.srcStage32')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Glance_of_Twilight">{{
              t('core.edit.srcStage33')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Inner_Beast_Battlefield">{{
              t('core.edit.srcStage34')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Salutations_of_Ashen_Dreams">{{
              t('core.edit.srcStage35')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Borehole_Planet_Past_Nightmares">{{
              t('core.edit.srcStage36')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Divine_Seed">{{
              t('core.edit.srcStage37')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_End_of_the_Eternal_Freeze">{{
              t('core.edit.srcStage38')
            }}</a-select-option>
            <a-select-option value="Echo_of_War_Destruction_Beginning">{{
              t('core.edit.srcStage39')
            }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="SimulatedUniverseWorld">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.simulatedUniverse')"
              :hint="t('core.edit.pickSimulatedUniverseWorld2')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.SimulatedUniverseWorld"
            size="large"
            :placeholder="t('core.edit.pickSimulatedUniverseWorld')"
            show-search
            :filter-option="filterOption"
            @change="
              emitSave('Stage.SimulatedUniverseWorld', formData.Stage.SimulatedUniverseWorld)
            "
          >
            <a-select-option value="-">{{ t('core.edit.disabled') }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_3">{{
              t('core.edit.world3')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_4">{{
              t('core.edit.world4')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_5">{{
              t('core.edit.world5')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_6">{{
              t('core.edit.world6')
            }}</a-select-option>
            <a-select-option value="Simulated_Universe_World_8">{{
              t('core.edit.world8')
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
            <FieldLabelWithHint
              :text="t('core.edit.useReservedTrailblazePower')"
              :hint="t('core.edit.whetherReservedTrailblazePower')"
              variant="form"
            />
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
            <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="formData.Stage.UseFuel ? 8 : 12">
        <a-form-item name="UseFuel">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.useFuel')"
              :hint="t('core.edit.whetherFuelUsed')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Stage.UseFuel"
            size="large"
            @change="emitSave('Stage.UseFuel', formData.Stage.UseFuel)"
          >
            <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col v-if="formData.Stage.UseFuel" :span="8">
        <a-form-item name="FuelReserve">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.fuelKeep')"
              :hint="t('core.edit.fuelKeepReserveWhen')"
              variant="form"
            />
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
import type { SrcUserConfig_Stage } from '@/api/models/SrcUserConfig_Stage'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'

type RelicStage = Exclude<NonNullable<SrcUserConfig_Stage['Relic']>, '-'>

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

const relicStageLabels = computed(
  () =>
    ({
      Cavern_of_Corrosion_Path_of_the_Secret_Actor: t('core.edit.srcStageSecretActor'),
      Cavern_of_Corrosion_Path_of_Insight: t('core.edit.srcStage1'),
      Cavern_of_Corrosion_Path_of_Possession: t('core.edit.srcStage2'),
      Cavern_of_Corrosion_Path_of_Hidden_Salvation: t('core.edit.srcStage3'),
      Cavern_of_Corrosion_Path_of_Thundersurge: t('core.edit.srcStage4'),
      Cavern_of_Corrosion_Path_of_Aria: t('core.edit.srcStage5'),
      Cavern_of_Corrosion_Path_of_Uncertainty: t('core.edit.srcStage6'),
      Cavern_of_Corrosion_Path_of_Cavalier: t('core.edit.srcStage7'),
      Cavern_of_Corrosion_Path_of_Dreamdive: t('core.edit.srcStage8'),
      Cavern_of_Corrosion_Path_of_Darkness: t('core.edit.srcStage9'),
      Cavern_of_Corrosion_Path_of_Elixir_Seekers: t('core.edit.srcStage10'),
      Cavern_of_Corrosion_Path_of_Conflagration: t('core.edit.srcStage11'),
      Cavern_of_Corrosion_Path_of_Holy_Hymn: t('core.edit.srcStage12'),
      Cavern_of_Corrosion_Path_of_Providence: t('core.edit.srcStage13'),
      Cavern_of_Corrosion_Path_of_Drifting: t('core.edit.srcStage14'),
      Cavern_of_Corrosion_Path_of_Jabbing_Punch: t('core.edit.srcStage15'),
      Cavern_of_Corrosion_Path_of_Gelid_Wind: t('core.edit.srcStage16'),
    }) satisfies Record<RelicStage, string>
)

// 材料关类别筛选
const materialCategory = ref('')

// 材料关卡选项
const materialOptions = computed(() => [
  // 拟造花萼（金）
  {
    value: 'Calyx_Golden_Memories_Planarcadia',
    label: t('core.edit.materialCharacterExp'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Planarcadia',
    label: t('core.edit.materialLightConeExp'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Planarcadia',
    label: t('core.edit.materialCredits'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_Amphoreus',
    label: t('core.edit.materialCharacterExp4'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Amphoreus',
    label: t('core.edit.materialLightConeExp4'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Amphoreus',
    label: t('core.edit.materialCredits4'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_Penacony',
    label: t('core.edit.materialCharacterExp3'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Penacony',
    label: t('core.edit.materialLightConeExp3'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Penacony',
    label: t('core.edit.materialCredits3'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_The_Xianzhou_Luofu',
    label: t('core.edit.materialCharacterExp2'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_The_Xianzhou_Luofu',
    label: t('core.edit.materialLightConeExp2'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_The_Xianzhou_Luofu',
    label: t('core.edit.materialCredits2'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Memories_Jarilo_VI',
    label: t('core.edit.materialCharacterExp5'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Aether_Jarilo_VI',
    label: t('core.edit.materialLightConeExp5'),
    category: 'Calyx_Golden',
  },
  {
    value: 'Calyx_Golden_Treasures_Jarilo_VI',
    label: t('core.edit.materialCredits5'),
    category: 'Calyx_Golden',
  },
  // 拟造花萼（赤）
  {
    value: 'Calyx_Crimson_Destruction_Herta_StorageZone',
    label: t('core.edit.traceMaterialDestruction'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Destruction_Luofu_ScalegorgeWaterscape',
    label: t('core.edit.traceMaterialDestruction3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Destruction_Planarcadia_InkfordHermitage',
    label: t('core.edit.traceMaterialDestruction2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Preservation_Herta_SupplyZone',
    label: t('core.edit.traceMaterialPreservation2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Preservation_Penacony_ClockStudiosThemePark',
    label: t('core.edit.traceMaterialPreservation'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_The_Hunt_Jarilo_OutlyingSnowPlains',
    label: t('core.edit.traceMaterialHunt'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_The_Hunt_Penacony_SoulGladScorchsandAuditionVenue',
    label: t('core.edit.traceMaterialHunt2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_The_Hunt_Amphoreus_MemortisShoreRuinsofTime',
    label: t('core.edit.traceMaterialHunt3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Abundance_Jarilo_BackwaterPass',
    label: t('core.edit.traceMaterialAbundance2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Abundance_Luofu_FyxestrollGarden',
    label: t('core.edit.traceMaterialAbundance'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Erudition_Jarilo_RivetTown',
    label: t('core.edit.traceMaterialErudition3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Erudition_Penacony_PenaconyGrandTheater',
    label: t('core.edit.traceMaterialErudition'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Erudition_Planarcadia_SeafeldTVTower',
    label: t('core.edit.traceMaterialErudition2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Harmony_Jarilo_RobotSettlement',
    label: t('core.edit.traceMaterialHarmony'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Harmony_Penacony_TheReverieDreamscape',
    label: t('core.edit.traceMaterialHarmony2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Nihility_Jarilo_GreatMine',
    label: t('core.edit.traceMaterialNihility2'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Nihility_Luofu_AlchemyCommission',
    label: t('core.edit.traceMaterialNihility'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Nihility_Amphoreus_RadiantScarwoodGroveofEpiphany',
    label: t('core.edit.traceMaterialNihility3'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Remembrance_Amphoreus_StrifeRuinsCastrumKremnos',
    label: t('core.edit.traceMaterialRemembrance'),
    category: 'Calyx_Crimson',
  },
  {
    value: 'Calyx_Crimson_Elation_Planarcadia_WorldEndTavern',
    label: t('core.edit.traceMaterialJoy'),
    category: 'Calyx_Crimson',
  },
  // 凝滞虚影
  {
    value: 'Stagnant_Shadow_Spike',
    label: t('core.edit.ascensionMaterialPhysical2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Perdition',
    label: t('core.edit.ascensionMaterialPhysical3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Duty',
    label: t('core.edit.ascensionMaterialPhysical'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Deepsheaf',
    label: t('core.edit.ascensionMaterialPhysical4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Blaze',
    label: t('core.edit.ascensionMaterialFire2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Scorch',
    label: t('core.edit.ascensionMaterialFire3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Roast',
    label: t('core.edit.ascensionMaterialQuantum2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Ire',
    label: t('core.edit.ascensionMaterialFire4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Ashes',
    label: t('core.edit.ascensionMaterialFire'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Rime',
    label: t('core.edit.ascensionMaterialIce'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Icicle',
    label: t('core.edit.ascensionMaterialIce2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Nectar',
    label: t('core.edit.ascensionMaterialIce3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Sirens',
    label: t('core.edit.ascensionMaterialIce4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Fulmination',
    label: t('core.edit.ascensionMaterialLightning4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Doom',
    label: t('core.edit.ascensionMaterialLightning2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Mechwolf',
    label: t('core.edit.ascensionMaterialLightning3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Soundburst',
    label: t('core.edit.ascensionMaterialLightning'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Gust',
    label: t('core.edit.ascensionMaterialWind'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Celestial',
    label: t('core.edit.ascensionMaterialWind2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Gloam',
    label: t('core.edit.ascensionMaterialWindSaber'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Cinders',
    label: t('core.edit.ascensionMaterialWind3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Quanta',
    label: t('core.edit.ascensionMaterialQuantum4'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Abomination',
    label: t('core.edit.ascensionMaterialQuantum'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Gelidmoon',
    label: t('core.edit.ascensionMaterialQuantumArcher'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Devour',
    label: t('core.edit.ascensionMaterialQuantum3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Mirage',
    label: t('core.edit.ascensionMaterialImaginary3'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Puppetry',
    label: t('core.edit.ascensionMaterialImaginary'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Timbre',
    label: t('core.edit.ascensionMaterialImaginary2'),
    category: 'Stagnant_Shadow',
  },
  {
    value: 'Stagnant_Shadow_Sloggyre',
    label: t('core.edit.ascensionMaterialImaginaryLv'),
    category: 'Stagnant_Shadow',
  },
])

// 筛选后的材料关卡选项
const filteredMaterialOptions = computed(() => {
  if (!materialCategory.value) {
    return materialOptions.value
  }
  return materialOptions.value.filter(option => option.category === materialCategory.value)
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
  return t('core.edit.srcStageUnconfigured')
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
  if (!value || value === '-') return t('core.edit.disabled')

  const stageMap: Record<string, string> = {
    ...relicStageLabels.value,
    // 饰品
    Divergent_Universe_Bugs_Incoming: t('core.edit.srcStage17'),
    Divergent_Universe_Gilded_Recollection: t('core.edit.srcStage18'),
    Divergent_Universe_Within_the_West_Wind: t('core.edit.srcStage19'),
    Divergent_Universe_Moonlit_Blood: t('core.edit.srcStage20'),
    Divergent_Universe_Unceasing_Strife: t('core.edit.srcStage21'),
    Divergent_Universe_Famished_Worker: t('core.edit.srcStage22'),
    Divergent_Universe_Eternal_Comedy: t('core.edit.srcStage23'),
    Divergent_Universe_To_Sweet_Dreams: t('core.edit.srcStage24'),
    Divergent_Universe_Pouring_Blades: t('core.edit.srcStage25'),
    Divergent_Universe_Fruit_of_Evil: t('core.edit.srcStage26'),
    Divergent_Universe_Permafrost: t('core.edit.srcStage27'),
    Divergent_Universe_Gentle_Words: t('core.edit.srcStage28'),
    Divergent_Universe_Smelted_Heart: t('core.edit.srcStage29'),
    Divergent_Universe_Untoppled_Walls: t('core.edit.srcStage30'),
  }

  // 材料关卡从materialOptions中查找
  if (type === 'Materials') {
    const option = materialOptions.value.find(opt => opt.value === value)
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
