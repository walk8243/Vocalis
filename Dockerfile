FROM python:3.11-slim

# 音声デコード用システムライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
	ffmpeg \
	libsndfile1 \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip 自体の更新と requirements のコピー
COPY requirements.txt .

# pip キャッシュをマウントして再ビルドを高速化
RUN --mount=type=cache,target=/root/.cache/pip \
	pip install --no-cache-dir -r requirements.txt

# アプリケーションコードの配置
COPY . .

RUN mkdir -p uploads static

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
