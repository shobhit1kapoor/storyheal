import React from 'react'
import ReactDOM from 'react-dom/client'
import { CacheProvider, Global, css } from '@emotion/react'
import createCache from '@emotion/cache'
import App from './App'
import hljsThemeCss from 'highlight.js/styles/github.css?inline'
import './i18n'

// Determine the target document for rendering.
// If we are running inside the controller iframe, render into the UI iframe's document.
function getTargetDocument(): Document {
  try {
    const isController = window.name === 'storyheal-controller-frame'
    if (isController && window.parent && 'frames' in window.parent) {
      const uiFrame = (window.parent as any).frames['storyheal-ui-frame'] as Window | undefined
      if (uiFrame && uiFrame.document) return uiFrame.document
    }
  } catch (e) {
    // cross-origin: fall back to current document
  }
  return document
}

const targetDoc = getTargetDocument()
const container = targetDoc.getElementById('storyheal-root') || targetDoc.getElementById('root')

if (!container) {
  // Create a fallback container when UI shell didn't provide one
  const el = targetDoc.createElement('div')
  el.id = 'storyheal-root'
  targetDoc.body.appendChild(el)
}

// Inject highlight.js theme CSS into the UI iframe head
if (!targetDoc.getElementById('hljs-theme')) {
  const style = targetDoc.createElement('style')
  style.id = 'hljs-theme'
  style.textContent = hljsThemeCss
  targetDoc.head.appendChild(style)
}

const emotionCache = createCache({ key: 'storyheal', container: targetDoc.head })

ReactDOM.createRoot((targetDoc.getElementById('storyheal-root') || targetDoc.getElementById('root')) as HTMLElement).render(
  <React.StrictMode>
    <CacheProvider value={emotionCache}>
      <Global styles={css`
        :root { --primary:#2f80ed; --bg:#ffffff; --text:#1f2937; --muted:#6b7280; }
        html, body, #storyheal-root, #root { height: 100%; overscroll-behavior: contain; }
        body { margin:0; background: var(--bg-primary, var(--bg)); color: var(--text-primary, var(--text)); font: 14px/1.4 system-ui,-apple-system, Segoe UI, Roboto, Helvetica, Arial; }
        * { box-sizing: border-box; }
      `} />
      <App />
    </CacheProvider>
  </React.StrictMode>
)

