import { ref } from 'vue'
import { defineStore } from 'pinia'
import { pickHomeGreeting } from '@/views/home/homeGreeting'

export const useHomeGreetingStore = defineStore('homeGreeting', () => {
  const greeting = ref(pickHomeGreeting())

  const refreshGreeting = () => {
    greeting.value = pickHomeGreeting(greeting.value.text)
  }

  return { greeting, refreshGreeting }
})
