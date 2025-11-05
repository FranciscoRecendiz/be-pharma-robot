FROM python:3.12-slim

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm build-essential gfortran libopenblas-dev liblapack-dev \
    libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g n8n

COPY requirements.txt /project/requirements.txt
COPY agent_requirements.txt /project/agent_requirements.txt
RUN pip install --no-cache-dir -r /project/requirements.txt && \
    pip install --no-cache-dir -r /project/agent_requirements.txt

WORKDIR /project
COPY src /project/src

EXPOSE 5678
CMD ["n8n", "start"]



