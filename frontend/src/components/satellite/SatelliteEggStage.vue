<template>
  <!-- 三月七的相册：快门一闪，刚才的画面做成拍立得落下来 -->
  <div v-if="shutterKey" :key="shutterKey" class="egg-shutter"></div>
  <Transition name="egg-polaroid">
    <figure v-if="polaroid" :key="polaroid.key" class="egg-polaroid">
      <img :src="polaroid.src" alt="" />
      <figcaption>{{ t('home.satelliteEgg.photoCaption') }} · {{ polaroid.caption }}</figcaption>
    </figure>
  </Transition>

  <Teleport to="body">
    <!-- 原神，启动！白屏、七元素加载条、光门、点击进入 -->
    <Transition name="egg-fade">
      <div v-if="genshinOpen" class="egg-genshin" @click="closeGenshin">
        <div class="egg-genshin-gate"></div>
        <div class="egg-genshin-content">
          <div class="egg-genshin-title">{{ t('home.satelliteEgg.genshinLaunch') }}</div>
          <div class="egg-genshin-ornament"></div>
          <div class="egg-genshin-elements">
            <span
              v-for="(color, index) in ELEMENT_COLORS"
              :key="color"
              :style="{ '--element': color, '--delay': `${0.6 + index * 0.22}s` }"
            ></span>
          </div>
          <div class="egg-genshin-enter">{{ t('home.satelliteEgg.clickToEnter') }}</div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 开发者头像绑在火箭上满场乱飞，按 commit 数打榜 -->
  <SatelliteRocketRace ref="race" />
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import SatelliteRocketRace from './SatelliteRocketRace.vue'

/** 原神七元素的颜色，按风、岩、雷、草、水、火、冰排 */
const ELEMENT_COLORS = ['#74c2a8', '#fab632', '#af8ec1', '#a5c83b', '#4cc2f1', '#ef7938', '#9fd6e3']
const GENSHIN_MS = 5600
const POLAROID_MS = 4200

const { t } = useI18n()

const shutterKey = ref(0)
const polaroid = ref<{ key: number; src: string; caption: string } | null>(null)
const genshinOpen = ref(false)
const race = ref<InstanceType<typeof SatelliteRocketRace> | null>(null)

const timers = new Set<number>()

function later(callback: () => void, ms: number): void {
  const timer = window.setTimeout(() => {
    timers.delete(timer)
    callback()
  }, ms)
  timers.add(timer)
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') closeGenshin()
}

/** 快门一闪，拍立得落下来，过几秒自己收走 */
function showPolaroid(src: string): void {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  shutterKey.value += 1
  polaroid.value = {
    key: shutterKey.value,
    src,
    caption: `${pad(now.getMonth() + 1)}/${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`,
  }
  const key = shutterKey.value
  later(() => {
    if (polaroid.value?.key === key) polaroid.value = null
  }, POLAROID_MS)
}

function launchGenshin(): void {
  if (genshinOpen.value) return
  genshinOpen.value = true
  window.addEventListener('keydown', handleKeydown)
  later(closeGenshin, GENSHIN_MS)
}

function closeGenshin(): void {
  genshinOpen.value = false
  window.removeEventListener('keydown', handleKeydown)
}

async function launchRockets(): Promise<void> {
  await race.value?.launch()
}

onUnmounted(() => {
  timers.forEach(timer => window.clearTimeout(timer))
  timers.clear()
  window.removeEventListener('keydown', handleKeydown)
})

defineExpose({ showPolaroid, launchGenshin, launchRockets })
</script>

<style scoped>
/* ==================== 三月七的相册 ==================== */
.egg-shutter {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: #fff;
  pointer-events: none;
  animation: egg-shutter 320ms ease-out forwards;
}

@keyframes egg-shutter {
  from {
    opacity: 0.95;
  }
  to {
    opacity: 0;
  }
}

.egg-polaroid {
  position: absolute;
  top: 26px;
  right: 28px;
  z-index: 21;
  width: 230px;
  margin: 0;
  padding: 10px 10px 30px;
  background: #fbfaf6;
  border-radius: 3px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
  transform: rotate(-5deg);
  pointer-events: none;
}

.egg-polaroid img {
  display: block;
  width: 100%;
  height: 150px;
  object-fit: cover;
  background: #111;
}

