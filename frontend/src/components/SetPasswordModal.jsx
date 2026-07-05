import { useState } from 'react'
import { EmailAuthProvider, linkWithCredential, reauthenticateWithPopup } from 'firebase/auth'
import { auth, googleProvider } from '../firebase'

/**
 * Lets a user who signed up via Google add a password to that same
 * account, so they can also sign in with email + password afterwards.
 * Without this, an email already used for Google sign-in is a dead end:
 * sign-up rejects it as taken, and there's no password to reset.
 */
export default function SetPasswordModal({ onClose }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  async function linkPassword() {
    const credential = EmailAuthProvider.credential(auth.currentUser.email, password)
    await linkWithCredential(auth.currentUser, credential)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (password.length < 6) {
      setError('Password should be at least 6 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      await linkPassword()
      setSuccess(true)
    } catch (err) {
      console.error(err.code, err.message)
      if (err.code === 'auth/requires-recent-login') {
        // Linking a credential is security-sensitive — Firebase wants a
        // fresh sign-in first. Re-auth with the method they already
        // have (Google), then retry automatically.
        try {
          await reauthenticateWithPopup(auth.currentUser, googleProvider)
          await linkPassword()
          setSuccess(true)
        } catch (reauthErr) {
          console.error(reauthErr.code, reauthErr.message)
          setError(`Please try again — re-authentication failed (${reauthErr.code || 'unknown error'}).`)
        }
      } else if (err.code === 'auth/email-already-in-use' || err.code === 'auth/credential-already-in-use') {
        setError('A password is already set on this account.')
      } else if (err.code === 'auth/operation-not-allowed') {
        setError('Email/Password sign-in is not enabled for this project yet.')
      } else {
        setError(`Could not set password (${err.code || 'unknown error'}). Please try again.`)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        {success ? (
          <>
            <div className="modal-title">Password set</div>
            <p className="modal-text">
              You can now sign in with {auth.currentUser?.email} and this password, not just Google.
            </p>
            <button className="modal-btn" onClick={onClose} type="button">Done</button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="modal-title">Set a password</div>
            <p className="modal-text">
              Add a password to {auth.currentUser?.email} so you can sign in without Google too.
            </p>
            <input
              className="modal-input"
              type="password"
              placeholder="New password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={6}
              autoFocus
              required
            />
            <input
              className="modal-input"
              type="password"
              placeholder="Confirm password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              minLength={6}
              required
            />
            {error && <div className="modal-error">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="modal-btn-secondary" onClick={onClose}>Cancel</button>
              <button type="submit" className="modal-btn" disabled={loading}>
                {loading ? 'Saving…' : 'Set Password'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
