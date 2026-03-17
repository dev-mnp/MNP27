#!/bin/sh
# Helper script to build Docker image with proper environment variable handling

# Check if build args are provided
if [ -n "$VITE_SUPABASE_URL" ] && [ -n "$VITE_SUPABASE_ANON_KEY" ]; then
  # Build with build args
  docker build \
    --build-arg VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
    --build-arg VITE_SUPABASE_ANON_KEY="$VITE_SUPABASE_ANON_KEY" \
    "$@"
else
  # Build without build args (will use .env.production)
  docker build "$@"
fi

