# https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu
FROM debian:bookworm-slim as build_image
RUN export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && apt-get -y install --no-install-recommends \
  autoconf \
  build-essential \
  ca-certificates \
  curl \
  gpg \
  gpg-agent \
  pkg-config \
  yasm \
  zlib1g-dev
RUN mkdir ~/ffmpeg_sources ~/ffmpeg_build ~/bin
RUN cd ~/ffmpeg_sources && \
    curl --output ffmpeg-6.1.1.tar.gz https://ffmpeg.org/releases/ffmpeg-6.1.1.tar.gz && \
    curl --output ffmpeg-6.1.1.tar.gz.asc https://ffmpeg.org/releases/ffmpeg-6.1.1.tar.gz.asc && \
    curl -sSL https://ffmpeg.org/ffmpeg-devel.asc | gpg --import - && \
    gpg --verify ffmpeg-6.1.1.tar.gz.asc ffmpeg-6.1.1.tar.gz && \
    tar xzf ffmpeg-6.1.1.tar.gz && \
    cd ffmpeg-6.1.1 && \
    PATH="$HOME/bin:$PATH" PKG_CONFIG_PATH="$HOME/ffmpeg_build/lib/pkgconfig" ./configure \
      --prefix="$HOME/ffmpeg_build" \
      --pkg-config-flags="--static" \
      --extra-cflags="-I$HOME/ffmpeg_build/include" \
      --extra-ldflags="-L$HOME/ffmpeg_build/lib" \
      --extra-libs="-lpthread -lm" \
      --ld="g++" \
      --bindir="$HOME/bin" \
      && \
    PATH="$HOME/bin:$PATH" make -j$(nproc) && \
    make install && \
    hash -r

FROM python:3.11-slim as runtime_image

LABEL org.opencontainers.image.authors "colinho <github@colin.technology>"
LABEL org.opencontainers.image.description "Waving at the TIDAL music service with Python"
LABEL org.opencontainers.image.documentation "https://github.com/ebb-earl-co/tidal-wave/blob/trunk/README.md"
LABEL org.opencontainers.image.source "https://github.com/ebb-earl-co/tidal-wave"
LABEL org.opencontainers.image.licenses "LGPL-2.1-only"

ENV PIP_DEFAULT_TIMEOUT=100 \
    # Allow statements and log messages to immediately appear
    PYTHONUNBUFFERED=1 \
    # disable a pip version check to reduce run-time & log-spam
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # cache is useless in docker image, so disable to reduce image size
    PIP_NO_CACHE_DIR=1
RUN useradd --create-home --shell /bin/bash debian
COPY --from=build_image --chown=debian:debian /root/bin/ffmpeg /usr/local/bin/ffmpeg
USER debian
WORKDIR /home/debian
COPY --chown=debian:debian requirements.txt .
COPY --chown=debian:debian tidal_wave/ ./tidal_wave/
RUN mkdir -p /home/debian/.config/tidal-wave/ /home/debian/Music/ && \
    chown -R debian:debian /home/debian/.config/tidal-wave/ /home/debian/Music/ && \
    pip install --user -r requirements.txt
VOLUME /home/debian/.config/tidal-wave /home/debian/Music
ENTRYPOINT ["python3", "-m", "tidal_wave"]
CMD ["--help"]
