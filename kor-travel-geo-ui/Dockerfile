FROM node:26.13.1-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS deps
RUN npm install --global npm@12.0.1

WORKDIR /app
COPY package.json package-lock.json .npmrc ./
COPY vendor ./vendor
RUN --mount=type=cache,id=kor-travel-web-npm-v2,target=/root/.npm,sharing=locked \
    npm ci --engine-strict --prefer-offline --no-audit --no-fund

FROM node:26.13.1-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS builder
RUN npm install --global npm@12.0.1

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN --mount=type=cache,id=kor-travel-geo-next-v2,target=/app/.next/cache,sharing=locked \
    npm run build
# 이 앱은 tracked public/이 없으므로 runtime static 디렉터리를 명시한다.
RUN mkdir -p /app/public

FROM node:26.13.1-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS runner
RUN npm install --global npm@12.0.1

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=12505
ENV HOME=/home/node \
    NPM_CONFIG_CACHE=/home/node/.npm \
    XDG_CACHE_HOME=/home/node/.cache

COPY --from=deps /app/package.json /app/package-lock.json /app/.npmrc ./
# UI 소스만 바뀌면 잠금 파일로 설치한 런타임 의존성 레이어를 재사용한다.
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.next ./.next

COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./
# 권한 조정은 새 이미지의 생성 산출물/cache에만 적용한다.
RUN mkdir -p /app/.next/cache /home/node/.npm /home/node/.cache \
    && chown node:node /app/.next/cache /home/node/.npm /home/node/.cache
USER node

EXPOSE 12505
CMD ["npm", "run", "start"]
