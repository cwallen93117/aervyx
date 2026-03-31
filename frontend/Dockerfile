FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* /app/
RUN npm install

COPY . /app

CMD ["sh", "-lc", "npm run build && npm run start -- --hostname 0.0.0.0 --port 3000"]
