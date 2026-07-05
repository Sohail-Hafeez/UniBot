import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import nustLogo from '../assets/nust-logo.png'

const SUGGESTIONS = [
  { icon: '🏠', label: 'Hostel', sub: 'What are the hostel fees at NUST?' },
  { icon: '🎓', label: 'Admissions', sub: 'What documents do I need for admission?' },
  { icon: '💰', label: 'Scholarships', sub: 'What scholarships are available?' },
  { icon: '📚', label: 'Registration', sub: 'How do I register for courses?' },
]

// How close to the bottom (in px) still counts as "at the bottom" —
// used only to *resume* auto-follow once the user scrolls back down.
const NEAR_BOTTOM_THRESHOLD = 40

// Keys that indicate the user wants to look away from the bottom.
const INTERRUPT_KEYS = new Set(['ArrowUp', 'PageUp', 'Home'])

export default function ChatWindow({ messages, isStreaming, onSuggestion }) {
  const containerRef = useRef(null)
  const stickToBottomRef = useRef(true)

  // Only genuine user input (wheel-up, arrow/page-up keys) cancels
  // auto-follow. We deliberately do NOT use the generic `scroll` event
  // for this: our own smooth auto-scroll fires `scroll` events too while
  // animating, and treating those as "user interrupted" would cancel
  // the animation mid-flight — which is what caused the bouncing before.
  const handleWheel = (e) => {
    if (e.deltaY < 0) stickToBottomRef.current = false
  }

  const handleKeyDown = (e) => {
    if (INTERRUPT_KEYS.has(e.key)) stickToBottomRef.current = false
  }

  // Scrolling back down to the bottom (by any means) always resumes
  // auto-follow — this direction of the check is safe to base on the
  // generic `scroll` event since "reached the bottom" is unambiguous.
  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distanceFromBottom < NEAR_BOTTOM_THRESHOLD) stickToBottomRef.current = true
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el || !stickToBottomRef.current) return
    el.scrollTop = el.scrollHeight
  }, [messages])

  // Window-level, not on the container: during streaming the textarea is
  // disabled and can't hold focus, so a container-only listener would
  // miss the very key presses we need to catch.
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  if (messages.length === 0) {
    return (
      <div className="chat-window">
        <div className="empty-state">
          <div className="empty-hero">
            <img src={nustLogo} alt="NUST" className="empty-logo" />
            <div className="empty-title">Hi, I'm UniBot</div>
            <div className="empty-subtitle">Your NUST &amp; MCS assistant — ask about admissions, hostel, fees, scholarships, and more.</div>
          </div>
          <div className="suggestion-grid">
            {SUGGESTIONS.map((s, i) => (
              <button
                key={s.label}
                className="suggestion-card"
                style={{ animationDelay: `${i * 60}ms` }}
                onClick={() => onSuggestion?.(s.sub)}
              >
                <span className="suggestion-icon-chip">{s.icon}</span>
                <span className="suggestion-text">
                  <span className="suggestion-label">{s.label}</span>
                  <span className="suggestion-sub">{s.sub}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-window" ref={containerRef} onScroll={handleScroll} onWheel={handleWheel}>
      {messages.map((msg, i) => (
        <div key={i} className="message-row">
          <MessageBubble
            role={msg.role}
            content={msg.content}
            isStreaming={isStreaming && i === messages.length - 1 && msg.role === 'assistant'}
          />
        </div>
      ))}
    </div>
  )
}
