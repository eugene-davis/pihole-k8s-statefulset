FROM python:3.9.13-alpine3.16

RUN mkdir /pihole-sync

COPY . /pihole-sync/

WORKDIR /pihole-sync

RUN python -mvenv /pihole-sync/venv && /pihole-sync/venv/bin/python -m pip install --no-cache-dir --upgrade pip && /pihole-sync/venv/bin/pip install --no-cache-dir . && chown 999 -R /pihole-sync

ENTRYPOINT [ "/pihole-sync/venv/bin/pihole_sync" ]