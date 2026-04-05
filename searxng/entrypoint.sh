#!/bin/sh
# Entrypoint wrapper for SearXNG on Fly.io.
#
# The upstream SearXNG entrypoint only patches the `ultrasecretkey` placeholder
# when the settings file does not exist. Since we bake a customized template
# into the image, we copy it into place here and do the sed replacement
# ourselves before handing off to the upstream entrypoint.
set -eu

TEMPLATE="/etc/searxng/settings.template.yml"
TARGET="/etc/searxng/settings.yml"

cp "$TEMPLATE" "$TARGET"

SECRET="$(head -c 24 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')"
sed -i "s/ultrasecretkey/${SECRET}/g" "$TARGET"

exec /usr/local/searxng/entrypoint.sh
