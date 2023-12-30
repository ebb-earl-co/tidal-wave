# https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu
FROM debian:bookworm-slim as build_image
RUN export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && apt-get -y install --no-install-recommends \
  autoconf \
  bzip2 \
  build-essential \
  pkg-config \
  wget \
  yasm \
  zlib1g-dev
RUN mkdir ~/ffmpeg_sources ~/ffmpeg_build ~/bin
RUN cd ~/ffmpeg_sources && \
    wget --no-check-certificate -O ffmpeg-snapshot.tar.bz2 https://ffmpeg.org/releases/ffmpeg-snapshot.tar.bz2 && \
    tar xjvf ffmpeg-snapshot.tar.bz2 && \
    cd ffmpeg && \
    PATH="$HOME/bin:$PATH" PKG_CONFIG_PATH="$HOME/ffmpeg_build/lib/pkgconfig" ./configure \
      --prefix="$HOME/ffmpeg_build" \
      --pkg-config-flags="--static" \
      --extra-cflags="-I$HOME/ffmpeg_build/include" \
      --extra-ldflags="-L$HOME/ffmpeg_build/lib" \
      --extra-libs="-lpthread -lm" \
      --ld="g++" \
      --bindir="$HOME/bin" && \
    PATH="$HOME/bin:$PATH" make && \
    make install && \
    hash -r

FROM python:3.11-slim as runtime_image
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
