FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY src ./src

ENV NODE_ENV=production
EXPOSE 8010

CMD ["node", "src/index.js"]
