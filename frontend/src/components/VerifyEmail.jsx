import { useState } from 'react'
import { sendEmailVerification, signOut } from 'firebase/auth'
import { auth } from '../firebase'

const RESEND_COOLDOWN_SECONDS = 30

/**
 * Blocks access to the app until the signed-in user has confirmed their
 * email address. Google accounts are already verified by Google and never
 * reach this screen — it only gates email/password sign-ups, which is
 * exactly the gap that let anyone register with an email they don't own.
 */
export default function VerifyEmail({ onVerified }) {
  const [sending, setSending] = useState(false)
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [cooldown, setCooldown] = useState(0)

  async function handleResend() {
    setError('')
    setMessage('')
    setSending(true)
    try {
      await sendEmailVerification(auth.currentUser)
      setMessage('Verification email sent — check your inbox (and spam folder).')
      setCooldown(RESEND_COOLDOWN_SECONDS)
      const timer = setInterval(() => {
        setCooldown((c) => {
          if (c <= 1) {
            clearInterval(timer)
            return 0
          }
          return c - 1
        })
      }, 1000)
    } catch (err) {
      setError(err.code === 'auth/too-many-requests'
        ? 'Too many requests — please wait a bit before trying again.'
        : 'Could not send verification email. Please try again.')
    } finally {
      setSending(false)
    }
  }

  async function handleCheckVerified() {
    setError('')
    setMessage('')
    setChecking(true)
    try {
      await auth.currentUser.reload()
      if (auth.currentUser.emailVerified) {
        // reload() refreshes the profile flag, but the cached ID token
        // still carries the old email_verified:false claim from before
        // verification — the backend checks the TOKEN's claim, not the
        // profile, so without forcing a fresh token every API call would
        // keep getting rejected. force=true fetches a new one now.
        await auth.currentUser.getIdToken(true)
        onVerified()
      } else {
        setError("Still not verified — click the link in the email first.")
      }
    } catch {
      setError('Could not check verification status. Please try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="verify-email-screen">
      <div className="verify-email-card">
        <div className="verify-email-icon">✉️</div>
        <div className="verify-email-title">Verify your email</div>
        <p className="verify-email-text">
          We sent a confirmation link to <strong>{auth.currentUser?.email}</strong>.
          Click it, then come back here and continue.
        </p>

        <button className="modal-btn" onClick={handleCheckVerified} disabled={checking}>
          {checking ? 'Checking…' : "I've verified — Continue"}
        </button>

        <button
          className="verify-email-resend"
          onClick={handleResend}
          disabled={sending || cooldown > 0}
          type="button"
        >
          {cooldown > 0 ? `Resend email (${cooldown}s)` : 'Resend verification email'}
        </button>

        {error && <div className="modal-error">{error}</div>}
        {message && <div className="verify-email-success">{message}</div>}

        <button className="verify-email-signout" onClick={() => signOut(auth)} type="button">
          Sign out
        </button>
      </div>
    </div>
  )
}
