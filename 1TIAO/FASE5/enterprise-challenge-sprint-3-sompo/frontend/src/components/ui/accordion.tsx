import * as AccordionPrimitive from '@radix-ui/react-accordion'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'

const Accordion = AccordionPrimitive.Root
const AccordionItem = AccordionPrimitive.Item

function AccordionTrigger({ className, children, ...props }: ComponentProps<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="ui-accordion-header">
      <AccordionPrimitive.Trigger className={cn('ui-accordion-trigger', className)} {...props}>{children}<span aria-hidden="true">⌄</span></AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  )
}

function AccordionContent({ className, children, ...props }: ComponentProps<typeof AccordionPrimitive.Content>) {
  return <AccordionPrimitive.Content className={cn('ui-accordion-content', className)} {...props}><div>{children}</div></AccordionPrimitive.Content>
}

export { Accordion, AccordionContent, AccordionItem, AccordionTrigger }
