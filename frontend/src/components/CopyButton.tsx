import { useState } from 'react'

export default function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={copy}
      className={`font-mono text-xs transition-colors duration-150 uppercase tracking-wider ${
        copied ? 'text-orange-400' : 'text-text-muted hover:text-white'
      } ${className ?? ''}`}
      aria-label="Copy to clipboard"
    >
      {copied ? 'copied!' : 'copy'}
    </button>
  )
}
