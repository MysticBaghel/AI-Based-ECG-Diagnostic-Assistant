import { useState } from 'react'

import { Icon } from '@/shared/icons/Icon'

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      const area = document.createElement('textarea')
      area.value = value
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  return (
    <button type="button" className="button button--ghost button--sm" onClick={copy}>
      <Icon name={copied ? 'check' : 'copy'} size={15} />
      {copied ? 'Copied' : label}
    </button>
  )
}
