# Data Entry App - Docker Build and GCR Push Guide

This guide covers building the Docker image locally and pushing it to Google Container Registry (GCR).

## 📋 Prerequisites

- Docker installed and running
- Google Cloud SDK (gcloud) installed and configured
- A GCP project with billing enabled
- Access to your Supabase project credentials

## 🏗️ Project Overview

**Data Entry App** is a React-based application built with:
- React + Vite + TypeScript
- Supabase backend integration
- Role-based access control (RBAC)
- Tailwind CSS for styling

## 🐳 Local Development with Docker

### Quick Start

1. **Clone and setup environment:**
   ```bash
   cd Project-MNP/data-entry-app
   # For local development, create .env file
   # For production builds, create .env.production file
   cp env.production.example .env.production
   # Edit .env.production with your Supabase credentials
   ```

2. **Run with Docker Compose:**
   ```bash
   docker-compose up data-entry-app
   ```

3. **Access the application:**
   - Production: http://localhost:3000

### Manual Docker Commands

```bash
# Build the image (requires .env.production file)
docker build -t data-entry-app .

# Or build with build arguments (overrides .env.production)
docker build \
  --build-arg VITE_SUPABASE_URL=your-supabase-url \
  --build-arg VITE_SUPABASE_ANON_KEY=your-anon-key \
  -t data-entry-app .

# Run the container
docker run -p 3000:3000 data-entry-app
```

**Note:** Environment variables are baked into the build at build time. Runtime environment variables (`-e` flag) won't work for Vite apps since the values are already compiled into the JavaScript bundle.

## ☁️ Google Container Registry (GCR) Deployment

### Step 1: Configure Environment Variables

Create a `.env.production` file or use build arguments:

```bash
# Option 1: Copy the example file and edit it
cp env.production.example .env.production
# Then edit .env.production with your actual Supabase credentials

# The .env.production file should contain:
# VITE_SUPABASE_URL=https://your-project-id.supabase.co
# VITE_SUPABASE_ANON_KEY=your-anon-key-here
```

**Important:** The `.env.production` file is used during the Docker build process. Vite reads these variables at build time and bakes them into the production JavaScript bundle. 

**How it works:**
- If you provide build args (`--build-arg`), they will override/update the `.env.production` file during build
- If you don't provide build args, the existing `.env.production` file will be used
- The Dockerfile automatically handles this - build args take precedence over the file

### Step 2: Build Docker Image

Build the image with your GCP project ID:

```bash
# Set your GCP project ID
export PROJECT_ID=your-gcp-project-id

# Build with default .env.production
docker build -t gcr.io/$PROJECT_ID/data-entry-app .

# Or build with build arguments (overrides .env.production)
docker build \
  --build-arg VITE_SUPABASE_URL=https://your-project-id.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your-anon-key \
  -t gcr.io/$PROJECT_ID/data-entry-app .
```

### Step 3: Authenticate with GCR

```bash
# Configure Docker to use gcloud as a credential helper
gcloud auth configure-docker

# Or authenticate directly
gcloud auth login
```

### Step 4: Push to GCR

```bash
# Push the image to GCR
docker push gcr.io/$PROJECT_ID/data-entry-app

# Or push with a specific tag
docker tag gcr.io/$PROJECT_ID/data-entry-app gcr.io/$PROJECT_ID/data-entry-app:v1.0.0
docker push gcr.io/$PROJECT_ID/data-entry-app:v1.0.0
```

## 🔧 Environment Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_SUPABASE_URL` | Your Supabase project URL | `https://xyz.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous key | `eyJhbGciOiJIUzI1NiIs...` |

### Setting Up Production Environment Variables

**Option 1: Using .env.production file (Recommended for local builds)**

1. Copy the example file:
   ```bash
   cp env.production.example .env.production
   ```

2. Edit `.env.production` with your actual credentials:
   ```bash
   VITE_SUPABASE_URL=https://your-project-id.supabase.co
   VITE_SUPABASE_ANON_KEY=your-actual-anon-key
   ```

