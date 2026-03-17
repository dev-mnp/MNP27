# Multi-stage build for React app
FROM node:18-alpine AS builder

# Set working directory
WORKDIR /app

# Accept build arguments for Vite environment variables (optional - can override .env.production)
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code (includes .env.production if it exists)
COPY . .  

# If build args are provided, update/create .env.production with those values
# This ensures build args override .env.production file
# If build args are NOT provided, the existing .env.production will be used
RUN if [ -n "$VITE_SUPABASE_URL" ] || [ -n "$VITE_SUPABASE_ANON_KEY" ]; then \
      if [ -f .env.production ]; then \
        # Update existing .env.production, preserving other vars
        if [ -n "$VITE_SUPABASE_URL" ]; then \
          sed -i "s|^VITE_SUPABASE_URL=.*|VITE_SUPABASE_URL=$VITE_SUPABASE_URL|" .env.production || \
          echo "VITE_SUPABASE_URL=$VITE_SUPABASE_URL" >> .env.production; \
        fi && \
        if [ -n "$VITE_SUPABASE_ANON_KEY" ]; then \
          sed -i "s|^VITE_SUPABASE_ANON_KEY=.*|VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY|" .env.production || \
          echo "VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY" >> .env.production; \
        fi; \
      else \
        # Create .env.production from build args
        echo "VITE_SUPABASE_URL=${VITE_SUPABASE_URL:-}" > .env.production && \
        echo "VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY:-}" >> .env.production; \
      fi; \
    fi

# Build the application
# Vite will read from .env.production file
RUN npm run build

# Production stage with Nginx
FROM nginx:alpine AS production

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Expose port
EXPOSE 3000

# Start nginx
CMD ["nginx", "-g", "daemon off;"]

