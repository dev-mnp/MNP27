#!/bin/sh

# Replace environment variables in built files
echo "Configuring environment variables..."

# Create a script to replace environment variables in the built files
envsubst '${VITE_SUPABASE_URL} ${VITE_SUPABASE_ANON_KEY}' < /usr/share/nginx/html/index.html > /tmp/index.html
mv /tmp/index.html /usr/share/nginx/html/index.html

# Replace variables in JS files if they exist
find /usr/share/nginx/html -name "*.js" -exec sed -i "s|https://miftepyeoqfjyjeqffet.supabase.co|${VITE_SUPABASE_URL:-https://miftepyeoqfjyjeqffet.supabase.co}|g" {} \;
find /usr/share/nginx/html -name "*.js" -exec sed -i "s|eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1pZnRlcHllb3FmanlqZXFmZmV0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU3ODY5NzgsImV4cCI6MjA4MTM2Mjk3OH0.19nAsbnhQmTNrp6XqZ-iiUULMW8tnwSHIx5GbP5-cGY|${VITE_SUPABASE_ANON_KEY:-}|g" {} \;

echo "Environment configuration complete."

# Execute the main command
exec "$@"

