import { createRouter, createWebHashHistory } from 'vue-router'
import VueDetectView from '../views/VueDetectView.vue'
import DetectTaskDetailView from '../views/DetectTaskDetailView.vue'
import VueChunkView from '../views/VueChunkView.vue'
import ProjectChunkDetailView from '../views/ProjectChunkDetailView.vue'
import VueApiView from '../views/VueApiView.vue'
import VueRequestView from '../views/VueRequestView.vue'

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/vueChunk',
    },
    {
      path: '/vueDetect',
      name: 'vue-detect',
      component: VueDetectView,
    },
    {
      path: '/vueDetect/tasks/:taskId',
      name: 'vue-detect-task-detail',
      component: DetectTaskDetailView,
    },
    {
      path: '/vueChunk',
      name: 'vue-chunk',
      component: VueChunkView,
    },
    {
      path: '/vueChunk/projects/:domain',
      name: 'vue-chunk-project-detail',
      component: ProjectChunkDetailView,
    },
    {
      path: '/vueApi',
      name: 'vue-api',
      component: VueApiView,
    },
    {
      path: '/vueRequest',
      name: 'vue-request',
      component: VueRequestView,
    },
  ],
})

export default router
