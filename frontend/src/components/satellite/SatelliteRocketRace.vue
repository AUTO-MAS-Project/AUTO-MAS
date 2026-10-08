<template>
  <Transition name="race-fade">
    <div v-if="state" ref="stage" class="race" @pointerdown.stop @click.stop="close">
      <div v-if="state.phase !== 'ready'" class="race-message">
        {{ t(MESSAGE_KEYS[state.phase]) }}
      </div>
      <template v-else>
        <div class="race-countdown">
          <span
            v-for="(step, index) in countdownSteps"
            :key="step"
            :style="{ '--delay': `${index * 0.45}s` }"
          >
            {{ step }}
          </span>
        </div>
        <div ref="puffLayer" class="race-puffs"></div>
        <div
          v-for="(item, index) in racers"
          :key="item.login"
          :ref="element => setRacerElement(index, element)"
          class="race-rocket"
        >
          <div class="race-label">
            <span v-if="index === 0">👑</span>
            #{{ index + 1 }} {{ item.login }}
            <b>{{ item.commits }}</b>
          </div>
          <div class="race-ship">
            <svg viewBox="0 0 64 120" class="race-hull" aria-hidden="true">
              <path d="M32 2 C48 18 52 40 50 78 L14 78 C12 40 16 18 32 2 Z" fill="#eef2f8" />
              <path d="M32 2 C40 10 44 18 46 26 L18 26 C20 18 24 10 32 2 Z" fill="#ff5a5f" />
              <path d="M14 58 L2 92 L16 84 Z M50 58 L62 92 L48 84 Z" fill="#ff5a5f" />
              <rect x="22" y="78" width="20" height="8" rx="2" fill="#6b7280" />
            </svg>
            <!-- 开发者头像绑在机身上：两道绑带斜着勒住 -->
            <div class="race-pilot">
              <img
                v-if="item.avatarUrl"
                :src="sizedAvatar(item.avatarUrl, 64)"
                alt=""
                referrerpolicy="no-referrer"
              />
              <span v-else class="race-initial">{{ item.login.slice(0, 1) }}</span>
              <i class="race-strap"></i>
              <i class="race-strap race-strap-2"></i>
            </div>
            <div class="race-flame"></div>
          </div>
        </div>
        <SatelliteRocketBoard :list="state.list" :max="state.max" :fetched-at="state.fetchedAt" />
      </template>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, type ComponentPublicInstance } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchWeeklyBoard, sizedAvatar, type Contributor } from './contributors'
import {
  createRocketPath,
  getRocketPose,
  RACE_TIMELINE,
  type FlightBox,
  type RocketPath,
} from './rocketFlight'
import SatelliteRocketBoard from './SatelliteRocketBoard.vue'

/** 只放前几名：再多就成了一锅粥 */
const MAX_ROCKETS = 6
/** 榜单占掉右边这么宽，火箭只在左边乱飞 */
const BOARD_SPACE = 290
/** 每枚火箭隔多久冒一团烟；整场同时在飘的烟团上限 */
const PUFF_INTERVAL = 70
const MAX_PUFFS = 90
/** 拉榜单期间、拉不到、本周没人提交时显示的话 */
const MESSAGE_KEYS = {
  fueling: 'home.satelliteEgg.rocketFueling',
  failed: 'home.satelliteEgg.rocketNoFuel',
  empty: 'home.satelliteEgg.rocketEmpty',
} as const

interface RaceState {
  phase: 'fueling' | 'failed' | 'empty' | 'ready'
  list: Contributor[]
  max: number
  fetchedAt: string
}

const { t } = useI18n()
const logger = window.electronAPI.getLogger('卫星动画')

const state = ref<RaceState | null>(null)
const stage = ref<HTMLDivElement | null>(null)
const puffLayer = ref<HTMLDivElement | null>(null)
const countdownSteps = computed(() => ['3', '2', '1', t('home.satelliteEgg.rocketLaunch')])
const racers = computed(() => state.value?.list.slice(0, MAX_ROCKETS) ?? [])

