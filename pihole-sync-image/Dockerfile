FROM python:3.9.10-alpine3.15

RUN mkdir /pihole-sync

COPY pihole_sync.py /pihole-sync/pihole_sync.py
RUN python -mvenv /pihole-sync/venv && /pihole-sync/venv/bin/pip install kubernetes==23.3.0 && chown 999 -R /pihole-sync

ENTRYPOINT [ "/pihole-sync/venv/bin/python", "/pihole-sync/pihole_sync.py" ]