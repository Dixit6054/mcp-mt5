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

# Install base packages (libasound2t64 is for Ubuntu 24.04)
RUN apt-get update && apt-get install -y \
    xvfb \
    x11-apps \
    xauth \
    ca-certificates \
    curl \
    libasound2t64 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

# Copy Hangover
COPY --from=hangover-builder /opt/hangover /opt/hangover

# Set up symlinks for Wine / Hangover binaries
RUN ln -s /opt/hangover/bin/wine /usr/local/bin/wine && \
    ln -s /opt/hangover/bin/wine64 /usr/local/bin/wine64 && \
    ln -s /opt/hangover/bin/winecfg /usr/local/bin/winecfg && \
    ln -s /opt/hangover/bin/wineserver /usr/local/bin/wineserver

# Set environment variables
ENV WINEPREFIX=/root/.wine
ENV DISPLAY=:99
ENV WINEDEBUG=-all

# Pre-create Wine prefix, install WebView2 and MT5 setup headless
RUN Xvfb :99 -screen 0 1024x768x16 & \
    export DISPLAY=:99 && \
    sleep 2 && \
    winecfg -v=win11 && \
    sleep 2 && \
    curl -L "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/f2910a1e-e5a6-4f17-b52d-7faf525d17f8/MicrosoftEdgeWebview2Setup.exe" -o webview2.exe && \
    wine webview2.exe /silent /install && \
    sleep 5 && \
    curl -L "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -o mt5setup.exe && \
    wine mt5setup.exe /auto && \
    # Wait for MT5 terminal to be fully installed in portable directory
    while [ ! -f "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; do sleep 1; done && \
    sleep 5 && \
    wineserver -k && \
    rm -f webview2.exe mt5setup.exe

# Copy validation and entrypoint scripts
COPY config-validator.sh /usr/local/bin/config-validator.sh
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/config-validator.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
