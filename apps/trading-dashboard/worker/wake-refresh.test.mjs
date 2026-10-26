import test from 'node:test'
import assert from 'node:assert/strict'
import { installWakeRefresh } from '../src/wake-refresh.ts'

test('returning to a visible tab, browser history or network requests an immediate refresh', () => {
 const page = new EventTarget(), browser = new EventTarget()
 page.visibilityState = 'hidden'
 let calls = 0
 const dispose = installWakeRefresh(page, browser, () => { calls++ })
 page.dispatchEvent(new Event('visibilitychange'))
 browser.dispatchEvent(new Event('focus'))
 assert.equal(calls, 0)
 page.visibilityState = 'visible'
 page.dispatchEvent(new Event('visibilitychange'))
 browser.dispatchEvent(new Event('focus'))
 browser.dispatchEvent(new Event('pageshow'))
 browser.dispatchEvent(new Event('online'))
 assert.equal(calls, 4)
 dispose()
 page.dispatchEvent(new Event('visibilitychange'))
 browser.dispatchEvent(new Event('focus'))
 browser.dispatchEvent(new Event('online'))
 assert.equal(calls, 4, 'unmounted effects must not leave refresh listeners behind')
})
