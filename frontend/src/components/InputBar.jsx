import { useState, useRef, useEffect, useLayoutEffect } from 'react'
import VoiceButton from './VoiceButton'

export default function InputBar({ onSend, disabled, ttsEnabled, onToggleTTS }) {
  const [text, setText] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    if (!disabled) textareaRef.current?.focus()
  }, [disabled])

  // Resize textarea on every text change, synchronously before paint
  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [text])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleTranscript = (transcript) => {
    setText((prev) => prev ? `${prev} ${transcript}` : transcript)
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  return (
    <div className="input-bar">
      <div className="input-wrapper">
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Message UniBot..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          className={`tts-btn ${ttsEnabled ? 'active' : ''}`}
          onClick={onToggleTTS}
          title={ttsEnabled ? 'Mute voice responses' : 'Enable voice responses'}
          type="button"
        >
          {ttsEnabled ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M3 10v4h4l5 5V5L7 10H3z" />
              <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v8.06c1.48-.74 2.5-2.26 2.5-4.03z" />
              <path d="M14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M3 10v4h4l5 5V5L7 10H3z" />
              <path d="M19 6.41 17.59 5 15 7.59 12.41 5 11 6.41 13.59 9 11 11.59 12.41 13 15 10.41 17.59 13 19 11.59 16.41 9z" />
            </svg>
          )}
        </button>
        <button className="send-btn" onClick={submit} disabled={disabled || !text.trim()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 4l-8 8h5v8h6v-8h5z" />
          </svg>
        </button>
        <VoiceButton onTranscript={handleTranscript} disabled={disabled} />
      </div>
    </div>
  )
}
