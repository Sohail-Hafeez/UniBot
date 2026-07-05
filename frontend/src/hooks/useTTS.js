import { useRef, useCallback } from 'react'
import { authFetch } from '../authFetch'

// Sentence boundary: ends with . ! ? ۔ ؟ followed by space or end of string
const SENTENCE_END = /^([\s\S]*?[.!?۔؟]+)(\s|$)/

export function useTTS() {
  const enabled = useRef(false)
  const queue = useRef([])       // list of ObjectURLs ready to play
  const playing = useRef(false)
  const buffer = useRef('')      // token accumulation buffer
  const fetching = useRef(0)     // in-flight TTS requests

  const playNext = useCallback(() => {
    if (queue.current.length === 0) {
      playing.current = false
      return
    }
    playing.current = true
    const url = queue.current.shift()
    const audio = new Audio(url)
    audio.onended = () => {
      URL.revokeObjectURL(url)
      playNext()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      playNext()
    }
    audio.play().catch(() => playNext())
  }, [])

  const fetchAndEnqueue = useCallback(async (text) => {
    if (!text.trim()) return
    fetching.current += 1
    try {
      const res = await authFetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      queue.current.push(url)
      if (!playing.current) playNext()
    } catch (err) {
      console.error('TTS error:', err)
    } finally {
      fetching.current -= 1
    }
  }, [playNext])

  // Feed one streaming token — flushes on sentence boundary
  const feedToken = useCallback((token) => {
    if (!enabled.current) return
    buffer.current += token
    const match = buffer.current.match(SENTENCE_END)
    if (match) {
      const sentence = match[1]
      buffer.current = buffer.current.slice(match[0].length)
      fetchAndEnqueue(sentence)
    }
  }, [fetchAndEnqueue])

  // Call when the stream ends — flushes any remaining buffer
  const flush = useCallback(() => {
    if (!enabled.current) return
    const remaining = buffer.current.trim()
    if (remaining) {
      fetchAndEnqueue(remaining)
      buffer.current = ''
    }
  }, [fetchAndEnqueue])

  const stop = useCallback(() => {
    queue.current = []
    playing.current = false
    buffer.current = ''
  }, [])

  const setEnabled = useCallback((val) => {
    enabled.current = val
    if (!val) stop()
  }, [stop])

  const isEnabled = useCallback(() => enabled.current, [])

  return { feedToken, flush, stop, setEnabled, isEnabled }
}
