<script setup>
import { withBase } from 'vitepress'
</script>

<template>
  <figure class="pulse-live">
    <img
      :src="withBase('/assets/pulse-map-demo.svg')"
      alt="Animated Pulse map showing people and agents building, waiting for input, and running checks in parallel."
      width="752"
      height="842"
    >
    <figcaption>
      A morning at a small shop project, in time-lapse.
      The same view runs in your terminal: <a :href="withBase('/guides/pulse-map')"><code>pulse map</code></a>.
    </figcaption>
  </figure>
</template>
