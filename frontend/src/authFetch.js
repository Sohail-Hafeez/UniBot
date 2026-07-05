import { auth } from './firebase'

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

  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  })
}
