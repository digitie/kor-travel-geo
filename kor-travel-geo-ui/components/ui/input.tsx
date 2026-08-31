import * as React from "react"

import { cn } from "@/lib/utils"

type InputProps = Omit<React.ComponentProps<"input">, "size"> & {
  /** map workbench의 두 컨트롤 높이: 기본 36px, 보조 30px. */
  size?: "default" | "sm"
}

function Input({ className, type, size = "default", ...props }: InputProps) {
  return (
    <input
      type={type}
      data-slot="input"
      data-size={size}
      className={cn(
        "w-full min-w-0 rounded-control border border-input bg-card px-3 text-text-primary transition-[color,background-color,border-color] duration-fast ease-out",
        "h-control text-sm data-[size=sm]:h-control-sm data-[size=sm]:px-2.5 data-[size=sm]:text-xs",
        "file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-xs file:font-medium file:text-text-primary placeholder:text-text-tertiary",
        "hover:bg-surface-subtle focus-visible:border-text-secondary focus-visible:bg-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        "disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-secondary read-only:cursor-default read-only:bg-surface-subtle read-only:text-text-secondary",
        "aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
export type { InputProps }
