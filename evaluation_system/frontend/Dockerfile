FROM node:22-alpine AS build

ARG NPM_REGISTRY_URL=https://registry.npmjs.org

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY_URL}"

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist/ /usr/share/nginx/html/

EXPOSE 80
