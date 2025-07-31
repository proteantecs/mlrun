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

# Configure cmake build with explicit install prefix
RUN cmake ../mysql-server \
    -DDOWNLOAD_BOOST=1 \
    -DWITH_BOOST=boost \
    -DWITH_UNIT_TESTS=OFF \
    -DWITHOUT_SERVER=ON \
    -DWITH_EDITLINE=bundled \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local/mysql \
    -DCMAKE_C_FLAGS="-O3" \
    -DCMAKE_CXX_FLAGS="-O3"

# Build and install
RUN make -j$(nproc) client
RUN make -j$(nproc) install

# Find and copy mysqldump to a known location for easier copying
RUN MYSQLDUMP_PATH=$(find /usr/local -name "mysqldump" -type f 2>/dev/null | head -1) && \
    if [ -z "$MYSQLDUMP_PATH" ]; then \
        echo "ERROR: mysqldump binary not found!" && exit 1; \
    else \
        echo "Found mysqldump at: $MYSQLDUMP_PATH" && \
        mkdir -p /tmp/mysql-bin && \
        cp "$MYSQLDUMP_PATH" /tmp/mysql-bin/mysqldump && \
        chmod +x /tmp/mysql-bin/mysqldump; \
    fi

# ---- Stage 2: Final minimal runtime image ----
FROM cgr.dev/chainguard/wolfi-base:latest

# Install runtime requirements and bash
RUN apk add --no-cache bash

# Create the user for mlrun
RUN adduser -u 1000 -D mlrun

# Copy the mysqldump binary from the known temporary location
COPY --from=builder /tmp/mysql-bin/mysqldump /usr/local/bin/mysqldump

# Ensure executable permissions
RUN chmod +x /usr/local/bin/mysqldump

# Default shell
ENTRYPOINT ["/bin/bash"]