FROM node:22.23.1-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
# postinstall (scripts/patch-vworld-map-web-esm-imports.mjs) needs its own file present
# before `npx --yes npm@12.0.1 ci` runs its lifecycle scripts — the rest of the source only lands later,
# in the builder stage's `COPY . .`.
COPY scripts ./scripts
COPY vendor ./vendor
RUN npx --yes npm@12.0.1 ci

FROM node:22.23.1-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22.23.1-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=12505

COPY --from=builder /app/package.json /app/package-lock.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 12505
CMD ["npm", "run", "start"]
