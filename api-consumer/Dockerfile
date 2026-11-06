FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY src ./src

ENV NODE_ENV=production
EXPOSE 8010

USER node

CMD ["node", "src/index.js"]
