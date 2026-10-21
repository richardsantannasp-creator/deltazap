# Conector do WhatsApp por QR code. A sessão fica em /session (volume): sem ele você precisaria escanear o QR a cada reinício.
FROM node:20-slim
ENV NODE_ENV=production AUTH_DIR=/session/auth JID_FILE=/session/jids.json LINES_FILE=/session/lines.json GATEWAY_HOST=0.0.0.0
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY index.js ./
RUN mkdir -p /session && chown -R node /session /app
USER node
EXPOSE 3001
CMD ["node", "index.js"]
