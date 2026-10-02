# kgi-interop-monitor container image

FROM python:3.12-slim

# git: pyproject.toml installs nicescholia from its git repository
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# install the dependencies in their own layer for faster rebuilds
COPY pyproject.toml /build/
RUN python -c "import sys, tomllib; \
        project = tomllib.load(sys.stdin.buffer)['project']; \
        print('\n'.join(project['dependencies']))" \
        < /build/pyproject.toml > /build/requirements.txt \
    && pip install --no-cache-dir --requirement /build/requirements.txt

# install the package itself; the build files are not needed afterwards
COPY README.md LICENSE /build/
COPY src /build/src
RUN pip install --no-cache-dir --no-deps /build && rm -rf /build

# unprivileged user; the app writes its caches and states into its home
RUN useradd --create-home kgi
USER kgi
WORKDIR /home/kgi

# the measured states; created by kgi so a volume mounted here is writable
RUN mkdir .nicescholia

ENV PYTHONUNBUFFERED=1

EXPOSE 9001

# listen on all interfaces, not only the container's localhost
CMD ["kgi-interop-monitor", "--serve", "--host", "0.0.0.0", "--port", "9001"]
