import { config } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach } from 'vitest'

beforeEach(() => {
  setActivePinia(createPinia())
})

config.global.stubs = {
  ...config.global.stubs,
  RouterLink: {
    props: ['to'],
    template: '<a><slot /></a>',
  },
}
