import type { HTMLAttributes, TableHTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

function Table({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) { return <table className={cn('ui-table', className)} {...props} /> }
function TableHeader({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) { return <thead className={cn('ui-table-header', className)} {...props} /> }
function TableBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) { return <tbody className={cn('ui-table-body', className)} {...props} /> }
function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) { return <tr className={cn('ui-table-row', className)} {...props} /> }
function TableHead({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) { return <th className={cn('ui-table-head', className)} {...props} /> }
function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) { return <td className={cn('ui-table-cell', className)} {...props} /> }
function TableCaption({ className, ...props }: HTMLAttributes<HTMLTableCaptionElement>) { return <caption className={cn('ui-table-caption', className)} {...props} /> }

export { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow }
