# https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu
FROM docker.io/library/debian:bookworm-slim as build_image
RUN export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && apt-get -y install --no-install-recommends build-essential pkg-config yasm
COPY FFmpeg-6.1.1/ FFmpeg-6.1.1/
WORKDIR FFmpeg-6.1.1
RUN PATH="$HOME/bin:$PATH" PKG_CONFIG_PATH="$HOME/ffmpeg_build/lib/pkgconfig" ./configure \
      --prefix="$HOME/ffmpeg_build" \
      --pkg-config-flags="--static" \
      --extra-cflags="-I$HOME/ffmpeg_build/include" \
      --extra-ldflags="-L$HOME/ffmpeg_build/lib" \
      --extra-libs="-lpthread -lm" \
      --ld="g++" \
      --bindir="$HOME/bin" \
      --disable-everything \
      --disable-doc \
      --disable-htmlpages \
      --disable-podpages \
      --disable-txtpages \
      --disable-network \
      --disable-autodetect \
      --disable-hwaccels \
      --disable-ffprobe \
      --disable-ffplay \
      --enable-decoder=flac,mjpeg \
      --enable-demuxer=aac,eac3,flac,image2,mov,mpegts \
      --enable-encoder=flac,mjpeg \
      --enable-filter=copy \
      --enable-muxer=eac3,flac,mjpeg,mpegts,mp4 \
      --enable-protocol=file \
      --enable-small \
      && \
    PATH="$HOME/bin:$PATH" make -j$(nproc) && \
    make install && \
    hash -r

FROM docker.io/library/python:3.11-slim as runtime_image

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
RUN pip install --user --upgrade pip setuptools wheel dumb-init && \
    pip install --user -r requirements.txt && \
    mkdir -p /home/debian/.config/tidal-wave/ /home/debian/Music/ && \
    chown -R debian:debian /home/debian/.config/tidal-wave/ /home/debian/Music/
ENV PATH="/home/debian/.local/bin:$PATH"
VOLUME /home/debian/.config/tidal-wave /home/debian/Music
ENTRYPOINT ["dumb-init", "--", "python3", "-m", "tidal_wave"]
CMD ["--help"]
