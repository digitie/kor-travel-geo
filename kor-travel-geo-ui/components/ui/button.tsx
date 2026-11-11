import * as React from "react"
import { Slot } from "radix-ui"

import { buttonVariants, type ButtonVariantProps } from "@/components/ui/button-variants"
import { cn } from "@/lib/utils"

// React 19의 ref prop을 Radix Trigger와 실제 버튼에 그대로 전달한다.
function Button(
  { className, variant = "default", size = "default", asChild = false, ref, ...props }:
    React.ComponentProps<"button"> & ButtonVariantProps & { asChild?: boolean }
) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      ref={ref}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button }
