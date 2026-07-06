import { useState, useRef } from 'react'
import { authFetch } from '../authFetch'

export default function VoiceButton({ onTranscript, disabled }) {
  const [recording, setRecording] = useState(false)
  const [loading, setLoading] = useState(false)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const startTimeRef = useRef(null)

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunksRef.current = []

      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())

        if (chunksRef.current.length === 0) {
          console.warn('No audio chunks captured')
          return
        }

        setLoading(true)
        try {
          const blob = new Blob(chunksRef.current)
          const form = new FormData()
          form.append('file', blob, 'recording.webm')

          const res = await authFetch('/api/transcribe', { method: 'POST', body: form })
          if (!res.ok) throw new Error(`Server error ${res.status}`)

          const data = await res.json()
          if (data.text?.trim()) {
            onTranscript(data.text.trim())
          }
        } catch (err) {
          console.error('Transcription failed:', err)
        } finally {
          setLoading(false)
        }
      }

      recorder.start(200)
      startTimeRef.current = Date.now()
      setRecording(true)
    } catch (err) {
      console.error('Mic error:', err)
      alert('Microphone access denied. Please allow microphone permissions and reload.')
    }
  }

  function stopRecording() {
    const elapsed = Date.now() - (startTimeRef.current || 0)
    if (elapsed < 600) chunksRef.current = [] // discard — onstop sees empty → skips API call
    recorderRef.current?.stop()
    setRecording(false)
  }

  return (
    <button
      className={`voice-btn ${recording ? 'recording' : ''} ${loading ? 'loading' : ''}`}
      onClick={recording ? stopRecording : startRecording}
      disabled={disabled || loading}
      title={recording ? 'Click to stop & transcribe' : 'Click to start voice input (English / اردو)'}
      type="button"
    >
      {loading ? (
        <span className="voice-spinner" />
      ) : recording ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <rect x="5" y="5" width="14" height="14" rx="2" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </svg>
      )}
    </button>
  )
}
