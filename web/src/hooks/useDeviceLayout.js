import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'cobot1-care-layout'

function readStoredLayout() {
  if (typeof window === 'undefined') return 'phone'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'phone' || stored === 'tablet') return stored
  return 'phone'
}

export function useDeviceLayout() {
  const [layout, setLayoutState] = useState(readStoredLayout)

  const setLayout = useCallback((mode) => {
    if (mode !== 'phone' && mode !== 'tablet') return
    setLayoutState(mode)
    localStorage.setItem(STORAGE_KEY, mode)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.careLayout = layout
    return () => {
      delete document.documentElement.dataset.careLayout
    }
  }, [layout])

  return {
    layout,
    setLayout,
    isTablet: layout === 'tablet',
  }
}
