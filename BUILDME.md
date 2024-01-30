# Python Package

`tidal-wave` is, first and foremost, a Python project that is built and uploaded to PyPi. Indeed, that is the sole purpose of `pyproject.toml` and `setup.py` at the root of the repository. No frameworks are used for this process such as `poetry` or `pipenv`, just the standard Python `setuptools` and `build`. To that end, the process of building a Python package for a given release is 
  1. change the line `version = ` in `pyproject.toml` to a new version. At the time of writing this, that would be `"2024.1.14"`. This is because PyPi disallows package name/version duplicates.
  2. With a Python virtual environment, or, e.g. on a Debian-based OS, install the APT package `python3-build`, or, with the OS's system-wide Python3 installation, install the `build` package. 
    - I like to have a Python3 virtual environment created with the system Python3 in my home directory for all the bits and bobs required in development: `~/.venv`
  3. From the repository root, simply run `$ python3 -m build` (or, on Windows, `> venv\Scripts\python.exe -m build`) and let the process run its course.
  4. Once that process has finished, there will be two new files in the `dist` subdirectory of the repository root: `dist/tidal-wave-2024.1.14.tar.gz`, and `tidal_wave-2024.1.14-py3-none-any.whl`.
  5. These binaries are uploaded to PyPi using GitHub Actions: in particular, the `.github/workflows/python-build.yml` file

