import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

type AlertProps = HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'destructive' }

function Alert({ className, variant = 'default', ...props }: AlertProps) {
  return <div role="alert" className={cn('ui-alert', variant === 'destructive' && 'ui-alert-danger', className)} {...props} />
}

function AlertTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn('ui-alert-title', className)} {...props} />
}

function AlertDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('ui-alert-description', className)} {...props} />
}

export { Alert, AlertDescription, AlertTitle }
