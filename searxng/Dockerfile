FROM searxng/searxng:latest

# Bake the settings template into the image. At container start, the wrapper
# below copies it into place and replaces the `ultrasecretkey` placeholder
# with a random value (same mechanism the upstream entrypoint uses when
# creating a fresh settings file). This keeps the repo-tracked config free
# of any committed secret and avoids needing a writable volume on Fly.io.
COPY settings.yml /etc/searxng/settings.template.yml

ENTRYPOINT ["/bin/sh", "-c", "cp /etc/searxng/settings.template.yml /etc/searxng/settings.yml && sed -i \"s/ultrasecretkey/$(head -c 24 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')/g\" /etc/searxng/settings.yml && exec /usr/local/searxng/entrypoint.sh"]
