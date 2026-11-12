FROM node:22.23.1-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS deps
RUN npm install --global npm@12.0.1

WORKDIR /app
COPY package.json package-lock.json .npmrc ./
COPY vendor ./vendor
RUN npm ci --engine-strict

FROM node:22.23.1-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS builder
RUN npm install --global npm@12.0.1

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
# 이 앱은 tracked public/이 없으므로 runtime static 디렉터리를 명시한다.
RUN mkdir -p /app/public

FROM node:22.23.1-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS runner
RUN npm install --global npm@12.0.1

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=12505
ENV HOME=/home/node \
    NPM_CONFIG_CACHE=/home/node/.npm \
    XDG_CACHE_HOME=/home/node/.cache

COPY --from=builder /app/package.json /app/package-lock.json /app/.npmrc ./
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules

COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./
# 권한 조정은 새 이미지의 생성 산출물/cache에만 적용한다.
RUN mkdir -p /app/.next/cache /home/node/.npm /home/node/.cache \
    && chown node:node /app/.next/cache /home/node/.npm /home/node/.cache
USER node

EXPOSE 12505
CMD ["npm", "run", "start"]
