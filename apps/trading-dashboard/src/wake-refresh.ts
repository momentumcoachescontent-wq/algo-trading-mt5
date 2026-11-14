// Background timers are not a reliable resume signal. These events explicitly
// request a fresh read when the user returns to a visible page or network.
export function installWakeRefresh(
  page: EventTarget & { readonly visibilityState: string },
  browser: EventTarget,
  refresh: () => void,
): () => void {
  const wake = () => { if (page.visibilityState !== 'hidden') refresh() }
  const events = ['focus', 'online', 'pageshow'] as const
  page.addEventListener('visibilitychange', wake)
  for (const event of events) browser.addEventListener(event, wake)
  return () => {
    page.removeEventListener('visibilitychange', wake)
    for (const event of events) browser.removeEventListener(event, wake)
  }
}
