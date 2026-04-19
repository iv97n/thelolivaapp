# Use lightweight alpine Python image
FROM python:3.11-alpine

# Set working directory
WORKDIR /app

# Copy the server script and public static files
COPY server.py ./
COPY public/ ./public/

# Expose port 8080
EXPOSE 8080

# Start python backend
CMD ["python3", "server.py"]
