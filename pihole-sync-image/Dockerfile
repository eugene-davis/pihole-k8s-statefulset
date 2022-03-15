FROM python:3.9.10-alpine3.15

RUN mkdir /pihole-sync

COPY pihole_sync.py /pihole-sync/pihole_sync.py
COPY requirements.txt /requirements.txt

RUN python -mvenv /pihole-sync/venv && /pihole-sync/venv/bin/pip install -r /requirements.txt && chown 999 -R /pihole-sync && rm  /requirements.txt

ENTRYPOINT [ "/pihole-sync/venv/bin/python", "/pihole-sync/pihole_sync.py" ]