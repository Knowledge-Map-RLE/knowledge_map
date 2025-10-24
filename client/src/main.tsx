import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/index.css'
import './styles/fonts.css'
import App from './App.tsx'

if (import.meta.env.DEV && typeof window !== 'undefined') {
  const devtools = (window as any).__REACT_DEVTOOLS_GLOBAL_HOOK__ as {
    renderers?: Map<unknown, { version?: string }>
    registerRenderer?: (...args: any[]) => any
    __KM_VERSION_PATCHED__?: boolean
  } | undefined

  if (devtools && !devtools.__KM_VERSION_PATCHED__) {
    const ensureVersion = (renderer: { version?: string } | undefined) => {
      if (renderer && (!renderer.version || renderer.version.trim() === '')) {
        renderer.version = '0.0.0'
      }
      return renderer
    }

    if (devtools.renderers && typeof devtools.renderers.forEach === 'function') {
      devtools.renderers.forEach(renderer => ensureVersion(renderer))
    }

    if (typeof devtools.registerRenderer === 'function') {
      const originalRegister = devtools.registerRenderer
      devtools.registerRenderer = function patchedRegisterRenderer(...args: any[]) {
        if (args.length >= 2) {
          args[1] = ensureVersion(args[1])
        } else if (args.length === 1) {
          args[0] = ensureVersion(args[0])
        }
        return originalRegister.apply(this, args)
      }
    }

    devtools.__KM_VERSION_PATCHED__ = true
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
