import * as React from "react"

import { badgeVariants, type BadgeVariantProps } from "@/components/ui/badge-variants"
import { cn } from "@/lib/utils"

function Badge({
  className,
  tone = "neutral",
  ...props
}: React.ComponentProps<"span"> & BadgeVariantProps) {
  return (
    <span
      data-slot="badge"
      data-tone={tone}
      className={cn(badgeVariants({ tone }), className)}
      {...props}
    />
  )
}

export { Badge }
