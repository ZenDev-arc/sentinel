import CopyButton from './CopyButton'

interface Props {
  code: string
  language?: string
  filename?: string
}

export default function CodeBlock({ code, language = 'bash', filename }: Props) {
  return (
    <div className="border border-bg-border overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-bg-surface border-b border-bg-border">
        <span className="text-text-muted text-xs font-mono">
          {filename ?? language}
        </span>
        <CopyButton text={code} />
      </div>
      <pre className="bg-bg-base p-5 overflow-x-auto">
        <code className="font-mono text-sm text-text-primary leading-relaxed">{code}</code>
      </pre>
    </div>
  )
}
