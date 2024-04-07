# https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu
FROM docker.io/library/debian:bookworm-slim as build_image
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update -qq && \
    apt-get -y install --no-install-recommends ca-certificates g++ gcc git make pkg-config yasm && \
    git clone --single-branch --branch n6.1.1 --depth=1 https://github.com/FFmpeg/FFmpeg.git /opt/ffmpeg-n6.1.1

WORKDIR /opt/ffmpeg-n6.1.1
RUN ./configure \
      --prefix="/usr/local/" \
      --pkg-config-flags="--static" \
      --extra-cflags="-march=native" \
      --extra-cflags="-I/usr/local/include" \
      --extra-ldflags="-L/usr/local/lib" \
      --extra-libs="-lpthread -lm" \
      --ld="g++" \
      --bindir="/usr/local/bin" \
      --disable-everything \
      --disable-shared \
      --disable-doc \
      --disable-htmlpages \
      --disable-podpages \
      --disable-txtpages \
      --disable-network \
      --disable-autodetect \
      --disable-hwaccels \
      --disable-ffprobe \
      --disable-ffplay \
      --enable-bsf=aac_adtstoasc,extract_extradata,h264_metadata,mpeg2_metadata \
      --enable-decoder=aac,flac,h264,mjpeg \
      --enable-demuxer=aac,eac3,flac,h264,image2,mov,mpegts \
      --enable-encoder=aac,flac,h264,mjpeg \
      --enable-filter=copy \
      --enable-muxer=eac3,flac,h264,mjpeg,mpegts,mp4 \
      --enable-parser=aac,h264 \
      --enable-protocol=file \
      --enable-small \
      && make -j$(nproc) && make install && hash -r

FROM docker.io/library/python:3.11-slim
LABEL org.opencontainers.image.authors="colinho <github@colin.technology>"
LABEL org.opencontainers.image.description="Waving at the TIDAL music service with Python"
LABEL org.opencontainers.image.documentation="https://github.com/ebb-earl-co/tidal-wave/blob/trunk/README.md"
LABEL org.opencontainers.image.source="https://github.com/ebb-earl-co/tidal-wave"
LABEL org.opencontainers.image.licenses="LGPL-2.1-only"

ENV PIP_DEFAULT_TIMEOUT=100 \
    # Allow statements and log messages to immediately appear
    PYTHONUNBUFFERED=1 \
    # disable a pip version check to reduce run-time & log-spam
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # cache is useless in docker image, so disable to reduce image size
    PIP_NO_CACHE_DIR=1
RUN useradd --create-home --shell /bin/bash debian && mkdir -p /home/debian/.local/bin/ && chown -R debian:debian /home/debian/
COPY --from=build_image --chown=debian:debian /usr/local/bin/ffmpeg /home/debian/.local/bin/ffmpeg
USER debian
WORKDIR /home/debian
COPY --chown=debian:debian pyproject.toml .
COPY --chown=debian:debian tidal_wave/ ./tidal_wave/
RUN pip install --user --upgrade pip setuptools wheel dumb-init && \
    pip install --user . && \
    mkdir -p /home/debian/.config/tidal-wave/ /home/debian/Music/ && \
    chown -R debian:debian /home/debian/.config/tidal-wave/ /home/debian/Music/
ENV PATH="/home/debian/.local/bin:$PATH"
VOLUME /home/debian/.config/tidal-wave /home/debian/Music
ENTRYPOINT ["dumb-init", "--", "tidal-wave"]
CMD ["--help"]
