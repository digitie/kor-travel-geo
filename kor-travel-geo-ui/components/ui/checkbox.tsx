"use client"

import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"
import { CheckIcon } from "lucide-react"

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative flex size-4 shrink-0 items-center justify-center rounded-control border border-input bg-card text-brand-foreground transition-[color,background-color,border-color] duration-fast ease-out",
        "after:absolute after:-inset-2 after:content-[''] data-[unchecked]:hover:border-text-secondary data-[unchecked]:hover:bg-surface-subtle",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:border-input disabled:bg-surface-subtle disabled:text-text-secondary aria-invalid:border-destructive",
        "data-[state=checked]:border-brand data-[state=checked]:bg-brand data-[state=checked]:text-brand-foreground data-[state=checked]:hover:border-brand-hover data-[state=checked]:hover:bg-brand-hover",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none [&>svg]:size-3.5"
      >
        <CheckIcon
        />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
