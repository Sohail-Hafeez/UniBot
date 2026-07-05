import { useState, useEffect } from 'react'
import {
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendPasswordResetEmail,
  sendEmailVerification,
  updateProfile,
} from 'firebase/auth'
import { auth, googleProvider } from '../firebase'
import mcsLogo from '../assets/mcs-logo.png'
import './Login.css'

function GoogleIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 18 18">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" />
      <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z" />
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" />
    </svg>
  )
}

function friendlyError(code) {
  switch (code) {
    case 'auth/invalid-email':
      return 'That email address looks invalid.'
    case 'auth/user-not-found':
    case 'auth/wrong-password':
    case 'auth/invalid-credential':
      return 'Incorrect email or password.'
    case 'auth/email-already-in-use':
      return 'An account with that email already exists. If you originally signed up with Google, log in with Google below — you can add a password from the sidebar afterwards.'
    case 'auth/weak-password':
      return 'Password should be at least 6 characters.'
    case 'auth/popup-closed-by-user':
      return null // user cancelled — not an error worth showing
    default:
      return null // unrecognized — caller shows the raw code instead of guessing
  }
}

function describeError(err) {
  console.error(err.code, err.message)
  return friendlyError(err.code) || `Something went wrong (${err.code || 'unknown error'}). Please try again.`
}

export default function Login() {
  const [mode, setMode] = useState('signin') // 'signin' | 'signup'
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [resetMessage, setResetMessage] = useState('')
  const [loading, setLoading] = useState(false)

  // Auto-dismiss the error/success banner after a few seconds instead of
  // leaving it on screen until the next action clears it.
  useEffect(() => {
    if (!error && !resetMessage) return
    const timer = setTimeout(() => {
      setError('')
      setResetMessage('')
    }, 3500)
    return () => clearTimeout(timer)
  }, [error, resetMessage])

  function switchMode(next) {
    setMode(next)
    setError('')
    setResetMessage('')
  }

  async function handleGoogle() {
    setError('')
    setResetMessage('')
    setLoading(true)
    try {
      await signInWithPopup(auth, googleProvider)
    } catch (err) {
      if (err.code !== 'auth/popup-closed-by-user') setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setResetMessage('')
    setLoading(true)
    try {
      if (mode === 'signin') {
        await signInWithEmailAndPassword(auth, email, password)
      } else {
        const credential = await createUserWithEmailAndPassword(auth, email, password)
        if (fullName.trim()) {
          await updateProfile(credential.user, { displayName: fullName.trim() })
        }
        await sendEmailVerification(credential.user)
      }
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleForgotPassword() {
    setError('')
    setResetMessage('')
    if (!email.trim()) {
      setError('Enter your email above first, then tap "Forgot password?"')
      return
    }
    setLoading(true)
    try {
      await sendPasswordResetEmail(auth, email.trim())
      setResetMessage(
        "If that email has a password set, we've sent a reset link. " +
        "(Signed up with Google? There's no password to reset — use \"Continue with Google\" instead.)"
      )
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="ig-page">
      <div className="ig-container">
        <div className="ig-box">
          <div className={`ig-crest-wrap ${mode === 'signup' ? 'ig-crest-wrap-cropped' : ''}`}>
            <img src={mcsLogo} alt="MCS" className="ig-crest ig-crest-standalone" />
            {mode === 'signup' && (
              <div className="ig-tagline-overlay">Sign up to chat with UniBot</div>
            )}
          </div>

          <form className="ig-form" onSubmit={handleSubmit} autoComplete="off">
            {mode === 'signup' && (
              <div className="ig-field">
                <input
                  type="text"
                  placeholder=" "
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  autoComplete="name"
                />
                <label>Full Name</label>
              </div>
            )}

            <div className="ig-field">
              <input
                type="email"
                placeholder=" "
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
                readOnly
                onFocus={(e) => e.target.removeAttribute('readonly')}
                required
              />
              <label>Email</label>
            </div>

            <div className="ig-field">
              <input
                type="password"
                placeholder=" "
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="off"
                readOnly
                onFocus={(e) => e.target.removeAttribute('readonly')}
                minLength={6}
                required
              />
              <label>Password</label>
            </div>

            <button className="ig-submit-btn" type="submit" disabled={loading || !email || !password}>
              {loading && <span className="ig-spinner" />}
              {mode === 'signin' ? 'Log In' : 'Sign Up'}
            </button>
          </form>

          <div className="ig-divider"><span>OR</span></div>

          <button className="ig-google-link" onClick={handleGoogle} disabled={loading} type="button">
            <span className="ig-google-icon"><GoogleIcon /></span> Log in with Google
          </button>

          {mode === 'signin' && (
            <button className="ig-forgot-link" onClick={handleForgotPassword} disabled={loading} type="button">
              Forgot password?
            </button>
          )}

          {error && <div className="ig-message error">⚠ {error}</div>}
          {resetMessage && <div className="ig-message success">✓ {resetMessage}</div>}
        </div>

        <div className="ig-signup-box">
          {mode === 'signin' ? (
            <>Don't have an account?{' '}
              <button type="button" onClick={() => switchMode('signup')}>Sign up</button>
            </>
          ) : (
            <>Have an account?{' '}
              <button type="button" onClick={() => switchMode('signin')}>Log in</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
