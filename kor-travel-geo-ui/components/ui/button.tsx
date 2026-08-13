import * as React from "react"
import { Slot } from "radix-ui"

import { buttonVariants, type ButtonVariantProps } from "@/components/ui/button-variants"
import { cn } from "@/lib/utils"

// React 18에서는 radix Trigger asChild가 ref를 넘기므로 forwardRef가 필수다
// (함수 컴포넌트 ref 경고 + 포커스 복귀 무력화 방지).
const Button = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<"button"> &
    ButtonVariantProps & {
      asChild?: boolean
    }
>(function Button(
  { className, variant = "default", size = "default", asChild = false, ...props },
  ref
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
})

export { Button }
