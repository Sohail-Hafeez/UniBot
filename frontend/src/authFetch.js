import { auth } from './firebase'

// Backend base URL. Empty in dev (Vite's /api proxy in vite.config.js
// handles it) — set VITE_API_URL to the deployed backend's origin
// (e.g. https://your-app.up.railway.app) once frontend and backend are
// on different domains, otherwise every /api call 404s against the
// frontend's own host.
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * fetch() wrapper that attaches the signed-in user's Firebase ID token
 * as a Bearer Authorization header. All backend routes require this —
 * it's how the server knows which user's data to read/write.
 */
export async function authFetch(url, options = {}) {
  const user = auth.currentUser
  if (!user) {
    throw new Error('authFetch called with no signed-in user')
  }

  const token = await user.getIdToken()

  return fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  })
}
