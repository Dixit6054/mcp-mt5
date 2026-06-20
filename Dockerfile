# Stage 1: Download and unpack Hangover
FROM ubuntu:24.04 AS hangover-builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl tar
WORKDIR /opt
RUN curl -L -O https://github.com/AndreRH/hangover/releases/download/hangover-11.9/hangover_11.9_ubuntu2404_noble_arm64.tar && \
    tar -xf hangover_11.9_ubuntu2404_noble_arm64.tar && \
    rm hangover_11.9_ubuntu2404_noble_arm64.tar

# Stage 2: Final image
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# Copy Hangover deb packages from builder stage
COPY --from=hangover-builder /opt/*.deb /opt/

# Install base packages, dependencies, and hangover deb packages
RUN apt-get update && apt-get install -y \
    xvfb \
    x11-apps \
    xauth \
    ca-certificates \
    curl \
    libasound2t64 \
    libpulse0 \
    x11vnc \
    && apt-get install -y /opt/*.deb \
    && rm -rf /opt/*.deb /var/lib/apt/lists/*

# Set environment variables
ENV WINEPREFIX=/root/.wine
ENV DISPLAY=:99
ENV WINEDEBUG=-all

# Expose VNC port
EXPOSE 5900


# Copy validation and entrypoint scripts
COPY config-validator.sh /usr/local/bin/config-validator.sh
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/config-validator.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
