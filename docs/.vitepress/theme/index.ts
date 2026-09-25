import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import HeroMap from './HeroMap.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  // The live map takes the hero's image slot, next to the headline
  Layout: () => h(DefaultTheme.Layout, null, { 'home-hero-image': () => h(HeroMap) }),
}
