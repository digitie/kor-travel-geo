import * as React from "react"
import { ChevronDownIcon } from "lucide-react"

import { cn } from "@/lib/utils"

/**
 * Styled native `<select>`. Radix Select is deliberately NOT used for admin
 * forms: unit tests drive selects with `fireEvent.change` + `getByRole("option")`
 * and live e2e locates them via `getByLabel`, both of which depend on native
 * select semantics.
 */
type NativeSelectProps = Omit<React.ComponentPropsWithRef<"select">, "size"> & {
  /** map workbench의 두 컨트롤 높이: 기본 36px, 보조 30px. */
  size?: "default" | "sm"
}

const NativeSelect = React.forwardRef<HTMLSelectElement, NativeSelectProps>(
  function NativeSelect({ className, children, size = "default", ...props }, ref) {
    return (
      <div
        data-slot="native-select-wrapper"
        className="group/native-select relative inline-flex w-full"
        data-size={size}
      >
        <select
          ref={ref}
          data-slot="native-select"
          data-size={size}
          className={cn(
            "w-full min-w-0 appearance-none rounded-control border border-input bg-card pr-9 pl-3 text-text-primary transition-[color,background-color,border-color] duration-fast ease-out",
            "h-control text-sm data-[size=sm]:h-control-sm data-[size=sm]:pl-2.5 data-[size=sm]:text-xs",
            "hover:bg-surface-subtle focus-visible:border-text-secondary focus-visible:bg-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
            "disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-secondary aria-invalid:border-destructive",
            className
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDownIcon
          aria-hidden="true"
          data-slot="native-select-icon"
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-text-secondary group-data-[size=sm]/native-select:right-2.5 group-data-[size=sm]/native-select:size-3.5"
        />
      </div>
    )
  }
)

export { NativeSelect }
export type { NativeSelectProps }
