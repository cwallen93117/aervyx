FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* /app/
RUN npm install

COPY . /app

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]