let racerElements: (HTMLElement | null)[] = []
let paths: RocketPath[] = []
let frame: number | null = null
let closeTimer: number | null = null
const lastPuffAt: number[] = []

function setRacerElement(index: number, element: Element | ComponentPublicInstance | null): void {
  racerElements[index] = element instanceof HTMLElement ? element : null
}

/** 先加油（拉 GitHub 贡献者），拉到了就倒数发射；拉不到显示没油了，一会儿自己关 */
async function launch(): Promise<void> {
  if (state.value) return
  state.value = { phase: 'fueling', list: [], max: 1, fetchedAt: '' }
  window.addEventListener('keydown', handleKeydown)

  try {
    const { list } = await fetchWeeklyBoard()
    if (!state.value) return
    if (list.length === 0) {
      state.value = { ...state.value, phase: 'empty' }
      closeTimer = window.setTimeout(close, 2600)
      return
    }
    const max = Math.max(1, list[0]?.commits ?? 1)
    state.value = { phase: 'ready', list, max, fetchedAt: new Date().toLocaleTimeString() }
    paths = list
      .slice(0, MAX_ROCKETS)
      .map((item, index, top) => createRocketPath(index, top.length, Math.sqrt(item.commits / max)))
    await nextTick()
    startFlight()
    closeTimer = window.setTimeout(close, RACE_TIMELINE.end)
  } catch (err) {
    logger.warn(`开发者打榜拉取贡献者失败: ${String(err)}`)
    if (!state.value) return
    state.value = { ...state.value, phase: 'failed' }
    closeTimer = window.setTimeout(close, 2600)
  }
}

function startFlight(): void {
  const start = performance.now()
  lastPuffAt.length = 0
  const step = (now: number) => {
    const container = stage.value
    if (!container || !state.value) return
    const elapsed = now - start
    const box: FlightBox = {
      left: 50,
      right: Math.max(160, container.clientWidth - BOARD_SPACE),
      top: 60,
      bottom: container.clientHeight - 50,
    }

    paths.forEach((path, index) => {
      const element = racerElements[index]
      if (!element) return
      const pose = getRocketPose(path, box, elapsed)
      element.style.transform = `translate(${pose.x}px, ${pose.y}px)`
      element.style.opacity = pose.visible ? '1' : '0'
      const ship = element.querySelector<HTMLElement>('.race-ship')
      if (ship) ship.style.transform = `translate(-50%, -50%) rotate(${pose.angle}deg)`
      // 机身跟着方向转，头像和名字首字反着转回来，始终摆正
      const pilot = element.querySelector<HTMLElement>('.race-pilot')
      if (pilot) pilot.style.transform = `translateX(-50%) rotate(${-pose.angle}deg)`

      // 尾巴后面一路冒烟
      if (
        pose.visible &&
        elapsed > RACE_TIMELINE.liftoff &&
        now - (lastPuffAt[index] ?? 0) > PUFF_INTERVAL
      ) {
        lastPuffAt[index] = now
        const radians = (pose.angle * Math.PI) / 180
        spawnPuff(pose.x - Math.sin(radians) * 30, pose.y + Math.cos(radians) * 30)
      }
    })
    frame = requestAnimationFrame(step)
  }
  frame = requestAnimationFrame(step)
}

function spawnPuff(x: number, y: number): void {
  const layer = puffLayer.value
  if (!layer) return
  while (layer.childElementCount >= MAX_PUFFS) {
    layer.firstElementChild?.remove()
  }
  const puff = document.createElement('span')
  puff.className = 'race-puff'
  puff.style.left = `${x}px`
  puff.style.top = `${y}px`
  puff.addEventListener('animationend', () => puff.remove())
  layer.appendChild(puff)
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') close()
}

function close(): void {
  if (frame !== null) cancelAnimationFrame(frame)
  if (closeTimer !== null) window.clearTimeout(closeTimer)
  frame = null
  closeTimer = null
  racerElements = []
  paths = []
  state.value = null
  window.removeEventListener('keydown', handleKeydown)
}

