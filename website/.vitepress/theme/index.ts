import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import './custom.css'

import HomeHero from './components/HomeHero.vue'
import StatStrip from './components/StatStrip.vue'
import FeatureGrid from './components/FeatureGrid.vue'
import DemoShowcase from './components/DemoShowcase.vue'
import EcoSection from './components/EcoSection.vue'
import FlowSteps from './components/FlowSteps.vue'
import HomeFaq from './components/HomeFaq.vue'
import CtaBox from './components/CtaBox.vue'
import PluginGroups from './components/PluginGroups.vue'
import AccessTypes from './components/AccessTypes.vue'
import NotifyChannels from './components/NotifyChannels.vue'
import CertTable from './components/CertTable.vue'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('HomeHero', HomeHero)
    app.component('StatStrip', StatStrip)
    app.component('FeatureGrid', FeatureGrid)
    app.component('DemoShowcase', DemoShowcase)
    app.component('EcoSection', EcoSection)
    app.component('FlowSteps', FlowSteps)
    app.component('HomeFaq', HomeFaq)
    app.component('CtaBox', CtaBox)
    app.component('PluginGroups', PluginGroups)
    app.component('AccessTypes', AccessTypes)
    app.component('NotifyChannels', NotifyChannels)
    app.component('CertTable', CertTable)
  }
} satisfies Theme
