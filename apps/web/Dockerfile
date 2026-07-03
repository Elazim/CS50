FROM node:22-alpine AS build

WORKDIR /srv
RUN corepack enable
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/client ./packages/client
COPY apps/web/package.json ./apps/web/
RUN pnpm install --frozen-lockfile
COPY apps/web ./apps/web
RUN pnpm --filter web build

FROM node:22-alpine
WORKDIR /srv
RUN corepack enable
COPY --from=build /srv ./
EXPOSE 3000
CMD ["pnpm", "--filter", "web", "start"]