.egg-polaroid figcaption {
  margin-top: 8px;
  color: #6b5a4e;
  font-size: 13px;
  text-align: center;
  font-family: 'Segoe Print', 'Comic Sans MS', cursive;
}

.egg-polaroid-enter-active {
  transition:
    transform 520ms cubic-bezier(0.2, 1.4, 0.4, 1),
    opacity 300ms;
}

.egg-polaroid-leave-active {
  transition:
    transform 500ms ease-in,
    opacity 500ms ease-in;
}

.egg-polaroid-enter-from {
  opacity: 0;
  transform: translateY(-120px) rotate(-18deg);
}

.egg-polaroid-leave-to {
  opacity: 0;
  transform: translateY(60px) rotate(4deg);
}

/* ==================== 原神，启动！ ==================== */
.egg-fade-enter-active,
.egg-fade-leave-active {
  transition: opacity 420ms ease;
}

.egg-fade-enter-from,
.egg-fade-leave-to {
  opacity: 0;
}

.egg-genshin {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: grid;
  place-items: center;
  overflow: hidden;
  cursor: pointer;
  background: radial-gradient(circle at 50% 46%, #ffffff 0%, #f7f4ec 58%, #e9e3d4 100%);
  font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'SimSun', serif;
}

.egg-genshin-content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 22px;
}

.egg-genshin-title {
  font-size: clamp(34px, 5.4vw, 76px);
  font-weight: 700;
  letter-spacing: 0.32em;
  padding-left: 0.32em;
  background: linear-gradient(90deg, #7a5c2e, #d8b877, #7a5c2e);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
  animation: egg-genshin-title 1.1s cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

@keyframes egg-genshin-title {
  from {
    opacity: 0;
    filter: blur(10px);
    letter-spacing: 0.7em;
    transform: scale(1.08);
  }
  to {
    opacity: 1;
    filter: blur(0);
    letter-spacing: 0.32em;
    transform: scale(1);
  }
}

.egg-genshin-ornament {
  position: relative;
  width: min(420px, 60vw);
  height: 1px;
  background: linear-gradient(90deg, transparent, #c4ad7c, transparent);
  animation: egg-genshin-grow 900ms 300ms ease-out both;
}

.egg-genshin-ornament::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 9px;
  height: 9px;
  border: 1px solid #c4ad7c;
  background: #fbf8f0;
  transform: translate(-50%, -50%) rotate(45deg);
}

@keyframes egg-genshin-grow {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}

.egg-genshin-elements {
  display: flex;
  gap: 26px;
}

.egg-genshin-elements span {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #d9d4c7;
  animation: egg-genshin-element 420ms var(--delay) ease-out forwards;
}

@keyframes egg-genshin-element {
  to {
    background: var(--element);
    box-shadow:
      0 0 10px var(--element),
      0 0 26px var(--element);
    transform: scale(1.15);
  }
}

.egg-genshin-gate {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 4px;
  height: 4px;
  border-radius: 46% 46% 8px 8px / 30% 30% 8px 8px;
  background: radial-gradient(
    ellipse at 50% 60%,
    #ffffff 0%,
    #fff6d8 40%,
    rgba(255, 236, 180, 0) 72%
  );
  box-shadow: 0 0 120px 40px rgba(255, 238, 190, 0.8);
  opacity: 0;
  transform: translate(-50%, -50%);
  animation: egg-genshin-gate 1.6s 2.35s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
}

@keyframes egg-genshin-gate {
  0% {
    opacity: 0;
    width: 4px;
    height: 4px;
  }
  35% {
    opacity: 1;
    width: 6px;
    height: 78vh;
  }
  100% {
    opacity: 0.85;
    width: 38vw;
    height: 86vh;
  }
}

.egg-genshin-enter {
  margin-top: 10px;
  color: #8a7552;
  font-size: 18px;
  letter-spacing: 0.4em;
  padding-left: 0.4em;
  opacity: 0;
  animation:
    egg-genshin-enter 600ms 3.2s ease-out forwards,
    egg-genshin-blink 1.6s 3.8s ease-in-out infinite;
}

@keyframes egg-genshin-enter {
  to {
    opacity: 1;
  }
}

@keyframes egg-genshin-blink {
  50% {
    opacity: 0.35;
  }
}
</style>
