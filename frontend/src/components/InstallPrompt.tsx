import { useState, useEffect } from 'react'

export default function InstallPrompt() {
  const [showIOSPrompt, setShowIOSPrompt] = useState(false)
  const [showNotifPrompt, setShowNotifPrompt] = useState(false)
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null)

  useEffect(() => {
    // Check if already installed as PWA
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
      || (navigator as any).standalone === true
    const dismissed = localStorage.getItem('install_prompt_dismissed')

    if (isStandalone || dismissed) return

    // iOS detection — no native install prompt, need manual instructions
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
    if (isIOS) {
      setShowIOSPrompt(true)
      return
    }

    // Android/desktop — listen for beforeinstallprompt
    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  useEffect(() => {
    // Check if notifications are supported but not yet granted
    if ('Notification' in window && Notification.permission === 'default') {
      const notifDismissed = localStorage.getItem('notif_prompt_dismissed')
      if (!notifDismissed) {
        // Show after a short delay so it doesn't overwhelm
        const timer = setTimeout(() => setShowNotifPrompt(true), 3000)
        return () => clearTimeout(timer)
      }
    }
  }, [])

  const handleInstallAndroid = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt()
      await deferredPrompt.userChoice
      setDeferredPrompt(null)
    }
  }

  const handleEnableNotifications = async () => {
    try {
      const permission = await Notification.requestPermission()
      if (permission === 'granted') {
        // Re-trigger push subscription
        const { subscribeToPush } = await import('../App')
        subscribeToPush()
      }
    } catch (err) {
      console.log('Notification permission failed:', err)
    }
    setShowNotifPrompt(false)
    localStorage.setItem('notif_prompt_dismissed', '1')
  }

  const dismiss = (type: 'install' | 'notif') => {
    if (type === 'install') {
      setShowIOSPrompt(false)
      setDeferredPrompt(null)
      localStorage.setItem('install_prompt_dismissed', '1')
    } else {
      setShowNotifPrompt(false)
      localStorage.setItem('notif_prompt_dismissed', '1')
    }
  }

  return (
    <>
      {/* iOS Install Prompt */}
      {showIOSPrompt && (
        <div className="fixed bottom-20 md:bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 bg-surface border border-border rounded-2xl shadow-elevated p-4 z-50">
          <div className="flex items-start gap-3">
            <span className="text-2xl">+</span>
            <div className="flex-1">
              <p className="text-primary text-sm font-semibold">Install Planner</p>
              <p className="text-secondary text-xs mt-1">
                Tap the <strong>Share</strong> button in Safari, then <strong>"Add to Home Screen"</strong> for the full app experience with notifications.
              </p>
            </div>
            <button onClick={() => dismiss('install')} className="text-muted hover:text-primary text-sm">
              {'\u2715'}
            </button>
          </div>
        </div>
      )}

      {/* Android Install Prompt */}
      {deferredPrompt && (
        <div className="fixed bottom-20 md:bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 bg-surface border border-border rounded-2xl shadow-elevated p-4 z-50">
          <div className="flex items-start gap-3">
            <span className="text-2xl flex-shrink-0">+</span>
            <div className="flex-1">
              <p className="text-primary text-sm font-semibold">Install Planner</p>
              <p className="text-secondary text-xs mt-1">Add to your home screen for quick access and notifications.</p>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={handleInstallAndroid}
                  className="px-3 py-1.5 bg-accent text-white text-xs font-medium rounded-lg"
                >
                  Install
                </button>
                <button
                  onClick={() => dismiss('install')}
                  className="px-3 py-1.5 text-secondary text-xs"
                >
                  Not now
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Notification Permission Prompt */}
      {showNotifPrompt && !showIOSPrompt && !deferredPrompt && (
        <div className="fixed bottom-20 md:bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 bg-surface border border-border rounded-2xl shadow-elevated p-4 z-50">
          <div className="flex items-start gap-3">
            <span className="text-2xl flex-shrink-0">{'\u{1F514}'}</span>
            <div className="flex-1">
              <p className="text-primary text-sm font-semibold">Enable Notifications</p>
              <p className="text-secondary text-xs mt-1">Get reminders for schedule blocks, deadlines, and important emails.</p>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={handleEnableNotifications}
                  className="px-3 py-1.5 bg-accent text-white text-xs font-medium rounded-lg"
                >
                  Enable
                </button>
                <button
                  onClick={() => dismiss('notif')}
                  className="px-3 py-1.5 text-secondary text-xs"
                >
                  Later
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
