import { useState } from 'react'
import { createPortal } from 'react-dom'
import nustLogo from '../assets/nust-logo.png'

function groupSessionsByDate(sessions) {
  if (!Array.isArray(sessions)) return []

  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfYesterday = new Date(startOfToday)
  startOfYesterday.setDate(startOfYesterday.getDate() - 1)
  const startOfWeek = new Date(startOfToday)
  startOfWeek.setDate(startOfWeek.getDate() - 7)

  const buckets = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Previous 7 Days', items: [] },
    { label: 'Older', items: [] },
  ]

  for (const session of sessions) {
    const created = new Date(session.created_at)
    if (created >= startOfToday) buckets[0].items.push(session)
    else if (created >= startOfYesterday) buckets[1].items.push(session)
    else if (created >= startOfWeek) buckets[2].items.push(session)
    else buckets[3].items.push(session)
  }

  return buckets.filter((bucket) => bucket.items.length > 0)
}

export default function Sidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  user,
  onSignOut,
  onSetPassword,
  isOpen,
  onClose,
}) {
  const [confirmingSignOut, setConfirmingSignOut] = useState(false)
  const displayName = user?.displayName || user?.email || 'Account'
  const initial = displayName.charAt(0).toUpperCase()
  const hasPassword = user?.providerData?.some((p) => p.providerId === 'password')
  const groups = groupSessionsByDate(sessions)

  return (
    <div className={`sidebar ${isOpen ? 'open' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <img src={nustLogo} alt="NUST" className="logo-icon" />
          <span className="logo-name">UniBot</span>
        </div>
        <div className="sidebar-header-actions">
          <button className="new-chat-icon-btn" onClick={onNewChat} title="New chat">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
          <button className="sidebar-close-btn" onClick={onClose} title="Close menu">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div className="sidebar-body">
        {groups.map((group) => (
          <div key={group.label} className="session-group">
            <div className="sessions-label">{group.label}</div>
            <div className="session-list">
              {group.items.map((s) => (
                <div
                  key={s.id}
                  className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
                  onClick={() => onSelectSession(s.id)}
                >
                  <span className="session-title">{s.title || 'New Chat'}</span>
                  <button
                    className="delete-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDeleteSession(s.id)
                    }}
                    title="Delete"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {user && (
        <div className="sidebar-footer">
          <div className="user-info">
            {user.photoURL ? (
              <img className="user-avatar-img" src={user.photoURL} alt="" referrerPolicy="no-referrer" />
            ) : (
              <div className="user-avatar-fallback">{initial}</div>
            )}
            <span className="user-name" title={displayName}>{displayName}</span>
          </div>
          <div className="sidebar-footer-actions">
            {!hasPassword && (
              <button className="set-password-btn" onClick={onSetPassword} title="Set a password for this account">
                🔑
              </button>
            )}
            <button
              className="sign-out-btn"
              onClick={() => {
                setConfirmingSignOut(true)
                onClose?.()
              }}
              title="Sign out"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <path d="M16 17l5-5-5-5" />
                <path d="M21 12H9" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {confirmingSignOut && createPortal(
        // Rendered into document.body, not here — a position:fixed
        // element nested inside .sidebar would be confined to the
        // sidebar's own box once .sidebar gets a transform (for the
        // mobile slide-in/out drawer), since a transformed ancestor
        // becomes the containing block for fixed descendants. A portal
        // sidesteps that entirely.
        <div className="modal-overlay" onClick={() => setConfirmingSignOut(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Sign out?</div>
            <p className="modal-text">You'll need to sign in again to see your conversations.</p>
            <div className="modal-actions">
              <button className="modal-btn-secondary" onClick={() => setConfirmingSignOut(false)}>Cancel</button>
              <button
                className="modal-btn modal-btn-danger"
                onClick={() => {
                  setConfirmingSignOut(false)
                  onSignOut()
                }}
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}
