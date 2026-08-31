"use client"

import * as React from "react"
import { Label as LabelPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function Label({
  className,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        "flex items-center gap-1.5 text-xs leading-snug font-medium text-text-secondary select-none group-data-[invalid=true]/field:text-destructive group-data-[disabled=true]/field:opacity-55 group-data-[disabled=true]:pointer-events-none peer-disabled:cursor-not-allowed peer-disabled:opacity-55",
        className
      )}
      {...props}
    />
  )
}

export { Label }
