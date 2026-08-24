import type { InputHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn('ui-input', className)} {...props} />
}

export { Input }
