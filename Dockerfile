FROM emscripten/emsdk:6.0.10@sha256:e077d54e2b8970575ebc4f185ac1de0b95c05f2b266134d4ba27449af7aebf65 AS base-image

RUN \
  apt update -y && \
  apt install -y libclang1-20=1:20.1.2-0ubuntu1~24.04.3 && \
  ln -s /usr/lib/llvm-20/lib/libclang-20.so.1 /usr/lib/x86_64-linux-gnu/libclang.so

RUN \
  pip install --break-system-packages \
  clang==20.1.2 \
  pyyaml==6.0.3 \
  cerberus==1.3.8

WORKDIR /rapidjson/
RUN \
  git clone https://github.com/Tencent/rapidjson.git . && \
  git checkout 24b5e7a8b27f42fa16b96fc70aade9106cf7102f

ENV OCCT_COMMIT_HASH_FULL=b8f597c677811d1f9f4d8a97f5ae2825c0353a42
WORKDIR /occt/
RUN \
  curl -fsSL "https://github.com/Open-Cascade-SAS/OCCT/archive/${OCCT_COMMIT_HASH_FULL}.tar.gz" -o occt.tar.gz && \
  echo "dba62b81078dd43cec23feba89432be301582341001edad1b93342ad8bda35ea  occt.tar.gz" | sha256sum -c && \
  tar -xzf occt.tar.gz --strip-components=1 && \
  sed -n 's/^set (\(OCC_VERSION_[A-Z]*\) \([0-9]*\) )$/s|@\1@|\2|g/p' adm/cmake/version.cmake > /tmp/version.sed && \
  sed -f /tmp/version.sed -e 's|@SET_OCC_VERSION_DEVELOPMENT@||' -e 's|@OCCT_VERSION_DATE@||' adm/templates/Standard_Version.hxx.in > src/FoundationClasses/TKernel/Standard/Standard_Version.hxx && \
  ! grep -E '@[A-Z_]+@' src/FoundationClasses/TKernel/Standard/Standard_Version.hxx

WORKDIR /opencascade.js/
COPY src ./src
WORKDIR /src/

ARG threading=single-threaded
ENV threading=$threading

FROM base-image AS test-image

RUN \
  mkdir /opencascade.js/build/ && \
  mkdir /opencascade.js/dist/ && \
  /opencascade.js/src/applyPatches.py

ENTRYPOINT ["/opencascade.js/src/buildFromYaml.py"]

FROM test-image AS custom-build-image

RUN \
  /opencascade.js/src/generateBindings.py && \
  /opencascade.js/src/compileBindings.py ${threading} && \
  /opencascade.js/src/compileSources.py ${threading} && \
  chmod -R 777 /opencascade.js/ && \
  chmod -R 777 /occt

ENTRYPOINT ["/opencascade.js/src/buildFromYaml.py"]
