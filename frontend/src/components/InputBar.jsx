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
          {ttsEnabled ? '🔊' : '🔇'}
        </button>
        <button className="send-btn" onClick={submit} disabled={disabled || !text.trim()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
        <VoiceButton onTranscript={handleTranscript} disabled={disabled} />
      </div>
    </div>
  )
}
