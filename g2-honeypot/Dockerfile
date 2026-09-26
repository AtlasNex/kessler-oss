FROM python:3.11-slim
WORKDIR /app
# The SAME public kernel engagements run (C-2: the core is stdlib; pip brings the package only).
# Tarball URL, not git+: slim images carry no git, and the tarball needs none.
RUN pip install --no-cache-dir https://github.com/AtlasNex/kessler-oss/archive/refs/heads/main.tar.gz
COPY server.py export-capture.py ./
ENV HONEY_DB=/data/capture.db HONEY_PORT=8095
VOLUME /data
EXPOSE 8095
CMD ["python", "server.py"]
