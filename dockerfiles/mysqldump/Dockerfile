# ---- Stage 1: Build mysqldump from MySQL source ----
FROM cgr.dev/chainguard/wolfi-base:latest AS builder

# Install build dependencies only
RUN apk add --no-cache \
    build-base \
    cmake \
    ncurses-dev \
    bison \
    openssl-dev \
    zlib-dev \
    boost-dev \
    curl-dev \
    libedit-dev \
    libtirpc-dev \
    git \
    bash \
    make \
    xz \
    binutils

# Set working directory
WORKDIR /build

# Shallow clone only needed branch and minimal history
RUN git clone --branch mysql-8.0.42 --depth 1 https://github.com/mysql/mysql-server.git

# Create build dir outside source
RUN mkdir /build/build-dir

WORKDIR /build/build-dir

# Configure cmake build
RUN cmake ../mysql-server \
    -DDOWNLOAD_BOOST=1 \
    -DWITH_BOOST=boost \
    -DWITH_UNIT_TESTS=OFF \
    -DWITHOUT_SERVER=ON \
    -DWITH_EDITLINE=bundled \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="-O3" \
    -DCMAKE_CXX_FLAGS="-O3"

# Build and install
RUN make -j$(nproc) client
RUN make -j$(nproc) install

# ---- Stage 2: Final minimal runtime image ----
FROM cgr.dev/chainguard/wolfi-base:latest

# Install runtime requirements and bash
RUN apk add --no-cache bash

# Copy only the stripped mysqldump binary
COPY --from=builder /usr/local/mysql/bin/mysqldump /usr/local/bin/

# Ensure executable permissions
RUN chmod +x /usr/local/bin/mysqldump

# Default shell
ENTRYPOINT ["/bin/bash"]