3. Build the Docker image (the file will be automatically used):
   ```bash
   docker build -t gcr.io/$PROJECT_ID/data-entry-app .
   ```

**Option 2: Using Docker build arguments (Recommended for CI/CD)**

Build with build arguments that override `.env.production`:
```bash
docker build \
  --build-arg VITE_SUPABASE_URL=https://your-project-id.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your-anon-key \
  -t gcr.io/$PROJECT_ID/data-entry-app .
```

### Environment Variable Priority

1. **Docker build arguments** (highest priority - overrides everything)
   ```bash
   docker build --build-arg VITE_SUPABASE_URL=... --build-arg VITE_SUPABASE_ANON_KEY=...
   ```

2. **.env.production file** (used if build args not provided)
   - Create this file in the project root using `env.production.example` as a template
   - Vite will read it during build
   - **Note:** This file should NOT be committed to git (already in .gitignore)

3. **.env file** (for local development only, not used in Docker builds)

## 📦 Image Tagging Strategy

### Latest Tag
```bash
docker build -t gcr.io/$PROJECT_ID/data-entry-app:latest .
docker push gcr.io/$PROJECT_ID/data-entry-app:latest
```

### Version Tags
```bash
docker build -t gcr.io/$PROJECT_ID/data-entry-app:v1.0.0 .
docker push gcr.io/$PROJECT_ID/data-entry-app:v1.0.0
```

### Commit SHA Tags (for CI/CD)
```bash
COMMIT_SHA=$(git rev-parse --short HEAD)
docker build -t gcr.io/$PROJECT_ID/data-entry-app:$COMMIT_SHA .
docker push gcr.io/$PROJECT_ID/data-entry-app:$COMMIT_SHA
```

## 🔍 Verifying the Image

### List Images in GCR

```bash
gcloud container images list --repository=gcr.io/$PROJECT_ID
```

### View Image Tags

```bash
gcloud container images list-tags gcr.io/$PROJECT_ID/data-entry-app
```

### Test the Image Locally

```bash
# Pull and run the image from GCR
docker pull gcr.io/$PROJECT_ID/data-entry-app
docker run -p 3000:3131 gcr.io/$PROJECT_ID/data-entry-app
```

## 🆘 Troubleshooting

### Common Issues

1. **Build failures:**
   - Check Docker daemon is running
   - Verify all dependencies in package.json
   - Check for syntax errors in code
   - Ensure environment variables are set correctly

2. **Authentication errors:**
   ```bash
   # Re-authenticate
   gcloud auth login
   gcloud auth configure-docker
   ```

3. **Permission denied:**
   ```bash
   # Check if you have permissions on the GCP project
   gcloud projects list
   gcloud config set project $PROJECT_ID
   ```

4. **Image push failures:**
   - Verify GCR API is enabled: `gcloud services enable containerregistry.googleapis.com`
   - Check project billing is enabled
   - Verify image tag format: `gcr.io/$PROJECT_ID/image-name`

### Debug Commands

```bash
# Check container logs
docker logs <container-id>

# Inspect the image
docker inspect gcr.io/$PROJECT_ID/data-entry-app

# Test build locally first
docker build -t data-entry-app-test .
docker run -p 3000:3000 data-entry-app-test
```

## 📝 Notes

- The Docker image exposes port 3000 internally (nginx)
- For Cloud Run or other platforms, you may need to map port 3000 to 80
- Environment variables are baked into the build at build time (Vite requirement)
- Always use `.env.production` or build args for production builds
- Never commit `.env` or `.env.production` files with real credentials
- Use `env.production.example` as a template - copy it to `.env.production` and fill in your values

## 🔒 Security Best Practices

- Use GCP Secret Manager for sensitive credentials in production
- Rotate Supabase keys regularly
- Use least-privilege IAM roles for GCR access
- Enable GCR vulnerability scanning
- Use specific image tags instead of `latest` in production

## 📞 Support

For issues related to:
- **Application code**: Check the repository issues
- **Supabase**: Visit [Supabase documentation](https://supabase.com/docs)
- **GCP/GCR**: Check [Google Cloud documentation](https://cloud.google.com/container-registry/docs)

