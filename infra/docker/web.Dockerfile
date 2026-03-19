FROM node:20-alpine

WORKDIR /app/services/web

COPY services/web/package.json ./
COPY services/web/package-lock.json ./
RUN npm ci

COPY services/web ./

RUN addgroup -S appgroup && adduser -S appuser -G appgroup && chown -R appuser /app
USER appuser

CMD ["npm", "run", "dev"]
