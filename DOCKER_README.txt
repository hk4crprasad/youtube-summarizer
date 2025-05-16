# Docker Instructions

Simple steps to run this application with Docker:

## Build the Docker image
```bash
docker build -t yt .
```

## Run the Docker container
```bash
docker run -p 8080:8080 yt
```

The application will be available at http://localhost:8080

## Notes
- The Docker image includes ffmpeg and all dependencies
- Environment variables are loaded from the .env file
- The application runs on port 8080

## Customization
If you need to modify environment variables, edit the .env file before building the Docker image.
