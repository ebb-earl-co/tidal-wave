# Python Package

`tidal-wave` is, first and foremost, a Python project that is built and uploaded to PyPi. Indeed, that is the sole purpose of `pyproject.toml` and `setup.py` at the root of the repository. No frameworks are used for this process such as `poetry` or `pipenv`, just the standard Python `setuptools` and `build`. To that end, the process of building a Python package for a given release is 
  1. change the line `version = ` in `pyproject.toml` to a new version. At the time of writing this, that would be `"2024.4.3"`. This is because PyPi disallows package name/version duplicates.
  2. With a Python virtual environment, or, e.g. on a Debian-based OS, install the APT package `python3-build`, or, with the OS's system-wide Python3 installation, install the `build` package. 
    - I like to have a Python3 virtual environment created with the system Python3 in my home directory for all the bits and bobs required in development: `~/.venv`
  3. From the repository root, simply run `$ python3 -m build` (or, on Windows, `> venv\Scripts\python.exe -m build`) and let the process run its course.
  4. Once that process has finished, there will be two new files in the `dist` subdirectory of the repository root: `dist/tidal-wave-2024.4.3.tar.gz`, and `tidal_wave-2024.4.3-py3-none-any.whl`.
  5. These binaries are uploaded to PyPi using GitHub Actions: in particular, the [`.github/workflows/python-build.yml`](https://github.com/ebb-earl-co/tidal-wave/blob/trunk/.github/workflows/python-build.yml) file

# `pyinstaller`-Created Binaries
Perhaps *the* tried and true method of packaging up a Python project into a single executable comes from the [PyInstaller](https://pyinstaller.org) project. It is the long-term preferred packaging format for `tidal-wave` as it allows for inclusion of arbitrary binary files into the executable apart from Python 3 itself. This is appealing, as `tidal-wave` fundamentally relies on FFmpeg for its successful execution, and it is desired to ship Python 3, FFmpeg, and the `tidal-wave` package as **one binary executable for each platform**.

However, PyInstaller wants to package up a single Python script into an easily-distributed format, yet `tidal-wave` is a Python *package*: the raison d'être of `pyinstaller.py` is to have a script to which PyInstaller can be pointed to in order to package up the project. It mimics the instructions that Python's `build` uses to build a Python package, but it does so in a single .py file (*not* named setup.py) so that PyInstaller is satisfied. Additionally, PyInstaller would like a virtual environment with `tidal-wave`'s Python dependencies installed already, so the process starts with that:
  1. Create virtual environment in repository root: `$ "$(command -v python3)" -m venv ./venv` and install `tidal-wave`'s dependencies
   - `$ ./venv/bin/python3 -m pip install --upgrade pip setuptools wheel`
   - `$ ./venv/bin/python3 -m pip install -r requirements.txt`
   - `$ ./venv/bin/python3 -m pip install pyinstaller==6.7.0`
  2. Without compiling FFmpeg from source, the command is very simple:
  ```bash
  ./venv/bin/pyinstaller \
    --name tidal-wave_linux \
    --paths tidal_wave \
    --exclude-modules pyinstaller \
    --exclude-modules ruff \
    --clean \
    --noupx \
    --onefile \
    --strip \
    ./pyinstaller.py
  ```
  3. If successfully executed, the binary is located at `./dist/tidal-wave_linux`. In this situation, without FFmpeg, the binary is effectively the same as a .pyz file or similar Python archive
  4. For `tidal-wave` starting with version 2024.4.1, the following invocation is what creates the artifacts released with every version:
  ```bash
  # FFmpeg 7.0 is compiled before this step in the directory `ffmpeg-n7.0`
  ./venv/bin/pyinstaller \
    --name tidal-wave_linux \
    --paths tidal_wave \
    --exclude-modules pyinstaller \
    --exclude-modules ruff \
    --add-binary "ffmpeg-n7.0/ffmpeg:." \
    --clean \
    --noupx \
    --onefile \
    --strip \
    ./pyinstaller.py
  ```
  The resulting `tidal-wave_linux` artifact is a single-click executable with everything that `tidal-wave` needs to execute! The GitHub Actions automations that execute this process are:
  - `.github/workflows/pyinstaller-linux.yml`
  - `.github/workflows/pyinstaller-macos_arm64.yml`
  - `.github/workflows/pyinstaller-macos_x86.yml`
  - `.github/workflows/pyinstaller-windows.yml`

# Container Image
The file `Dockerfile` in the repository root is the template for an OCI container image. As the invocation of the container image is a self-contained runtime, not a single executable, it compiles FFmpeg from source, and passes the `ffmpeg` executable to the standard Python container image which executes `tidal-wave` as a module. This is the Docker [multi-stage build](https://docs.docker.com/build/building/multi-stage/#use-multi-stage-builds) pattern, and is useful to keep the container image size down.

To wit, the container image creates directories that are owned by the user `debian`, creates a Python virtual environment, installs the `tidal-wave` Python dependencies, and executes the command `$ source venv/bin/activate && pip install . && tidal_wave ...` depending on arguments passed in at runtime.

# FFmpeg
Ideally, for each release of `tidal-wave`, there will be a binary created and available on the Releases page for each platform. This would entail bundling [FFmpeg](https://ffmpeg.org), a triumphantly successful [FOSS](https://en.wikipedia.org/wiki/Free_and_open-source_software) project. Not only is it instructive to outline here how to compile a (usefully minimal) version of FFmpeg from source, but it is also required by FFmpeg's license: that is, instructions for how one's application that uses FFmpeg's libraries compiles FFmpeg, including disclaimers and links to FFmpeg's source code.

To fulfill these requirements, `tidal-wave` clones FFmpeg for every build, version 7.0, which corresponds to the [`n7.0` branch](https://github.com/FFmpeg/FFmpeg/tree/n7.0) of the GitHub-hosted mirror of FFmpeg's source code. Using this, reproducible compilation is very simple: even though the [FFmpeg documentation](https://trac.ffmpeg.org/wiki/CompilationGuide) advises building the newest snapshot version, fulfilling the license agreement of ensuring that the libraries included and binaries built for inclusion in one's project would be much more difficult.

Now, FFmpeg has a dizzying array of configuration options because it supports a vast amount of audio and video codecs. It is a very popular library for transcoding multimedia data into all of the formats required and desired in today's cornucopia of video on demand services. However, all that `tidal-wave` uses FFmpeg for is *remuxing* audio and video data. That is, instead of converting the, say, FLAC audio that is retrieved from TIDAL into another format, e.g. MP3, `tidal-wave` simply changes the .mp4 file that is retrieved from TIDAL into a .flac without changing the audio bytes at all. This is called re-muxing, and a good analogy is one of taking a letter out of one envelope and putting it into a differently-sized or differently-stamped envelope: the *contents* of the message are the same (i.e. the audio data), just the *container* (i.e. the file extension and metadata format) has changed. This simplifies the compiling of FFmpeg *significantly*, indeed creating a binary that is **one tenth** the size of the default binary spelled out in FFmpeg's documentation.

Only a few dependencies are necessary, but most important of them is a C/C++ compiler, such as `gcc`. On a Debian-based system, the following APT packages are the only requirements:
 - `ca-certificates`
 - `g++`
 - `gcc`
 - `git`
 - `make`
 - `pkg-config`
 - `yasm`

With these installed, configuring and compiling FFmpeg with the small amount of configuration needed for `tidal-wave` looks like the following:
```bash
configure \
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
    --enable-small && \
make -j$(nproc) && make -j$(nproc) install
```

The resulting binary, `/usr/local/bin/ffmpeg` will be around 4 MB in size. The above example is for Debian-based GNU/Linux x86\_64 systems. An analagous invocation for macOS, both x86\_64 and aarch64, is found in the [workflows](https://github.com/ebb-earl-co/tidal-wave/tree/trunk/.github/workflows) directory of this repository.
### Building FFmpeg on Windows
Because FFmpeg is a program that is designed for --and primarily used in-- Unix-like environments, getting the C and C++ tools necessary to compile it on Windows is difficult. There is the [Mingw-w64](https://www.mingw-w64.org/) project that brings the GCC (GNU C compiler) toolchain to Windows, and that is what `tidal-wave` leans on. Some wonderfully generous person took the Mingw-w64 project and created the [Media autobuild suite project](https://github.com/m-ab-s/media-autobuild_suite) for Windows that simplifies all of the sharp edges of cross-platform compiling into one, simple process. Indeed, `tidal-wave` simply uses a [fork of the media autobuild suite project](https://github.com/ebb-earl-co/media-autobuild_suite/releases/tag/n7.0) to provide `ffmpeg.exe` for [`tidal-wave` Windows release artifacts](https://github.com/ebb-earl-co/tidal-wave/blob/trunk/.github/workflows/pyinstaller-windows.yml#L29).

If you want to replicate this process on your own Windows machine, take a look at the [configuration file](https://github.com/ebb-earl-co/media-autobuild_suite/blob/master/build/media-autobuild_suite.ini) used for `tidal-wave`, and the accompanying [FFmpeg options](https://github.com/ebb-earl-co/media-autobuild_suite/blob/master/build/ffmpeg_options.txt)
## Licensing
By not passing `--enable-nonfree` and `--enable-gpl` when configuring FFmpeg, the resulting binary is licensed under the LGPLv2.1, *not* the GPL. This may be a minor distinction, but it is important to highlight. Videos retrieved from TIDAL using one of the PyInstaller-created binaries **will only** remux the file and add metadata: to re-encode the video would require the GPL-licensed `x264` library, which would render the binaries for all platforms under that license, not the LGPLv2.1.
