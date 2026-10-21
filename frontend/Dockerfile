# Build the React app, serve it with nginx, proxy /api to the backend.
FROM node:20-alpine AS build
WORKDIR /ui
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /ui/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# API_UPSTREAM is substituted at container start (e.g. http://bdx-api)
ENV API_UPSTREAM=http://backend:8000
EXPOSE 80
