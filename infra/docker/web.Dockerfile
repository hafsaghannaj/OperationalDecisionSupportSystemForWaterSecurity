FROM node:20-alpine

WORKDIR /app/services/web

COPY services/web/package.json ./
RUN npm install

COPY services/web ./

RUN addgroup -S appgroup && adduser -S appuser -G appgroup && chown -R appuser /app
USER appuser

CMD ["npm", "run", "dev"]
