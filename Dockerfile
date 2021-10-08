FROM python:3.8 as base
COPY mammoannotator /opt/mammoannotator
COPY setup.py /opt/
RUN cd /opt/ && pip install -e .
CMD cd /opt/server_root/ && \
    echo "bringing up img-server in port 8000" && \
    nohup python -m http.server 8000 --bind 127.0.0.1 > /dev/stdout > /dev/null & \
    /bin/bash