# `pyapp`-Created Binaries
The [`pyapp` project](https://github.com/ofek/pyapp) is a clever manipulation of [Rust's `cargo`](https://crates.io/crates/pyapp) packaging mechanism that wraps up a Python package into a single binary (.exe on Windows). Optionally, a Python3 installation can be included, so that the aforementioned binary is a single-file, self-bootstrapping executable! 

It requires that the [Rust language](https://www.rust-lang.org/tools/install) be installed, with the `cargo` tool a subset of that, and for some C/C++ compiler to be installed. This is trivial on GNU/Linux, and probably on macOS, but on Windows, it is a bit of a chore: [Visual Studio](https://visualstudio.microsoft.com/) is required (**not** the code editor; the full Visual Studio program). I found that, even after having installed Visual Studio, I needed to launch the program, and install the optional C++ desktop packages/libraries/frameworks.

Once these are installed and available on `PATH`, the genius of `pyapp` is that all it needs are a few environment variables to build the executable. For `tidal-wave`, binaries are ony created upon release, so that lines up with a Python package release. Indeed, `pyapp` *requires* a project version string in order to execute. So, continuing with the version `2024.1.14` from above, the steps are as follows:
  1. Set environment variables on Windows; optionally on GNU/Linux or macOS (the latter can pass environment variables simply at invocation time):
  `> $Env:PYAPP_PROJECT_NAME="tidal-wave"`, `> $Env:PYAPP_PROJECT_VERSION="2024.1.14"`, `> $Env:PYAPP_DISTRIBUTION_EMBED=1` `> $Env:PYAPP_PYTHON_VERSION=3.11`
  2. Simply call `> cargo.exe install pyapp --root out\` to compile `pyapp`, which will create a binary at `.\out\bin\pyapp.exe` on Windows.
   - On GNU/Linux or macOS, it's a 1-liner: `$ PYAPP_PROJECT_NAME=tidal-wave PYAPP_PROJECT_VERSION=2024.1.14 PYAPP_DISTRIBUTION_EMBED=1 PYAPP_PYTHON_VERSION=3.11 cargo install pyapp --root out/`

This process is run by GitHub Actions at every project release: in particular, the files
  - `.github/workflows/pyapp-linux.yml`
  - `.github/workflows/pyapp-macos_arm64.yml`
  - `.github/workflows/pyapp-macos.yml`
  - `.github/workflows/pyapp-windows.yml`

# `pyinstaller`-Created Binaries
Perhaps *the* tried and true method of packaging up a Python project into a single executable comes from the [Pyinstaller](https://pyinstaller.org) project. It has the same end goal as `pyapp`, but is much older and does not use Rust in its execution. In fact, it is the long-term preferred packaging format for `tidal-wave` as it allows for inclusion of arbitrary binary files into the executable apart from Python 3 itself. This is appealing, as `tidal-wave` fundamentally relies on FFmpeg for its successful execution, and it is desired to ship Python 3, FFmpeg, and the `tidal-wave` package as **one binary executable for each platform**.

However, `pyinstaller` wants to package up a single Python script into an easily-distributed format, yet `tidal-wave` is a Python *package*, so that is the role of the `pyinstaller.py`. It mimics the instructions that Python's `build` uses to build a Python package, but it does that in a single .py file, *not* named setup.py so that `pyinstaller` is satisfied. Additionally, `pyinstaller` would like a virtual environment with `tidal-wave`'s Python dependencies installed already, so the process starts with that:
  1. Create virtual environment in repository root: `$ $(command -v python3) -m venv ./venv` and install `tidal-wave`'s dependencies
   - `$ ./venv/bin/python3 -m pip install --upgrade pip setuptools wheel`
   - `$ ./venv/bin/python3 -m pip install -r requirements.txt`
   - `$ ./venv/bin/python3 -m pip install pyinstaller`
  2. Without compiling FFmpeg from source, the command is very simple:
  ```bash
  ./venv/bin/pyinstaller \
    --distpath ./.dist \
    --workpath ./.build \
    --name tidal-wave_py311_linux \
    --paths tidal_wave \
    --add-data "README.md:." \
    --clean \
    --noupx \
    --onefile \
    --strip \
    ./pyinstaller.py
  ```
  3. If successfully executed, the binary is located at `./.dist/tidal-wave_py311_linux`. In this situation, without FFmpeg, the binary is essentially the same as the `pyapp`-created binary for GNU/Linux. 
  4. At the time of writing, there is no GitHub Action automation to build an executable for Windows with `pyinstaller`, as I have not figured out how to compiled FFmpeg from source on Windows, or cross-compile *for* Windows on a nother platform.

  The GitHub Actions automations that execute this process are:
  - `.github/workflows/pyinstaller-linux.yml`
  - `.github/workflows/pyinstaller-macos_arm64.yml`
  - `.github/workflows/pyinstaller-macos_x86.yml`

# Container Image
The file `Dockerfile` in the repository root is the template for an OCI container image. As the invocation of the container image is a self-contained runtime, not a single executable, it compiles FFmpeg from source, and passes the `ffmpeg` executable to the standard Python container image which executes `tidal-wave` as a module. This is the Docker [multi-stage build](https://docs.docker.com/build/building/multi-stage/#use-multi-stage-builds) pattern, and is useful to keep the container image size down.

To wit, the container image creates directories that are owned by the user `debian`, creates a Python virtual environment, installs the `tidal-wave` Python dependencies, and executes the command `$ python3 -m tidal_wave ...` depending on arguments passed in with `$ docker run`. 

# FFmpeg
Ideally, for each release of `tidal-wave`, there will be a binary created and available on the Releases page for each platform. This would entail bundling [FFmpeg](https://ffmpeg.org), a triumphantly successful [FOSS](https://en.wikipedia.org/wiki/Free_and_open-source_software) project. Not only is it instructive to outline here how to compile a (usefully minimal) version of FFmpeg from source, but it is also required by FFmpeg's license: that is, instructions for how one's application that uses FFmpeg's libraries compiles FFmpeg, including disclaimers and links to FFmpeg's source code.

To fulfill these requirements, `tidal-wave`'s home repository on GitHub includes FFmpeg as a submodule: in particular, FFmpeg version 6.1.1, which corresponds to the [`n6.1.1` branch](https://github.com/FFmpeg/FFmpeg/tree/n6.1.1) of the GitHub-hosted mirror of FFmpeg's source code. Using this, reproducible compilation is very simple: even though the [FFmpeg documentation](https://trac.ffmpeg.org/wiki/CompilationGuide) advises building the newest snapshot version, fulfilling the license agreement of ensuring that the libraries included and binaries built for inclusion in one's project would be much more difficult.

Now, FFmpeg has a dizzying array of configuration options because it supports a vast amount of audio and video codecs. It is a very popular library for transcoding multimedia data into all of the formats required and desired in today's cornucopia of video on demand services. However, all that `tidal-wave` uses FFmpeg for is *remuxing* audio and video data. That is, instead of converting the, say, FLAC audio that is retrieved from TIDAL into another format, e.g. MP3, `tidal-wave` simply changes the .mp4 file that is retrieved from TIDAL into a .flac without changing the audio bytes at all. This is called re-muxing, and a good analogy is one of taking a letter out of one envelope and putting it into a differently-sized or differently-stamped envelope: the *contents* of the message are the same (i.e. the audio data), just the *container* (i.e. the file extension and metadata format) has changed. This simplifies the compiling of FFmpeg *significantly*, indeed creating a binary that is **one tenth** the size of the default binary spelled out in FFmpeg's documentation.

Only a few dependencies are necessary, but most important of them is a C/C++ compiler, such as `gcc`. On a Debian-based system, the following APT packages are the only requirements:
 - `autoconf`
 - `build-essential`
 - `pkg-config`
 - `yasm`

With these installed, configuring and compiling FFmpeg with the small amount of configuration needed for `tidal-wave` looks like the following:
```bash
$ PATH="$HOME/bin:$PATH" PKG_CONFIG_PATH="$HOME/ffmpeg_build/lib/pkgconfig" ./configure \
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
    --enable-small && \
PATH="$HOME/bin:$PATH" make -j$(nproc) && make install
```

The resulting binary, `${HOME}/bin/ffmpeg` will be around 2 MB in size. To fulfill the overarching goal of `tidal-wave`, bundling an executable with `pyinstaller` that includes FFmpeg, can be done by pointing to the directory with the newly-created FFmpeg binary:
```bash
$ ./venv/bin/pyinstaller \
    --distpath ./.dist \
    --workpath ./.build \
    --name tidal-wave_py311_FFmpeg6.1.1_macos_x86_64 \
    --target-arch=x86_64 \
    --paths tidal_wave \
    --add-data "README.md:." \
    --add-binary "${HOME}/bin/ffmpeg:." \
    --clean \
    --noupx \
    --onefile \
    --strip \
    ./pyinstaller.py
```

The above example is for Intel CPU-based Mac machines. An analagous invocation for the newer, Apple Silicon-based Mac machines is found in the file `.github/workflows/pyinstaller-macos_arm64.yml`.
## Licensing
By not passing `--enable-nonfree` and `--enable-gpl` when configuring FFmpeg, the resulting binary is licensed under the LGPLv2.1, *not* the GPL. This may be a minor distinction, but it is important to highlight. This is why videos retrieved from TIDAL using one of the `pyinstaller`-created binaries **will not** remux the file and add metadata: to do so would require the GPL-licensed `x264` library, which would render the binaries for all platforms under that license, not the LGPLv2.1. However, using FFmpeg externally installed with `tidal-wave` as a Python module, or with the `pyapp`-compiled binaries *would* remux any video requested, adding metadata.