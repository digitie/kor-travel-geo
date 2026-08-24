/**
 * Header the pre-render gate uses to hand the requested path to the Node-side session guard.
 *
 * Lives in its own module so `proxy.ts` and `lib/session-guard.ts` (Node, imports
 * `next/headers`) can share the name without either pulling the other into its bundle.
 */
export const PATHNAME_HEADER = "x-ktg-pathname";
