# Multi-stage build for frontend
FROM node:20-alpine as base

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Development stage
FROM base as development

# Copy source code
COPY . .

# Expose port for development server
EXPOSE 3000

# Development command
CMD ["npm", "run", "dev"]

# Build stage
FROM base as builder

# Accept build argument for API URL
ARG VITE_API_URL=https://u2foru.site

# Set environment variable for build
ENV VITE_API_URL=${VITE_API_URL}

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine as production

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
