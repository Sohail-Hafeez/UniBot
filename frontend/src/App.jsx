import { useState, useEffect } from 'react'
import { onAuthStateChanged, signOut } from 'firebase/auth'
import { auth } from './firebase'
import { authFetch } from './authFetch'
import Login from './components/Login'
import VerifyEmail from './components/VerifyEmail'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'
import SetPasswordModal from './components/SetPasswordModal'
import { useTTS } from './hooks/useTTS'

// authFetch + res.ok check + JSON parse, all in one place. A failed
// response (4xx/5xx) previously got passed straight to setState as if it
// were valid data — e.g. a 403 error body has no `.length`, and handing
// that to a session list that expects an array crashes the whole render
// tree. This throws instead, so callers can show a message and recover.
async function fetchJSON(url, options) {
  const res = await authFetch(url, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export default function App() {
  const [user, setUser] = useState(null)
  const [emailVerified, setEmailVerified] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [showSetPassword, setShowSetPassword] = useState(false)
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [ttsEnabled, setTtsEnabled] = useState(false)
  const [apiError, setApiError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const tts = useTTS()

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (nextUser) => {
      // Wipe any previous user's chat state immediately so there's never
      // a flash of one account's sessions while another is signed in.
      setSessions([])
      setActiveSessionId(null)
      setMessages([])

      if (nextUser?.emailVerified) {
        // A restored session can have emailVerified:true at the profile
        // level while the cached ID token still carries the OLD
        // email_verified:false claim from before verification (e.g. the
        // token was cached in an earlier tab, that tab closed before a
        // fresh token was ever fetched, and this page load just restores
        // the stale one). The backend checks the token's claim, not the
        // profile — so every API call would 403 until something forces a
        // refresh. Do it here, once per session-start, before initApp()
        // can ever fire and hit that mismatch.
        try {
          await nextUser.getIdToken(true)
        } catch (err) {
          console.error('Failed to refresh ID token:', err)
        }
      }

      setUser(nextUser)
      setEmailVerified(nextUser?.emailVerified ?? false)
      setAuthChecked(true)
    })
    return unsubscribe
  }, [])

  // Only call the API once the email is verified — the backend now
  // rejects unverified accounts outright, so calling any earlier would
  // just fail.
  useEffect(() => {
    if (user && emailVerified) {
      initApp().catch((err) => {
        console.error('Failed to initialise app:', err)
        setApiError(err.message || 'Could not load your conversations.')
      })
    }
  }, [user, emailVerified])

  async function initApp() {
    const data = await fetchJSON('/api/conversations')
    setSessions(data)
    if (data.length > 0) {
      await loadSession(data[0].id)
    } else {
      await startNewChat()
    }
  }

  async function loadSessions() {
    try {
      setSessions(await fetchJSON('/api/conversations'))
    } catch (err) {
      console.error('Failed to load sessions:', err)
      setApiError(err.message || 'Could not load your conversations.')
    }
  }

  async function startNewChat() {
    try {
      const { session_id } = await fetchJSON('/api/conversations', { method: 'POST' })
      setActiveSessionId(session_id)
      setMessages([])
      await loadSessions()
    } catch (err) {
      console.error('Failed to start new chat:', err)
      setApiError(err.message || 'Could not start a new chat.')
    }
  }

  async function loadSession(sessionId) {
    setActiveSessionId(sessionId)
    try {
      const { messages: msgs } = await fetchJSON(`/api/conversations/${sessionId}`)
      setMessages(msgs)
    } catch (err) {
      console.error('Failed to load session:', err)
      setApiError(err.message || 'Could not load that conversation.')
    }
  }

  function toggleTTS() {
    const next = !ttsEnabled
    setTtsEnabled(next)
    tts.setEnabled(next)
    if (!next) tts.stop()
  }

  async function sendMessage(text) {
    tts.stop() // stop any previous TTS if user sends a new message
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '' },
    ])
    setIsStreaming(true)

    try {
      const res = await authFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSessionId, message: text }),
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') {
            tts.flush()           // speak any remaining buffer
            setIsStreaming(false)
            loadSessions()
            break
          }
          try {
            const { token } = JSON.parse(payload)
            tts.feedToken(token)  // sentence-level TTS pipeline
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              updated[updated.length - 1] = { ...last, content: last.content + token }
              return updated
            })
          } catch {
            // partial SSE chunk — skip
          }
        }
      }
    } catch (err) {
      console.error('Stream error:', err)
      setIsStreaming(false)
    }
  }

  async function deleteSession(sessionId) {
    try {
      await fetchJSON(`/api/conversations/${sessionId}`, { method: 'DELETE' })
      if (sessionId === activeSessionId) {
        await startNewChat()
      } else {
        await loadSessions()
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
      setApiError(err.message || 'Could not delete that conversation.')
    }
  }

  if (!authChecked) {
    return <div className="auth-loading" />
  }

  if (!user) {
    return <Login />
  }

  if (!emailVerified) {
    return <VerifyEmail onVerified={() => setEmailVerified(true)} />
  }

  return (
    <div className="app">
      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />}
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewChat={() => { startNewChat(); setSidebarOpen(false) }}
        onSelectSession={(id) => { loadSession(id); setSidebarOpen(false) }}
        onDeleteSession={deleteSession}
        user={user}
        onSignOut={() => signOut(auth)}
        onSetPassword={() => setShowSetPassword(true)}
      />
      <div className="main">
        <div className="mobile-topbar">
          <button className="mobile-menu-btn" onClick={() => setSidebarOpen(true)} title="Menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12h18M3 6h18M3 18h18" />
            </svg>
          </button>
          <span className="mobile-topbar-title">UniBot</span>
        </div>
        {apiError && (
          <div className="api-error-banner">
            {apiError}
            <button onClick={() => setApiError('')} title="Dismiss">✕</button>
          </div>
        )}
        <ChatWindow messages={messages} isStreaming={isStreaming} onSuggestion={sendMessage} />
        <InputBar
          onSend={sendMessage}
          disabled={isStreaming}
          ttsEnabled={ttsEnabled}
          onToggleTTS={toggleTTS}
        />
      </div>
      {showSetPassword && <SetPasswordModal onClose={() => setShowSetPassword(false)} />}
    </div>
  )
}
