FROM searxng/searxng:latest

# Bake the settings template and entrypoint wrapper into the image.
# At container start, the entrypoint script copies the template into place
# and replaces the `ultrasecretkey` placeholder with a random value (same
# mechanism the upstream entrypoint uses when creating a fresh settings file).
# This keeps the repo-tracked config free of any committed secret and avoids
# needing a writable volume on Fly.io.
#
# NOTE: Fly.io runs `flyctl deploy --config fly.searxng.toml` from the repo
# root, so the Docker build context is the repo root (not `searxng/`).
# COPY paths must be relative to the repo root.
COPY searxng/settings.yml /etc/searxng/settings.template.yml
COPY searxng/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
