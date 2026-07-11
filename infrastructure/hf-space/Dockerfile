FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Bake the official checkpoints into the image at build time (public MIT repos,
# anonymous download). Layer order: deps -> weights -> code, so code edits
# never re-download weights. No weights ever enter the Space git repo.
ARG KRONOS_MODEL_ID=NeoQuasar/Kronos-small
ARG KRONOS_TOKENIZER_ID=NeoQuasar/Kronos-Tokenizer-base
ARG EMBEDDING_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
ENV KRONOS_MODEL_ID=${KRONOS_MODEL_ID} \
    KRONOS_TOKENIZER_ID=${KRONOS_TOKENIZER_ID} \
    EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID}

COPY download_models.py ./
RUN python download_models.py

COPY kronos_src ./kronos_src
COPY app.py ./

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Everything needed is baked above; fail fast if anything tries the network.
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
