<script setup>
import { withBase } from 'vitepress'
</script>

<template>
  <div class="pulse-live">
    <iframe :src="withBase('/map-demo.html')" title="The Pulse map: a morning at acme/shop in time-lapse"></iframe>
    <p>A morning at a small shop project, in time-lapse. Sebastian runs five agents at once; Alice and Bob work on several items in parallel. <span class="k ok"></span> working <span class="k hold"></span> waiting for you <span class="k bad"></span> a check failed. The same view runs in your terminal: <code>pulse map</code>.</p>
  </div>
</template>
