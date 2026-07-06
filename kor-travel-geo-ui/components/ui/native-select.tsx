import * as React from "react"
import { ChevronDownIcon } from "lucide-react"

import { cn } from "@/lib/utils"

/**
 * Styled native `<select>`. Radix Select is deliberately NOT used for admin
 * forms: unit tests drive selects with `fireEvent.change` + `getByRole("option")`
 * and live e2e locates them via `getByLabel`, both of which depend on native
 * select semantics.
 */
const NativeSelect = React.forwardRef<
  HTMLSelectElement,
  React.ComponentProps<"select">
>(function NativeSelect({ className, children, ...props }, ref) {
  return (
    <span
      data-slot="native-select-wrapper"
      className="relative inline-flex w-full"
    >
      <select
        ref={ref}
        data-slot="native-select"
        className={cn(
          "min-h-11 w-full min-w-0 appearance-none rounded-lg border border-input bg-transparent py-2 pr-9 pl-3 text-base transition-colors duration-[var(--duration-fast)] ease-[var(--ease-default)] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDownIcon
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </span>
  )
})

export { NativeSelect }
