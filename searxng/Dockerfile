FROM searxng/searxng:latest

# Bake the settings template into the image. At container start, the entrypoint
# script copies it into place and replaces the `ultrasecretkey` placeholder
# with a random value (same mechanism the upstream entrypoint uses when
# creating a fresh settings file). This keeps the repo-tracked config free
# of any committed secret and avoids needing a writable volume on Fly.io.
COPY settings.yml /etc/searxng/settings.template.yml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]