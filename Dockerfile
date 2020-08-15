FROM ubuntu:focal as test

ENV HOME=/root
ENV TZ=Europe/Prague
ENV LC_ALL=en_US.utf8

# Install base packages
RUN \
  sed -i 's/# \(.*multiverse$\)/\1/g' /etc/apt/sources.list && \
  echo "# Installing base packages" && \
  ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
  apt-get update && \
  apt-get -y upgrade && \
  apt-get -y install --no-install-recommends \
    lua5.1 liblua5.1-0-dev libjson-c-dev ca-certificates \
    git cmake make pkg-config gcc g++ openssh-client \
    python3-prctl python3-dev python3-setuptools python3-jsonschema \
    python3-pip python3-pbkdf2 locales gpg gpg-agent libcap-dev \
    mosquitto \
    && \
  apt-get clean

# Update python paths
RUN \
  update-alternatives --install /usr/bin/python python /usr/bin/python3 1 && \
  update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Generate locales
RUN \
  echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
  locale-gen

# Compile libubox
RUN \
  mkdir -p ~/build && \
  cd ~/build && \
  rm -rf libubox && \
  git clone git://git.openwrt.org/project/libubox.git && \
  cd ~/build/libubox && \
  git checkout master && \
  cmake CMakeLists.txt -DCMAKE_INSTALL_PREFIX:PATH=/usr && \
  make install

# Compile uci
RUN \
  mkdir -p ~/build && \
  cd ~/build && \
  rm -rf uci && \
  git clone git://git.openwrt.org/project/uci.git && \
  cd ~/build/uci && \
  git checkout master && \
  cmake CMakeLists.txt -DCMAKE_INSTALL_PREFIX:PATH=/usr && \
  make install

# Compile ubus
RUN \
  mkdir -p ~/build && \
  cd ~/build && \
  rm -rf ubus && \
  git clone https://gitlab.labs.nic.cz/turris/ubus.git && \
  cd ~/build/ubus && \
  git checkout master && \
  cmake CMakeLists.txt -DCMAKE_INSTALL_PREFIX:PATH=/usr && \
  make install

# Install ubus python bindings
RUN \
  mkdir -p ~/build && \
  cd ~/build && \
  rm -rf python-ubus && \
  git clone https://gitlab.labs.nic.cz/turris/python-ubus.git && \
  cd ~/build/python-ubus && \
  pip install .

# Compile iwinfo
RUN \
  mkdir -p ~/build && \
  cd ~/build && \
  rm -rf rpcd && \
  git clone git://git.openwrt.org/project/iwinfo.git && \
  cd iwinfo && \
  ln -s /usr/lib/x86_64-linux-gnu/liblua5.1.so liblua.so && \
  sed -i 's/..CC....IWINFO_LDFLAGS/\$(LD) \$(IWINFO_LDFLAGS/' Makefile && \
  CFLAGS="-I/usr/include/lua5.1/" LD=ld FPIC="-fPIC" LDFLAGS="-lc" make && \
  cp -r include/* /usr/local/include/ && \
  cp libiwinfo.so /usr/local/lib/

# Compile rpcd
RUN \
  mkdir -p ~/build && \
  cd ~/build && \
  rm -rf rpcd && \
  git clone git://git.openwrt.org/project/rpcd.git && \
  cd rpcd && \
  cmake CMakeLists.txt && \
  make install

# Add Gitlab's SSH key
RUN \
  mkdir /root/.ssh && \
  ssh-keyscan gitlab.labs.nic.cz > /root/.ssh/known_hosts

CMD [ "bash" ]
