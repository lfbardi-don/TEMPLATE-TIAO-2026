import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('ui-skeleton', className)} {...props} />
}

export { Skeleton }
