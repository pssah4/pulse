import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import HeroMap from './HeroMap.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  Layout: () => h(DefaultTheme.Layout, null, { 'home-hero-image': () => h(HeroMap) }),
}