onUnmounted(close)

defineExpose({ launch })
</script>

<style scoped>
.race {
  position: absolute;
  inset: 0;
  /* 压在场景和浮字上面，彩蛋大字除外 */
  z-index: 15;
  overflow: hidden;
  cursor: pointer;
  background: radial-gradient(
    ellipse at 35% 110%,
    rgba(30, 50, 100, 0.55),
    rgba(4, 8, 18, 0.35) 70%
  );
  color: #e8eefc;
}

.race-fade-enter-active,
.race-fade-leave-active {
  transition: opacity 360ms ease;
}

.race-fade-enter-from,
.race-fade-leave-to {
  opacity: 0;
}

.race-message {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.6);
}

/* 倒数放在左下角，像发射台的读数：左对齐，从左下角往外放大再收回 */
.race-countdown span {
  position: absolute;
  left: 28px;
  bottom: 20px;
  font-size: 64px;
  font-weight: 900;
  line-height: 1;
  white-space: nowrap;
  color: #ffd36b;
  text-shadow: 0 0 26px rgba(255, 180, 60, 0.8);
  opacity: 0;
  transform-origin: left bottom;
  animation: race-countdown 450ms var(--delay) ease-out both;
}

@keyframes race-countdown {
  0% {
    opacity: 0;
    transform: scale(1.6);
  }
  30% {
    opacity: 1;
    transform: scale(1);
  }
  100% {
    opacity: 0;
    transform: scale(0.85);
  }
}

.race-puffs {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.race-puffs :deep(.race-puff) {
  position: absolute;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0));
  transform: translate(-50%, -50%) scale(0.5);
  animation: race-puff 700ms ease-out forwards;
}

@keyframes race-puff {
  to {
    opacity: 0;
    transform: translate(-50%, -50%) scale(2.6);
  }
}

/* 火箭的位置每帧由脚本写在 transform 上，元素本身只是一个点 */
.race-rocket {
  position: absolute;
  left: 0;
  top: 0;
  width: 0;
  height: 0;
  opacity: 0;
  will-change: transform;
}

.race-ship {
  position: absolute;
  left: 0;
  top: 0;
  width: 40px;
  height: 75px;
  transform: translate(-50%, -50%);
}

.race-hull {
  display: block;
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.45));
}

.race-pilot {
  position: absolute;
  left: 50%;
  top: 19px;
  width: 24px;
  height: 24px;
  transform: translateX(-50%);
}

.race-pilot img,
.race-pilot .race-initial {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2px solid #4b5563;
  background: #1f2937;
  object-fit: cover;
}

/* 提交没关联 GitHub 账号时没有头像，显示名字首字 */
.race-initial {
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 800;
  color: #e8eefc;
}

/* 绑在火箭上的两道绑带 */
.race-strap {
  position: absolute;
  left: -4px;
  right: -4px;
  top: 7px;
  height: 3px;
  border-radius: 2px;
  background: #374151;
  transform: rotate(-18deg);
}

.race-strap-2 {
  top: 15px;
  transform: rotate(14deg);
}

.race-flame {
  position: absolute;
  left: 50%;
  top: 70px;
  width: 14px;
  height: 28px;
  border-radius: 50% 50% 50% 50% / 30% 30% 70% 70%;
  background: radial-gradient(
    ellipse at 50% 20%,
    #fffbe0 0%,
    #ffd36b 35%,
    #ff7a2f 70%,
    rgba(255, 80, 30, 0) 100%
  );
  transform: translateX(-50%);
  transform-origin: top center;
  animation: race-flame 90ms linear infinite alternate;
}

@keyframes race-flame {
  from {
    transform: translateX(-50%) scaleY(0.8);
  }
  to {
    transform: translateX(-50%) scaleY(1.2);
  }
}

.race-label {
  position: absolute;
  left: 0;
  top: -54px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.16);
  font-size: 11px;
  white-space: nowrap;
  transform: translateX(-50%);
}

.race-label b {
  margin-left: 3px;
  color: #ffd36b;
}
</style>
