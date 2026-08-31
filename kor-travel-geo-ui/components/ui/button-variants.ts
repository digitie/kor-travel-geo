import { cva, type VariantProps } from "class-variance-authority"

export const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-control border border-transparent bg-clip-padding font-medium whitespace-nowrap no-underline select-none transition-[color,background-color,border-color,box-shadow,transform] duration-fast ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:not-aria-[haspopup]:translate-y-px disabled:cursor-not-allowed aria-disabled:cursor-not-allowed aria-busy:cursor-progress aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-brand text-brand-foreground hover:bg-brand-hover active:bg-brand-hover disabled:bg-surface-muted disabled:text-text-primary aria-disabled:bg-surface-muted aria-disabled:text-text-primary",
        outline:
          "border-input bg-card text-text-primary hover:bg-surface-subtle active:bg-surface-muted aria-expanded:bg-surface-subtle aria-expanded:text-text-primary disabled:border-input disabled:bg-card aria-disabled:border-input aria-disabled:bg-card",
        secondary:
          "border-brand bg-brand-tint text-brand hover:border-brand-hover hover:text-brand-hover active:border-brand-hover active:text-brand-hover aria-expanded:border-brand aria-expanded:bg-brand-tint aria-expanded:text-brand disabled:border-brand disabled:text-brand aria-disabled:border-brand aria-disabled:text-brand",
        ghost:
          "text-text-secondary hover:bg-surface-subtle hover:text-text-primary active:bg-surface-muted aria-expanded:bg-surface-subtle aria-expanded:text-text-primary disabled:bg-transparent disabled:text-text-secondary aria-disabled:bg-transparent aria-disabled:text-text-secondary",
        destructive:
          "border-input bg-card text-destructive hover:border-destructive hover:bg-destructive-tint active:bg-destructive-tint aria-expanded:bg-destructive-tint disabled:border-input disabled:bg-card aria-disabled:border-input aria-disabled:bg-card",
        "destructive-solid":
          "bg-destructive text-brand-foreground hover:bg-text-primary hover:text-surface-page active:bg-text-primary active:text-surface-page disabled:bg-surface-muted disabled:text-text-primary aria-disabled:bg-surface-muted aria-disabled:text-text-primary",
        link: "text-brand underline-offset-4 hover:text-brand-hover hover:underline",
      },
      size: {
        default:
          "h-control gap-2 px-3.5 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        sm: "h-control-sm gap-1.5 px-2.5 text-xs has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3.5",
        xs: "h-control-sm gap-1.5 px-2 text-xs has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-control gap-2 px-3.5 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-control text-sm",
        "icon-sm": "size-control-sm text-xs [&_svg:not([class*='size-'])]:size-3.5",
        "icon-xs": "size-control-sm text-xs [&_svg:not([class*='size-'])]:size-3.5",
        "icon-lg": "size-control text-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export type ButtonVariantProps = VariantProps<typeof buttonVariants>
