import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import nustLogo from '../assets/nust-logo.png'

export default function MessageBubble({ role, content, isStreaming }) {
  const [copied, setCopied] = useState(false)
  const isAssistant = role === 'assistant'
  const showThinking = isAssistant && isStreaming && content.length === 0

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard permission denied — fail silently, nothing to recover
    }
  }

  return (
    <div className={`message-bubble ${role}`}>
      <div className={`avatar ${isAssistant ? 'ai-avatar' : 'user-avatar'}`}>
        {isAssistant ? <img src={nustLogo} alt="" className="avatar-logo" /> : 'U'}
      </div>
      <div className="bubble-col">
        <div className="bubble-content">
          {isAssistant ? (
            showThinking ? (
              <span className="thinking-dots"><span /><span /><span /></span>
            ) : (
              <>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                {isStreaming && <span className="cursor" />}
              </>
            )
          ) : (
            content
          )}
        </div>
        {isAssistant && !isStreaming && content && (
          <button className="copy-btn" onClick={handleCopy} title="Copy response" type="button">
            {copied ? '✓ Copied' : '⧉ Copy'}
          </button>
        )}
      </div>
    </div>
  )
}
