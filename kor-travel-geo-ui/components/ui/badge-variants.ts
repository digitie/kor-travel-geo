import { cva, type VariantProps } from "class-variance-authority"

export const badgeVariants = cva(
  "inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1 rounded-control border border-transparent px-2 text-2xs font-medium leading-none whitespace-nowrap tabular-nums transition-[color,background-color,border-color] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3",
  {
    variants: {
      tone: {
        neutral: "border-border bg-muted text-muted-foreground",
        brand: "border-[color-mix(in_srgb,var(--brand)_30%,transparent)] bg-brand-tint text-[var(--brand-ink)]",
        ok: "border-[color-mix(in_srgb,var(--ok)_30%,transparent)] bg-[color-mix(in_srgb,var(--ok)_10%,white)] text-[var(--ok)]",
        warn: "border-[color-mix(in_srgb,var(--warn)_30%,transparent)] bg-[color-mix(in_srgb,var(--warn)_10%,white)] text-[var(--warn)]",
        error:
          "border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] text-[var(--danger)]",
        info: "border-[color-mix(in_srgb,var(--info)_30%,transparent)] bg-[color-mix(in_srgb,var(--info)_8%,white)] text-[var(--info)]",
      },
    },
    defaultVariants: {
      tone: "neutral",
    },
  }
)

export type BadgeVariantProps = VariantProps<typeof badgeVariants>
