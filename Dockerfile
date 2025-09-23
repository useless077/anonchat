# Use the official Python 3.9 slim image as the base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install git and any other necessary system packages
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and switch to that user
RUN useradd -m myuser
USER myuser

# Copy the requirements.txt file into the working directory
COPY requirements.txt .

# Install the Python dependencies specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the application code into the working directory
COPY --chown=myuser:myuser . .

# Specify the command to run the bot when the container starts
CMD ["python", "bot.py"]
